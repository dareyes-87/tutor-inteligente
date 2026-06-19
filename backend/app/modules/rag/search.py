"""
Búsqueda semántica RAG: encuentra los fragmentos más relevantes
para una pregunta del estudiante.
"""
import logging

from app.modules.ingesta.embeddings import generate_embeddings
from app.modules.ingesta.indexer import get_collection

logger = logging.getLogger(__name__)

# Cuántos fragmentos devolver como contexto al LLM
TOP_K = 5
# Distancia máxima (ChromaDB usa distancia, no similitud; menor = más similar)
MAX_DISTANCE = 1.5


def search_fragments(
    query: str,
    asignatura: str | None = None,
    grado: str | None = None,
    top_k: int = TOP_K,
) -> list[dict]:
    """
    Busca los fragmentos más relevantes para una pregunta.

    1. Convierte la pregunta a un vector (embedding).
    2. Busca en ChromaDB los fragmentos más cercanos.
    3. Filtra por asignatura/grado si se proporcionan.
    4. Devuelve los fragmentos con su texto, metadatos y distancia.
    """
    # Generar embedding de la pregunta
    query_embedding = generate_embeddings([query])[0]

    collection = get_collection()

    # Construir filtro de metadatos (AND)
    where_filter = {}
    if asignatura and grado:
        where_filter = {
            "$and": [
                {"asignatura": asignatura},
                {"grado": grado},
            ]
        }
    elif asignatura:
        where_filter = {"asignatura": asignatura}
    elif grado:
        where_filter = {"grado": grado}

    # Buscar en ChromaDB
    query_params = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
    }
    if where_filter:
        query_params["where"] = where_filter

    results = collection.query(**query_params)

    # Procesar resultados
    fragments = []
    if results and results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            distance = results["distances"][0][i] if results["distances"] else None
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}

            # Filtrar por distancia máxima
            if distance is not None and distance > MAX_DISTANCE:
                continue

            fragments.append({
                "text": doc,
                "page_num": metadata.get("page_num"),
                "libro_id": metadata.get("libro_id"),
                "asignatura": metadata.get("asignatura"),
                "grado": metadata.get("grado"),
                "confidence": metadata.get("confidence"),
                "distance": round(distance, 4) if distance else None,
            })

    logger.info(
        f"RAG: query='{query[:50]}...' -> {len(fragments)} fragmentos encontrados"
    )
    return fragments
