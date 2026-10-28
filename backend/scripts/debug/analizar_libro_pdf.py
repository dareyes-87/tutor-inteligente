"""
Análisis en seco de un PDF antes de ingestarlo (sin OCR, sin LLM, sin escribir en BD).

- Cuenta páginas que la detección marcaría como digitales vs. que irían a OCR.
- Aplica chunking + filtro de ejercicios a las páginas digitales: % de teoría.
- Con --buscar, imprime el texto extraído de la página que contiene esa frase
  (modo actual de ingesta y, para comparar, otros modos de PyMuPDF).

Uso (dentro del contenedor):
  python scripts/debug/analizar_libro_pdf.py /tmp/libro.pdf --buscar "División de una expresión"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import fitz  # noqa: E402

from app.modules.ingesta.chunking import chunk_pages  # noqa: E402
from app.modules.ingesta.pdf_processor import _extract_digital_text, _page_has_text  # noqa: E402
from app.modules.rag.search import es_ejercicio_del_libro  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--buscar", help="frase a localizar (insensible a mayúsculas)")
    ap.add_argument("--ejemplos", type=int, default=0, help="nº de fragmentos de teoría/ejercicio a mostrar")
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    paginas, a_ocr = [], []
    for i, page in enumerate(doc):
        if _page_has_text(page):
            paginas.append({"page_num": i + 1, "text": _extract_digital_text(page),
                            "method": "digital", "confidence": 100.0})
        else:
            a_ocr.append(i + 1)
    print(f"{args.pdf}: {len(doc)} páginas, {len(paginas)} digitales, {len(a_ocr)} irían a OCR/imagen")
    if a_ocr:
        print(f"  páginas sin capa de texto: {a_ocr[:40]}{' …' if len(a_ocr) > 40 else ''}")

    chunks = chunk_pages(paginas, libro_id=0, asignatura="-", grado="-")
    ejercicios = [c for c in chunks if es_ejercicio_del_libro(c["text"])]
    teoria = len(chunks) - len(ejercicios)
    pct = 100 * teoria / len(chunks) if chunks else 0
    print(f"  fragmentos: {len(chunks)}, teoría (aceptados) {teoria} = {pct:.1f} %, ejercicio {len(ejercicios)}")
    for c in [c for c in chunks if not es_ejercicio_del_libro(c["text"])][: args.ejemplos]:
        print(f"\n  [TEORÍA p{c['metadata']['page_num']}] {c['text'][:300]!r}")
    for c in ejercicios[: args.ejemplos]:
        print(f"\n  [EJERCICIO p{c['metadata']['page_num']}] {c['text'][:300]!r}")

    if args.buscar:
        frase = args.buscar.lower()
        for i, page in enumerate(doc):
            if frase in page.get_text("text").lower():
                print(f"\n===== página {i + 1}: modo actual get_text('text', sort=True) =====")
                print(page.get_text("text", sort=True))
                print(f"\n===== página {i + 1}: get_text('text') sin sort =====")
                print(page.get_text("text"))
                print(f"\n===== página {i + 1}: get_text('blocks') =====")
                for b in page.get_text("blocks", sort=True):
                    print(repr(b[4]))
                break
        else:
            print(f"\n(no se encontró '{args.buscar}')")


if __name__ == "__main__":
    main()
