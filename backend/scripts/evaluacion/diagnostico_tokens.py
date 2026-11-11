"""
Diagnóstico de tokens por fragmento (correcciones del jurado, paso 1 y 2).

Lee TODOS los fragmentos de una colección de ChromaDB (los mismos chunks que
produjo process_pdf() + chunk_pages() en la ingesta) y los tokeniza con el
tokenizador del modelo de embeddings indicado, para medir cuánto texto queda
fuera de su ventana (max_seq_length, que incluye los tokens especiales).

Uso (dentro del contenedor backend):
    python scripts/evaluacion/diagnostico_tokens.py                      # MiniLM, libros_texto
    python scripts/evaluacion/diagnostico_tokens.py --modelo intfloat/multilingual-e5-small \
        --prefijo "passage: " --coleccion libros_texto

Imprime un JSON con las cifras (se copia a docs/tesis/resultados_correcciones_jurado.md).
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/
from sentence_transformers import SentenceTransformer  # noqa: E402

from app.modules.ingesta.indexer import get_chroma_client  # noqa: E402


def percentil(valores: list[int], p: float) -> float:
    s = sorted(valores)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default="paraphrase-multilingual-MiniLM-L12-v2")
    ap.add_argument("--prefijo", default="", help='p. ej. "passage: " para e5')
    ap.add_argument("--coleccion", default="libros_texto")
    args = ap.parse_args()

    col = get_chroma_client().get_collection(args.coleccion)
    datos = col.get(include=["documents", "metadatas"])
    textos = [args.prefijo + t for t in datos["documents"]]
    libros = {m["libro_id"] for m in datos["metadatas"]}

    model = SentenceTransformer(args.modelo)
    tok = model.tokenizer
    ventana = model.max_seq_length

    n_tokens, fraccion_fuera = [], []
    for t in textos:
        enc = tok(t, add_special_tokens=True, return_offsets_mapping=True)
        n = len(enc["input_ids"])
        n_tokens.append(n)
        if n <= ventana:
            fraccion_fuera.append(0.0)
            continue
        # Último token de contenido que entra (ventana - 1 token especial final).
        offsets = [o for o in enc["offset_mapping"][: ventana - 1] if o[1] > 0]
        chars_dentro = offsets[-1][1] if offsets else 0
        fraccion_fuera.append(1 - chars_dentro / len(t))

    superan = sum(1 for n in n_tokens if n > ventana)
    print(json.dumps({
        "modelo": args.modelo,
        "coleccion": args.coleccion,
        "prefijo": args.prefijo,
        "max_seq_length": ventana,
        "dimension": model.get_sentence_embedding_dimension(),
        "libros": len(libros),
        "fragmentos": len(textos),
        "chars_media": round(statistics.mean(len(t) for t in textos), 1),
        "tokens_media": round(statistics.mean(n_tokens), 1),
        "tokens_mediana": statistics.median(n_tokens),
        "tokens_p90": percentil(n_tokens, 90),
        "tokens_max": max(n_tokens),
        "fragmentos_que_superan_ventana": superan,
        "pct_fragmentos_que_superan_ventana": round(100 * superan / len(textos), 2),
        "pct_texto_fuera_promedio_todos": round(100 * statistics.mean(fraccion_fuera), 2),
        "pct_texto_fuera_promedio_truncados": round(
            100 * statistics.mean([f for f in fraccion_fuera if f > 0]), 2) if superan else 0.0,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
