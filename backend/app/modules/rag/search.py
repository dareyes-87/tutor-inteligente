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


def _where_metadatos(
    asignatura: str | None,
    grado: str | None,
    page_cond: dict | None = None,
) -> dict | None:
    """Construye el filtro de metadatos de ChromaDB (AND) a partir de
    asignatura/grado y una condición opcional de página. Devuelve None si no
    hay ninguna condición."""
    conds: list[dict] = []
    if asignatura:
        conds.append({"asignatura": asignatura})
    if grado:
        conds.append({"grado": grado})
    if page_cond is not None:
        conds.append(page_cond)
    if not conds:
        return None
    if len(conds) == 1:
        return conds[0]
    return {"$and": conds}


def _consultar(collection, query_embedding, where_filter, top_k, aplicar_max_distance):
    """Ejecuta el query a ChromaDB y arma la lista de fragmentos.

    `aplicar_max_distance=False` conserva TODOS los resultados del filtro (se usa
    en la búsqueda por número de página: ahí el contenido de la página importa
    aunque no tenga solape semántico con "explícame la página X", así que el
    corte por distancia semántica no debe descartarlo)."""
    query_params = {
        "query_embeddings": [query_embedding],
        "n_results": top_k,
    }
    if where_filter:
        query_params["where"] = where_filter

    results = collection.query(**query_params)

    fragments = []
    if results and results["documents"] and results["documents"][0]:
        ids = results.get("ids", [[]])
        for i, doc in enumerate(results["documents"][0]):
            distance = results["distances"][0][i] if results["distances"] else None
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}

            # Filtrar por distancia máxima (solo en la búsqueda semántica normal)
            if aplicar_max_distance and distance is not None and distance > MAX_DISTANCE:
                continue

            fragments.append({
                "text": doc,
                # chunk_id de ChromaDB (= Fragmento.chunk_id_vectordb); permite
                # mapear el resultado de vuelta a la fila Fragmento en Postgres.
                "chunk_id": ids[0][i] if ids and ids[0] else None,
                "page_num": metadata.get("page_num"),
                "libro_id": metadata.get("libro_id"),
                "asignatura": metadata.get("asignatura"),
                "grado": metadata.get("grado"),
                "confidence": metadata.get("confidence"),
                "distance": round(distance, 4) if distance else None,
            })
    return fragments


def search_fragments(
    query: str,
    asignatura: str | None = None,
    grado: str | None = None,
    top_k: int = TOP_K,
    page_num: int | None = None,
) -> list[dict]:
    """
    Busca los fragmentos más relevantes para una pregunta.

    1. Convierte la pregunta a un vector (embedding).
    2. Busca en ChromaDB los fragmentos más cercanos.
    3. Filtra por asignatura/grado si se proporcionan.
    4. Devuelve los fragmentos con su texto, metadatos y distancia.

    Si `page_num` viene, hace una búsqueda FILTRADA por ese número de página
    (para consultas del tipo "explícame la página 12"), sin aplicar el corte por
    distancia semántica. Si esa página no tiene fragmentos, reintenta con las
    páginas adyacentes (±1, por posibles desalineaciones del OCR). Si aun así no
    hay resultados, devuelve lista vacía y el llamador decide el fallback.
    """
    # Generar embedding de la pregunta
    query_embedding = generate_embeddings([query])[0]

    collection = get_collection()

    # --- Búsqueda por número de página (filtro exacto, sin corte por distancia) ---
    if page_num is not None:
        where_pagina = _where_metadatos(asignatura, grado, {"page_num": page_num})
        fragments = _consultar(
            collection, query_embedding, where_pagina, top_k, aplicar_max_distance=False
        )
        if not fragments:
            # OCR puede haber asignado la página ±1: reintentar con adyacentes.
            adyacentes = [p for p in (page_num - 1, page_num + 1) if p > 0]
            where_adj = _where_metadatos(
                asignatura, grado, {"page_num": {"$in": adyacentes}}
            )
            fragments = _consultar(
                collection, query_embedding, where_adj, top_k, aplicar_max_distance=False
            )
        logger.info(
            f"RAG query='{query[:50]}' page_num={page_num} "
            f"({len(fragments)} frags por página)"
        )
        return fragments

    # --- Búsqueda semántica normal (con corte por distancia) ---
    where_filter = _where_metadatos(asignatura, grado)
    fragments = _consultar(
        collection, query_embedding, where_filter, top_k, aplicar_max_distance=True
    )

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


_MARCADORES_EJERCICIO = ("mesa lista", "ahora es tu turno", "ejercicio", "practica")


def es_ejercicio_del_libro(texto: str) -> bool:
    """True si el texto de un fragmento es un ejercicio del libro (resuelto o
    propuesto: "¡Mesa lista!", "Ahora es tu turno", etc.), no la teoría del tema.

    El LLM tiende a copiar estos ejercicios como si fueran la definición del
    concepto (p. ej. tomar los elementos de un ejercicio de conjuntos como si
    fueran la teoría de pertenencia). Se usa para filtrar el POOL de fragmentos
    ANTES de armar el contexto que ve el LLM (micro-lección y actividades); NO
    cambia qué fragmentos se recuperan por rango de páginas, solo cuáles de
    esos se le pasan al LLM como contexto.
    """
    t = (texto or "").lower()
    return any(marcador in t for marcador in _MARCADORES_EJERCICIO)


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
