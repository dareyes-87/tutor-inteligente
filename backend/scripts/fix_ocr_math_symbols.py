"""
fix_ocr_math_symbols.py — corrección one-shot de símbolos matemáticos mal OCR-eados.

Los libros de Matemáticas escaneados (con teléfono) confunden en el OCR el símbolo
∈ (pertenencia a un conjunto) con € (euro). Esto es cosmético en el chat, pero grave
en las micro-lecciones: el generador de tarjetas produce quizzes que enseñan y
CALIFICAN que "€" es el símbolo de pertenencia.

Este script corrige € -> ∈ SOLO cuando el "€" aparece en contexto de teoría de
conjuntos (cerca de palabras como "pertenece", "conjunto", "elemento"...). NUNCA
toca las páginas de conversión de monedas (euros reales), ni el "€" de ruido de OCR
que no está en contexto matemático (p. ej. "agua €N un vaso" — dejar € es menos malo
que convertirlo a ∈).

Mantiene en sync PostgreSQL (fragmento.contenido_texto) y ChromaDB (documento +
embedding re-calculado), porque el RAG consulta Chroma, no Postgres.

Reutilizable para los libros de 5to/6to Matemáticas (mismo problema de OCR) vía
--libro-id, ajustando --excluir-paginas según dónde estén los euros reales.

Uso (DENTRO del contenedor backend):
    docker compose exec backend python scripts/fix_ocr_math_symbols.py --libro-id 4
    docker compose exec backend python scripts/fix_ocr_math_symbols.py --libro-id 4 \
        --excluir-paginas 62,63 --dry-run
"""
import argparse
import asyncio
import re

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.fragmento import Fragmento
from app.modules.ingesta.embeddings import generate_embeddings
from app.modules.ingesta.indexer import get_collection

# Si alguna de estas palabras está en la ventana alrededor de un "€", ese "€" es en
# realidad ∈ (pertenencia) mal OCR-eado y se corrige. Si no, se deja intacto.
PALABRAS_CONTEXTO = (
    "pertenece",
    "pertenecen",
    "pertenencia",
    "conjunto",
    "conjuntos",
    "elemento",
    "elementos",
    "simboliza",
    "subconjunto",
    "subconjuntos",
)
# Chars a cada lado del "€" donde buscar una palabra de contexto de conjuntos.
VENTANA = 60


def corregir_texto(texto: str) -> tuple[str, int]:
    """Sustituye € -> ∈ solo cuando hay contexto de teoría de conjuntos cerca.

    Devuelve (texto_corregido, n_sustituciones). Trabaja por-ocurrencia: dentro de
    un mismo fragmento, un "€" con contexto se convierte y otro sin contexto se deja.
    """
    low = texto.lower()
    partes: list[str] = []
    ultimo = 0
    n = 0
    for m in re.finditer("€", texto):
        i = m.start()
        ventana = low[max(0, i - VENTANA) : i + VENTANA + 1]
        if any(w in ventana for w in PALABRAS_CONTEXTO):
            partes.append(texto[ultimo:i])
            partes.append("∈")
            ultimo = i + 1
            n += 1
        # sin contexto matemático: no se toca el "€"
    partes.append(texto[ultimo:])
    return "".join(partes), n


async def main(libro_id: int, excluir_paginas: set[int], dry_run: bool) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Fragmento)
            .where(Fragmento.libro_id == libro_id)
            .where(Fragmento.contenido_texto.like("%€%"))
            .order_by(Fragmento.numero_pagina, Fragmento.id)
        )
        fragmentos = list(result.scalars().all())

        print(f"\n=== fix_ocr_math_symbols · libro_id={libro_id} ===")
        print(f"Fragmentos con '€': {len(fragmentos)}")
        print(f"Páginas excluidas (euros reales): {sorted(excluir_paginas) or '—'}")
        print(f"Modo: {'DRY-RUN (no escribe)' if dry_run else 'APLICAR CAMBIOS'}\n")

        cambios: list[tuple[Fragmento, str]] = []
        total_subs = 0
        for f in fragmentos:
            if f.numero_pagina in excluir_paginas:
                print(f"  [saltado pág {f.numero_pagina}] frag {f.id} (página de euros excluida)")
                continue
            nuevo, n = corregir_texto(f.contenido_texto)
            if n > 0:
                cambios.append((f, nuevo))
                total_subs += n
                extracto = " ".join(nuevo.split())
                idx = extracto.find("∈")
                ventana_txt = extracto[max(0, idx - 35) : idx + 35]
                print(f"  [CORREGIR pág {f.numero_pagina}] frag {f.id} ({f.chunk_id_vectordb}): "
                      f"{n} sustitución(es) €→∈  …{ventana_txt}…")
            else:
                print(f"  [sin cambio pág {f.numero_pagina}] frag {f.id}: '€' es ruido/sin contexto, se deja")

        print(f"\nFragmentos a corregir: {len(cambios)}")

        if not cambios:
            print("Nada que actualizar.\n")
            return

        if dry_run:
            print("DRY-RUN: no se escribió nada. Quita --dry-run para aplicar.\n")
            return

        # Re-embeddear los textos corregidos y actualizar Postgres + Chroma en sync.
        textos = [nuevo for _, nuevo in cambios]
        print("Re-calculando embeddings de los textos corregidos...")
        embeddings = generate_embeddings(textos)

        collection = get_collection()
        collection.update(
            ids=[f.chunk_id_vectordb for f, _ in cambios],
            documents=textos,
            embeddings=embeddings,
        )
        print(f"ChromaDB: {len(cambios)} documentos actualizados (documento + embedding).")

        for f, nuevo in cambios:
            f.contenido_texto = nuevo
        await db.commit()
        print(f"PostgreSQL: {len(cambios)} filas 'fragmento' actualizadas.")

        print("\n=== REPORTE FINAL ===")
        paginas = sorted({f.numero_pagina for f, _ in cambios})
        print(f"  Fragmentos corregidos: {len(cambios)}  ({total_subs} sustitución(es) €→∈ en total)")
        print(f"  Páginas afectadas: {paginas}")
        print(f"  Sustitución aplicada: € → ∈ (solo en contexto de conjuntos)")
        print("  Sincronizado en PostgreSQL y ChromaDB.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Corrige € -> ∈ mal OCR-eado en un libro.")
    parser.add_argument("--libro-id", type=int, required=True, help="ID del libro a corregir")
    parser.add_argument(
        "--excluir-paginas",
        type=str,
        default="62,63",
        help="Páginas con euros reales a excluir, separadas por coma (default: 62,63)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra qué haría, sin escribir")
    args = parser.parse_args()

    excluir = {int(p) for p in args.excluir_paginas.split(",") if p.strip().isdigit()}
    asyncio.run(main(args.libro_id, excluir, args.dry_run))
