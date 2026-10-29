"""
reconstruir_chroma.py — rehace la colección de Chroma desde la tabla `fragmento` de Postgres.

Para el traslado a producción (docs/despliegue-produccion.md, sección 9): tras restaurar
el dump de Postgres, el Chroma de destino está vacío (o tiene datos viejos). Este script
recalcula los embeddings (mismo modelo que la ingesta) y escribe cada fragmento con:
  id        = fragmento.chunk_id_vectordb (el que el RAG devuelve y une con `fragmento`)
  document  = fragmento.contenido_texto
  metadata  = {libro_id, asignatura, grado (NOMBRES), page_num, method, confidence},
              los mismos que escribe ingesta/chunking.py; method = "digital" si la
              confianza es 100, si no "ocr".
Sin OCR ni LLM. Re-ejecutable (upsert). Si la colección ya tiene vectores, aborta salvo
con --vaciar (la borra antes: evita fragmentos fantasma que ya no están en Postgres).

Uso (DENTRO del contenedor backend, working dir /app):
    PYTHONPATH=/app python scripts/reconstruir_chroma.py [--vaciar] [--lote 256]
"""
import argparse
import asyncio
import time

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.asignatura import Asignatura
from app.models.fragmento import Fragmento
from app.models.grado import Grado
from app.models.libro import LibroTexto
from app.modules.ingesta.embeddings import generate_embeddings
from app.modules.ingesta.indexer import COLLECTION_NAME, get_chroma_client, get_collection


async def main(vaciar: bool, lote: int) -> None:
    t0 = time.time()
    coleccion = get_collection()
    if coleccion.count():
        if not vaciar:
            raise SystemExit(f"La colección ya tiene {coleccion.count()} vectores; usar --vaciar para rehacerla.")
        get_chroma_client().delete_collection(COLLECTION_NAME)
        coleccion = get_collection()

    async with AsyncSessionLocal() as db:
        filas = (await db.execute(
            select(Fragmento, Asignatura.nombre, Grado.nombre)
            .join(LibroTexto, Fragmento.libro_id == LibroTexto.id)
            .join(Asignatura, LibroTexto.asignatura_id == Asignatura.id)
            .join(Grado, LibroTexto.grado_id == Grado.id)
            .order_by(Fragmento.id)
        )).all()
    print(f"{len(filas)} fragmentos en Postgres")

    for i in range(0, len(filas), lote):
        parte = filas[i:i + lote]
        textos = [f.contenido_texto for f, _, _ in parte]
        coleccion.upsert(
            ids=[f.chunk_id_vectordb for f, _, _ in parte],
            documents=textos,
            embeddings=await asyncio.to_thread(generate_embeddings, textos),
            metadatas=[{
                "libro_id": f.libro_id, "asignatura": asignatura, "grado": grado,
                "page_num": f.numero_pagina,
                "method": "digital" if f.confianza_ocr == 100 else "ocr",
                "confidence": f.confianza_ocr,
            } for f, asignatura, grado in parte],
        )
        print(f"  {min(i + lote, len(filas))}/{len(filas)}  ({time.time() - t0:.0f} s)", flush=True)

    total = coleccion.count()
    print(f"Chroma: {total} vectores (Postgres: {len(filas)}) en {time.time() - t0:.0f} s")
    if total != len(filas):
        raise SystemExit("ERROR: los conteos no coinciden (¿chunk_id_vectordb repetidos?)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vaciar", action="store_true", help="borra la colección antes de reconstruirla")
    ap.add_argument("--lote", type=int, default=256)
    args = ap.parse_args()
    asyncio.run(main(args.vaciar, args.lote))
