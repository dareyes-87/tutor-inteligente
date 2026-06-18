"""
Indexador: guarda los chunks con sus embeddings en ChromaDB.
ChromaDB permite filtrar por metadatos (asignatura, grado), lo que es
clave para que el RAG solo busque en los libros relevantes.
"""
import logging
import importlib
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "libros_texto"

_client = None


def _get_chromadb_module() -> Any:
    """Carga chromadb de forma diferida para evitar errores de resolución en análisis estático."""
    try:
        return importlib.import_module("chromadb")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "No se pudo importar 'chromadb'. Instala la dependencia con: pip install chromadb"
        ) from exc


def get_chroma_client() -> Any:
    """Conexión singleton a ChromaDB."""
    global _client
    if _client is None:
        chromadb = _get_chromadb_module()
        _client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
        )
        logger.info(f"Conectado a ChromaDB en {settings.CHROMA_HOST}:{settings.CHROMA_PORT}")
    return _client


def get_collection():
    """Obtiene o crea la colección de libros en ChromaDB."""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Fragmentos de libros de texto del Tutor Inteligente"},
    )


def index_chunks(
    chunks: list[dict],
    embeddings: list[list[float]],
) -> int:
    """
    Indexa los chunks con sus embeddings en ChromaDB.
    Devuelve la cantidad de chunks indexados.
    """
    collection = get_collection()

    ids = [c["chunk_id"] for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    # ChromaDB acepta lotes; enviamos todo de una vez
    # (para ~90 usuarios y libros escolares, los volúmenes son manejables)
    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    logger.info(f"Indexados {len(ids)} chunks en ChromaDB (colección: {COLLECTION_NAME})")
    return len(ids)


def delete_libro_chunks(libro_id: int) -> None:
    """Borra todos los chunks de un libro (para re-indexar)."""
    collection = get_collection()
    collection.delete(where={"libro_id": libro_id})
    logger.info(f"Eliminados chunks del libro {libro_id} de ChromaDB")
