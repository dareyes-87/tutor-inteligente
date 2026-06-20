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

# --- Umbrales de grounding (calibrados con scripts/debug/diagnostico_distancias.py) ---
# ChromaDB usa distancia (no similitud): menor = más parecido.
# Dos criterios en OR para decidir si hay contexto suficiente:
#   - 1 fragmento MUY cercano basta (preguntas puntuales con un buen match), o
#   - 2+ fragmentos decentes bastan (preguntas amplias o con OCR ruidoso).
UMBRAL_ESTRICTO = 0.85
UMBRAL_AMPLIO = 1.5
MIN_FRAGMENTOS_AMPLIO = 2

# Distancia máxima de los fragmentos que DEVUELVE search_fragments (la ventana de
# contexto que ve el LLM). Es > UMBRAL_AMPLIO a propósito: la DECISIÓN de relevancia
# usa UMBRAL_AMPLIO (1.5), pero una vez decidido que SÍ hay contexto conviene pasarle
# al LLM también los chunks "casi match" (p. ej. 1.51) que a veces contienen el dato
# exacto. No afecta el rechazo de preguntas fuera del libro: esas ni llegan al LLM
# porque is_context_relevant() ya devolvió False con el umbral de 1.5.
MAX_DISTANCE = 1.55


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

    best_dist = min(
        (f["distance"] for f in fragments if f["distance"] is not None),
        default=None,
    )
    relevant = is_context_relevant(fragments)
    logger.info(
        f"RAG query='{query[:50]}' "
        f"best_dist={best_dist:.3f} relevant={relevant} ({len(fragments)} frags)"
        if best_dist is not None
        else f"RAG query='{query[:50]}' best_dist=NA relevant={relevant} (0 frags)"
    )
    return fragments


def is_context_relevant(fragments: list[dict]) -> bool:
    """
    Decide si los fragmentos recuperados son contexto suficiente y relevante.

    Grounding por dos criterios en OR (se ignoran los fragmentos sin distancia):
      - hay >= 1 fragmento con distancia <= UMBRAL_ESTRICTO (un match muy bueno), o
      - hay >= MIN_FRAGMENTOS_AMPLIO fragmentos con distancia <= UMBRAL_AMPLIO
        (varios matches decentes).

    La usan chat y actividades para rechazar de forma determinística las
    preguntas fuera de los libros. Se prioriza que las preguntas SÍ cubiertas
    por el libro pasen: un falso negativo (rechazar algo que sí está) es peor
    que un falso positivo, porque el prompt del LLM es la segunda red.
    """
    distancias = [f["distance"] for f in fragments if f.get("distance") is not None]

    match_fuerte = any(d <= UMBRAL_ESTRICTO for d in distancias)
    matches_amplios = sum(1 for d in distancias if d <= UMBRAL_AMPLIO)

    return match_fuerte or matches_amplios >= MIN_FRAGMENTOS_AMPLIO
