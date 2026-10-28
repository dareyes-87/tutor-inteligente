"""
Simula cambios al filtro de ejercicios (rag/search.py::es_ejercicio_del_libro)
contra TODOS los fragmentos de la BD local, sin tocar el código de la app.

Variantes (frente al filtro actual). NOTA: V2 se aplicó en rag/search.py
(2026-10-28); desde entonces "actual" ya es V2 y las variantes no cambian nada.
  V1  quitar el marcador suelto "ejercicio" (en este corpus solo coincide con
      notas al docente —"propóngales un ejercicio"— o con "hacer ejercicio"
      físico, que es teoría de Ciencias).
  V2  V1 + normalizar espacios/saltos de línea antes de buscar marcadores (el
      OCR parte frases como "Ahora es tu\\nturno" y el filtro actual no las ve).
  V3  propuesta acotada: V1, pero un fragmento que hoy solo marca "ejercicio"
      SIGUE marcado si, normalizando espacios, contiene otro marcador (es decir,
      sí trae un ejercicio real partido por el OCR). No marca nada nuevo.

Uso (dentro del contenedor):
    docker compose exec backend python scripts/debug/simular_filtro_ejercicio.py
"""
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


def main():
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
