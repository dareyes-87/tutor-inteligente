"""
Worker de ingesta: procesa un PDF en segundo plano.
Se lanza desde el endpoint de subida usando FastAPI BackgroundTasks.
NUNCA corre dentro del request HTTP (un libro puede tardar minutos).
"""
import asyncio
import logging
import multiprocessing
import os
import traceback
from concurrent.futures import ProcessPoolExecutor

import torch
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
from app.modules.lecciones.generator import (
    generar_lecciones_desde_libro,
    libro_tiene_lecciones,
)

logger = logging.getLogger(__name__)


def _iniciar_proceso_hijo() -> None:
    logging.basicConfig(level=logging.INFO)
    # Deja la mitad de los núcleos al servidor (embedding de las preguntas del chat);
    # con todos, el chat tardaba hasta 8 s durante los embeddings de un libro grande.
    torch.set_num_threads(max(1, (os.cpu_count() or 2) // 2))


def _proceso_de_ingesta() -> ProcessPoolExecutor:
    """Proceso hijo para lo pesado en CPU (spawn: no hereda threads de torch ni del loop)."""
    return ProcessPoolExecutor(
        max_workers=1,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=_iniciar_proceso_hijo,
    )


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
    loop = asyncio.get_running_loop()
    hijo = _proceso_de_ingesta()
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
            # En el proceso hijo, no en un thread: PyMuPDF retiene el GIL en páginas
            # enormes (tablas de ~100 000 caracteres de las Guías) y en un thread
            # congelaba /health y el chat hasta 18 s.
            logger.info(f"[Libro {libro_id}] Iniciando extracción de texto...")
            pages = await loop.run_in_executor(hijo, process_pdf, libro.archivo_pdf_path)
            libro.total_paginas = len(pages)
            libro.paginas_procesadas = len(pages)
            await db.commit()

            if not pages:
                libro.estado_indexacion = EstadoIndexacion.error
                libro.error_detalle = "No se pudo extraer texto de ninguna página"
                await db.commit()
                return

            # === PASO 2: Chunking ===
            # CPU-bound: también en thread aparte.
            logger.info(f"[Libro {libro_id}] Dividiendo en chunks...")
            chunks = await asyncio.to_thread(
                chunk_pages,
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
            # sentence-transformers/torch en CPU es pesado: en el proceso hijo.
            logger.info(f"[Libro {libro_id}] Generando embeddings para {len(chunks)} chunks...")
            texts = [c["text"] for c in chunks]
            embeddings = await loop.run_in_executor(hijo, generate_embeddings, texts)
            hijo.shutdown(wait=False)

            # === PASO 4: Indexar en ChromaDB ===
            # I/O síncrona al cliente Chroma: en thread aparte para no bloquear.
            logger.info(f"[Libro {libro_id}] Indexando en ChromaDB...")
            await asyncio.to_thread(index_chunks, chunks, embeddings)

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

            # === PASO 7: Generar ruta de aprendizaje (lecciones) ===
            # Aislado en su propio try: si falla, el libro queda indexado igual.
            try:
                if await libro_tiene_lecciones(libro.id, db):
                    logger.info(
                        f"[Libro {libro_id}] Ya tiene lecciones; se omite la generación"
                    )
                else:
                    logger.info(f"[Libro {libro_id}] Generando lecciones automáticas...")
                    lecciones = await generar_lecciones_desde_libro(libro.id, db)
                    logger.info(
                        f"[Libro {libro_id}] {len(lecciones)} lecciones generadas"
                    )
            except Exception as e:
                logger.error(f"[Libro {libro_id}] No se pudieron generar lecciones: {e}")
                logger.error(traceback.format_exc())

        except Exception as e:
            logger.error(f"[Libro {libro_id}] ❌ Error: {e}")
            logger.error(traceback.format_exc())
            try:
                libro.estado_indexacion = EstadoIndexacion.error
                libro.error_detalle = str(e)[:500]
                await db.commit()
            except Exception:
                pass
        finally:
            hijo.shutdown(wait=False)
