"""
Worker de ingesta: procesa un PDF en segundo plano.
Se lanza desde el endpoint de subida usando FastAPI BackgroundTasks.
NUNCA corre dentro del request HTTP (un libro puede tardar minutos).
"""
import logging
import traceback

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.libro import LibroTexto, EstadoIndexacion
from app.models.fragmento import Fragmento
from app.models.asignatura import Asignatura
from app.models.grado import Grado
from app.modules.ingesta.pdf_processor import process_pdf
from app.modules.ingesta.chunking import chunk_pages
from app.modules.ingesta.embeddings import generate_embeddings
from app.modules.ingesta.indexer import index_chunks

logger = logging.getLogger(__name__)


async def procesar_libro(libro_id: int) -> None:
    """
    Pipeline completo de ingesta de un libro:
    1. Extraer texto (digital + OCR)
    2. Dividir en chunks con metadatos
    3. Generar embeddings
    4. Indexar en ChromaDB
    5. Guardar fragmentos en Postgres
    6. Actualizar estado del libro
    """
    async with AsyncSessionLocal() as db:
        try:
            # Obtener el libro con sus relaciones
            result = await db.execute(
                select(LibroTexto).where(LibroTexto.id == libro_id)
            )
            libro = result.scalar_one_or_none()
            if libro is None:
                logger.error(f"Libro {libro_id} no encontrado")
                return

            # Marcar como procesando
            libro.estado_indexacion = EstadoIndexacion.procesando
            await db.commit()

            # Obtener nombres de asignatura y grado para metadatos
            asig = await db.execute(
                select(Asignatura).where(Asignatura.id == libro.asignatura_id)
            )
            asignatura_obj = asig.scalar_one()

            gr = await db.execute(
                select(Grado).where(Grado.id == libro.grado_id)
            )
            grado_obj = gr.scalar_one()

            # === PASO 1: Extraer texto ===
            logger.info(f"[Libro {libro_id}] Iniciando extracción de texto...")
            pages = process_pdf(libro.archivo_pdf_path)
            libro.total_paginas = len(pages)
            libro.paginas_procesadas = len(pages)
            await db.commit()

            if not pages:
                libro.estado_indexacion = EstadoIndexacion.error
                libro.error_detalle = "No se pudo extraer texto de ninguna página"
                await db.commit()
                return

            # === PASO 2: Chunking ===
            logger.info(f"[Libro {libro_id}] Dividiendo en chunks...")
            chunks = chunk_pages(
                pages,
                libro_id=libro.id,
                asignatura=asignatura_obj.nombre,
                grado=grado_obj.nombre,
            )

            if not chunks:
                libro.estado_indexacion = EstadoIndexacion.error
                libro.error_detalle = "No se generaron fragmentos del texto extraído"
                await db.commit()
                return

            # === PASO 3: Embeddings ===
            logger.info(f"[Libro {libro_id}] Generando embeddings para {len(chunks)} chunks...")
            texts = [c["text"] for c in chunks]
            embeddings = generate_embeddings(texts)

            # === PASO 4: Indexar en ChromaDB ===
            logger.info(f"[Libro {libro_id}] Indexando en ChromaDB...")
            index_chunks(chunks, embeddings)

            # === PASO 5: Guardar fragmentos en Postgres ===
            logger.info(f"[Libro {libro_id}] Guardando fragmentos en Postgres...")
            for chunk in chunks:
                fragmento = Fragmento(
                    libro_id=libro.id,
                    contenido_texto=chunk["text"],
                    numero_pagina=chunk["metadata"]["page_num"],
                    tema=None,  # se puede enriquecer después
                    chunk_id_vectordb=chunk["chunk_id"],
                    confianza_ocr=chunk["metadata"]["confidence"],
                )
                db.add(fragmento)

            # === PASO 6: Calcular confianza promedio y finalizar ===
            ocr_pages = [p for p in pages if p["method"] == "ocr"]
            if ocr_pages:
                avg_conf = sum(p["confidence"] for p in ocr_pages) / len(ocr_pages)
            else:
                avg_conf = 100.0  # todo digital

            libro.confianza_ocr_promedio = round(avg_conf, 2)
            libro.estado_indexacion = EstadoIndexacion.completado
            libro.error_detalle = None
            await db.commit()

            logger.info(
                f"[Libro {libro_id}] ✅ Completado: {len(chunks)} fragmentos, "
                f"confianza OCR promedio: {avg_conf:.1f}%"
            )

        except Exception as e:
            logger.error(f"[Libro {libro_id}] ❌ Error: {e}")
            logger.error(traceback.format_exc())
            try:
                libro.estado_indexacion = EstadoIndexacion.error
                libro.error_detalle = str(e)[:500]
                await db.commit()
            except Exception:
                pass
