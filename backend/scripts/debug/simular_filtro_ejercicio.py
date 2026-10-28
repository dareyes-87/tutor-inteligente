"""
Simula cambios al filtro de ejercicios (rag/search.py::es_ejercicio_del_libro)
contra TODOS los fragmentos de la BD local, sin tocar el código de la app.

Variantes (frente al filtro actual). NOTA: V3 es el filtro aplicado en
rag/search.py (2026-10-28; V2 se probó y se revirtió). Desde entonces "actual" es V3.
  V1  quitar el marcador suelto "ejercicio" (en este corpus solo coincide con
      notas al docente —"propóngales un ejercicio"— o con "hacer ejercicio"
      físico, que es teoría de Ciencias).
  V2  V1 + normalizar espacios/saltos de línea antes de buscar marcadores (el
      OCR parte frases como "Ahora es tu\\nturno" y el filtro actual no las ve).
  V3  propuesta acotada: V1, pero un fragmento que hoy solo marca "ejercicio"
      SIGUE marcado si, normalizando espacios, contiene otro marcador (es decir,
      sí trae un ejercicio real partido por el OCR). No marca nada nuevo.

  V5  V4 corregido tras medirlo (ver comentario de v5). APLICADO en rag/search.py
      (2026-10-28): desde entonces "actual" = V5 y V3 sirve de referencia anterior.
  V4  (primera propuesta para libros MINEDUC de básico, con --pdf) actual + dos reglas:
      - "Paso N" sin "¿Qué más necesitamos saber?" -> ejercicio (Guías de Ciencias);
      - instrucción numerada ("1. Escriba…", "2. Calcule…") sin "Ejemplo" ->
        ejercicio (Matemática; el ejemplo resuelto y la conclusión se conservan).

Uso (dentro del contenedor):
    docker compose exec backend python scripts/debug/simular_filtro_ejercicio.py
    docker compose exec backend python scripts/debug/simular_filtro_ejercicio.py --pdf /tmp/1B.pdf /tmp/G1.pdf
"""
import argparse
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text  # noqa: E402

from app.config import settings  # noqa: E402
from app.modules.rag.search import _MARCADORES_EJERCICIO, es_ejercicio_del_libro  # noqa: E402

V1 = tuple(m for m in _MARCADORES_EJERCICIO if m != "ejercicio")


def v1(texto: str) -> bool:
    t = (texto or "").lower()
    return any(m in t for m in V1)


def v2(texto: str) -> bool:
    return v1(re.sub(r"\s+", " ", texto or ""))


def v3(texto: str) -> bool:
    return v1(texto) or ("ejercicio" in (texto or "").lower() and v2(texto))


_PASO = re.compile(r"\bpaso\s+\d")
# Verbos que abren las instrucciones numeradas en 1B/2B/3B (contados en los PDFs).
_INSTRUCCION = re.compile(
    r"(?m)^\s*\d+\.\s+(encuentre|calcule|escriba|resuelva|identifique|complete|clasifique|determine"
    r"|exprese|represente|construya|convierta|dibuje|desarrolle|compare|ordene|responda|observe"
    r"|indique|simplifique|forme|factorice|relacione|grafique|trace|ubique|analice|reduzca|elabore|plantee)\b"
)


def v4(texto: str) -> bool:
    t = (texto or "").lower()
    if es_ejercicio_del_libro(texto):
        return True
    if _PASO.search(t) and "qué más necesitamos saber" not in t:
        return True
    return bool(_INSTRUCCION.search(t)) and "ejemplo" not in t


# V5 = V4 corregido tras medirlo: en Matemática "Paso 1." / "Paso 1:" es un
# procedimiento (teoría, también en 4to Primaria); en las Guías "Paso N" es una
# cabecera sin puntuación ("Paso 1 Comparamos…"). Y "¿Qué necesitamos saber?"
# (sin "más") también introduce teoría.
_PASO_GUIA = re.compile(r"\bpaso\s+\d+(?![\d.:])")


