"""
Diagnóstico de distancias RAG para calibrar el grounding.

Mide las distancias reales que devuelve ChromaDB para un conjunto de
consultas (unas que SÍ están en el libro y otras que no), SIN aplicar el
corte de MAX_DISTANCE, para poder elegir umbrales con datos.

Uso:
    docker compose exec backend python3 scripts/debug/diagnostico_distancias.py

Es una herramienta de calibración: re-ejecutar cuando se indexen libros
nuevos para revisar si los umbrales de is_context_relevant() siguen bien.
"""
import os
import sys

# Permite ejecutar el script directamente (añade la raíz del backend, /app, al path).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.modules.ingesta.embeddings import generate_embeddings  # noqa: E402
from app.modules.ingesta.indexer import get_collection
from app.modules.rag.search import is_context_relevant, MAX_DISTANCE

# Filtro igual al que usa un estudiante real (carlos: Ciencias Naturales, 1ro Basico)
ASIGNATURA = "Ciencias Naturales"
GRADO = "1ro Basico"

CONSULTAS_LIBRO = [
    "¿Cuáles son los parásitos más frecuentes?",
    "¿Cuánto mide la Áscaris lumbricoides?",
    "¿Qué es la desnutrición?",
    "¿Cuáles son los nutrientes que necesita el cuerpo?",
    "¿Qué son los primeros auxilios?",
    "¿Cómo afecta el ruido a la audición?",
    "cuando mide la ascaris",  # error ortográfico intencional (simula a un niño)
    "que es la piramide alimenticia",
]
CONSULTAS_FUERA = [
    "¿Cuáles son las partes de una computadora?",
    "¿Cuál es la capital de Francia?",
]

BUCKETS = [0.85, 1.0, 1.1, 1.2]


def top5(query: str) -> list[dict]:
    """Top-5 fragmentos crudos (sin corte de distancia)."""
    emb = generate_embeddings([query])[0]
    res = get_collection().query(
        query_embeddings=[emb],
        n_results=5,
        where={"$and": [{"asignatura": ASIGNATURA}, {"grado": GRADO}]},
    )
    frags = []
    docs = res["documents"][0] if res.get("documents") else []
    dists = res["distances"][0] if res.get("distances") else []
    metas = res["metadatas"][0] if res.get("metadatas") else []
    for i, doc in enumerate(docs):
        d = dists[i] if i < len(dists) else None
        meta = metas[i] if i < len(metas) else {}
        frags.append({
            "text": doc,
            "distance": round(d, 4) if d is not None else None,
            "page_num": meta.get("page_num"),
        })
    return frags


def evaluar(query: str):
    frags = top5(query)
    print(f"\n>>> {query!r}")
    for f in frags:
        txt = (f["text"] or "").replace("\n", " ")[:80]
        print(f"    dist={f['distance']}  pág={f['page_num']}  {txt!r}")
    counts = {b: sum(1 for f in frags if f["distance"] is not None and f["distance"] <= b) for b in BUCKETS}
    print("    conteo por umbral: " + "  ".join(f"<= {b}: {counts[b]}" for b in BUCKETS))
    print(f"    is_context_relevant() ACTUAL (MAX_DISTANCE={MAX_DISTANCE}): {is_context_relevant(frags)}")


def main():
    print("=" * 70)
    print(f"DIAGNÓSTICO DE DISTANCIAS RAG  (asignatura={ASIGNATURA!r}, grado={GRADO!r})")
    print(f"Fragmentos indexados: {get_collection().count()}")
    print("=" * 70)
    print("\n### DEBEN PASAR (están en el libro) ###")
    for q in CONSULTAS_LIBRO:
        evaluar(q)
    print("\n\n### DEBEN SER RECHAZADAS (fuera del libro) ###")
    for q in CONSULTAS_FUERA:
        evaluar(q)
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
