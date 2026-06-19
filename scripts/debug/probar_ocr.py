"""
Script de debug TEMPORAL para medir el OCR mejorado sobre un PDF concreto,
sin pasar por toda la ingesta (sin tocar Postgres ni ChromaDB).

Uso (dentro del contenedor backend):
    docker compose exec backend python scripts/debug/probar_ocr.py /ruta/al/libro.pdf

Imprime, por página, el método (digital/ocr/imagen), la confianza y un extracto
del texto; y al final un resumen con la confianza OCR promedio del libro.

Borrar esta carpeta (scripts/debug/) cuando ya no se necesite.
"""
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")

from app.modules.ingesta.pdf_processor import process_pdf


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python scripts/debug/probar_ocr.py <ruta_al_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    print(f"\n=== Procesando: {pdf_path} ===\n")

    pages = process_pdf(pdf_path)

    print("\n=== Detalle por página ===")
    for p in pages:
        extracto = p["text"][:120].replace("\n", " ")
        print(
            f"  Pág {p['page_num']:>2} | {p['method']:<7} | "
            f"conf={p['confidence']:>5.1f} | {len(p['text']):>4} chars | {extracto}"
        )

    ocr = [p for p in pages if p["method"] == "ocr"]
    digital = [p for p in pages if p["method"] == "digital"]
    imagen = [p for p in pages if p["method"] == "imagen"]
    avg = sum(p["confidence"] for p in ocr) / len(ocr) if ocr else 0.0

    print("\n=== Resumen ===")
    print(f"  Total páginas:        {len(pages)}")
    print(f"  Digitales:            {len(digital)}")
    print(f"  OCR:                  {len(ocr)}")
    print(f"  Saltadas (imagen):    {len(imagen)} -> {[p['page_num'] for p in imagen]}")
    print(f"  Confianza OCR promedio: {avg:.1f}%  (antes con libro de prueba: 51.8%)")


if __name__ == "__main__":
    main()