def v5(texto: str) -> bool:
    t = (texto or "").lower()
    if es_ejercicio_del_libro(texto):
        return True
    if _PASO_GUIA.search(t) and "necesitamos saber" not in t:
        return True
    return bool(_INSTRUCCION.search(t)) and "ejemplo" not in t


def simular_pdfs(rutas: list[str], variante=v5) -> None:
    """V4 sobre PDFs aún no ingestados: % de teoría antes/después, 3 ejemplos de
    fragmentos que pasarían a marcarse y ventanas de 5 páginas (≈ una lección)
    que se quedarían sin teoría."""
    import fitz

    from app.modules.ingesta.chunking import chunk_pages
    from app.modules.ingesta.pdf_processor import _extract_digital_text, _page_has_text
    from app.modules.lecciones.generator import PAGINAS_POR_LECCION

    for ruta in rutas:
        doc = fitz.open(ruta)
        paginas = [{"page_num": i + 1, "text": _extract_digital_text(p), "method": "digital", "confidence": 100.0}
                   for i, p in enumerate(doc) if _page_has_text(p)]
        chunks = chunk_pages(paginas, libro_id=0, asignatura="-", grado="-")
        antes = [not es_ejercicio_del_libro(c["text"]) for c in chunks]
        despues = [not variante(c["text"]) for c in chunks]
        n = len(chunks)
        print(f"\n== {ruta}: {n} fragmentos | teoría actual {100 * sum(antes) / n:.1f} % -> {variante.__name__.upper()} {100 * sum(despues) / n:.1f} %")
        nuevos = [c for c, a, d in zip(chunks, antes, despues) if a and not d]
        for c in nuevos[:: max(1, len(nuevos) // 3)][:3]:
            t = re.sub(r"\s+", " ", c["text"])
            print(f"   pasa a marcarse p{c['metadata']['page_num']}: {t[:260]}…")
        con_texto = sorted({c["metadata"]["page_num"] for c in chunks})
        ventanas = [con_texto[i:i + PAGINAS_POR_LECCION] for i in range(0, len(con_texto), PAGINAS_POR_LECCION)]
        sin_teoria = [f"{v[0]}-{v[-1]}" for v in ventanas
                      if not any(d for c, d in zip(chunks, despues) if c["metadata"]["page_num"] in v)]
        print(f"   ventanas de {PAGINAS_POR_LECCION} págs sin teoría con {variante.__name__.upper()}: {len(sin_teoria)}/{len(ventanas)} {sin_teoria}")
        sin_mas = [c for c in chunks if "qué necesitamos saber" in c["text"].lower()]
        for c in sin_mas[:: max(1, len(sin_mas) // 3)][:3]:
            t = re.sub(r"\s+", " ", c["text"])
            i = t.lower().find("qué necesitamos saber")
            print(f"   '¿Qué necesitamos saber?' p{c['metadata']['page_num']} ({variante.__name__.upper()} {'ejercicio' if variante(c['text']) else 'teoría'}): …{t[max(0, i - 10):i + 420]}…")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", nargs="+", help="PDFs sin ingestar: simula V4 sobre ellos y sobre el corpus de la BD")
    ap.add_argument("--variante", choices=["v4", "v5"], default="v5")
    args = ap.parse_args()
    if args.pdf:
        with create_engine(settings.database_url_sync).connect() as c:
            filas = c.execute(text(
                "select f.contenido_texto, l.titulo from fragmento f join libro_texto l on l.id = f.libro_id"
            )).all()
        variante = {"v4": v4, "v5": v5}[args.variante]
        print(f"Libros ya indexados ({args.variante.upper()} no debe cambiarlos):")
        for titulo in sorted({f.titulo for f in filas}):
            de = [f for f in filas if f.titulo == titulo]
            cambian = sum(es_ejercicio_del_libro(f.contenido_texto) != variante(f.contenido_texto) for f in de)
            print(f"   {titulo}: {len(de)} fragmentos, cambian {cambian}")
        simular_pdfs(args.pdf, variante)
        return
    with create_engine(settings.database_url_sync).connect() as c:
        filas = c.execute(text(
            "select f.id, f.libro_id, f.numero_pagina, f.contenido_texto, l.titulo "
            "from fragmento f join libro_texto l on l.id = f.libro_id order by f.id"
        )).all()
    print(f"Corpus: {len(filas)} fragmentos")
    actual = {f.id: es_ejercicio_del_libro(f.contenido_texto) for f in filas}
    print(f"Filtro actual marca como ejercicio: {sum(actual.values())}")
    for nombre, variante in (("V1", v1), ("V2", v2), ("V3", v3)):
        nuevo = {f.id: variante(f.contenido_texto) for f in filas}
        aceptados = [f for f in filas if actual[f.id] and not nuevo[f.id]]
        marcados = [f for f in filas if not actual[f.id] and nuevo[f.id]]
        print(f"\n== {nombre}: marca {sum(nuevo.values())} | pasan a ACEPTARSE {len(aceptados)} | pasan a MARCARSE {len(marcados)}")
        for titulo in sorted({f.titulo for f in filas}):
            a = sum(f.titulo == titulo for f in aceptados)
            m = sum(f.titulo == titulo for f in marcados)
            print(f"   {titulo}: +{a} aceptados, +{m} marcados")
        print("   aceptados:", [(f.id, f.numero_pagina) for f in aceptados])
        print("   marcados: ", [(f.id, f.numero_pagina) for f in marcados])
        for f in aceptados[:3] if nombre == "V3" else []:
            t = re.sub(r"\s+", " ", f.contenido_texto)
            i = t.lower().find("ejercicio")
            print(f"   ejemplo id={f.id} p{f.numero_pagina} ({f.titulo}): …{t[max(0, i - 160):i + 80]}…")
        for f in marcados[:3]:
            t = re.sub(r"\s+", " ", f.contenido_texto).lower()
            m = next(m for m in V1 if m in t)
            i = t.find(m)
            print(f"   nuevo marcado id={f.id} p{f.numero_pagina} por {m!r}: …{t[max(0, i - 60):i + 60]}…")

    lecciones_sin_teoria(filas)


def lecciones_sin_teoria(filas, variante=None):
    """Fragmentos de teoría que le quedan a cada lección de la ruta (los que
    usan micro-lección y actividades) con el filtro actual y con `variante`."""
    variante = variante or v2
    with create_engine(settings.database_url_sync).connect() as c:
        lecciones = c.execute(text(
            "select l.id, l.libro_id, l.orden, l.paginas, l.nombre from leccion l order by l.libro_id, l.orden"
        )).all()
    print("\n== Lecciones de la ruta (teoría disponible: actual -> variante)")
    for libro in sorted({l.libro_id for l in lecciones}):
        de_libro = [l for l in lecciones if l.libro_id == libro]
        vacias, pocas = [], []
        for l in de_libro:
            n = [int(x) for x in re.findall(r"\d+", l.paginas or "")]
            if not n:
                continue
            ini, fin = min(n), max(n)
            en_rango = [f for f in filas if f.libro_id == libro and f.numero_pagina is not None and ini <= f.numero_pagina <= fin]
            antes = sum(not es_ejercicio_del_libro(f.contenido_texto) for f in en_rango)
            despues = sum(not variante(f.contenido_texto) for f in en_rango)
            if despues == 0:
                vacias.append((l.orden, l.paginas, antes, despues, len(en_rango)))
            elif despues < 3:
                pocas.append((l.orden, l.paginas, antes, despues, len(en_rango)))
        print(f"   libro {libro}: {len(de_libro)} lecciones | SIN teoría: {len(vacias)} {vacias} | <3 frags: {len(pocas)} {pocas}")


if __name__ == "__main__":
    main()
