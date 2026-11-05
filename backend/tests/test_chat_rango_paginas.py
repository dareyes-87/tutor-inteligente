"""
Chat: rangos de páginas ("resume desde la página 40 a la 45").

Detección y armado de la respuesta son unitarias; las de recuperación usan Chroma + embeddings
con el libro de Ciencias Naturales 9no Básico (corren dentro del contenedor). En ese libro las
páginas 1–11 no tienen fragmentos y la 40 tiene 5.
"""
import pytest

from app.modules.chat.service import (
    MAX_PAGINAS_RANGO, _citas_validas, _completar_rango, _detectar_paginas, recuperar_contexto,
)
from app.modules.rag.search import TOP_K, is_context_relevant

CIENCIAS_9NO = ("Ciencias Naturales", "9no Básico")


@pytest.mark.parametrize("texto, esperado", [
    ("resume desde la página 40 a la 45", list(range(40, 46))),
    ("páginas 40 a 45", list(range(40, 46))),
    ("de la 40 a la 45", list(range(40, 46))),
    ("págs 40-45", list(range(40, 46))),
    ("página 40 hasta la página 45", list(range(40, 46))),
    ("páginas 40 y 41", [40, 41]),
    ("explícame la página 12", [12]),
    ("cuánto es 40-45", []),          # resta, no páginas
    ("¿qué es la fotosíntesis?", []),
])
def test_detecta_rangos_pares_y_una_pagina(texto, esperado):
    assert _detectar_paginas(texto) == esperado


@pytest.mark.asyncio
async def test_rango_normal_trae_todas_las_paginas_en_orden():
    ctx, por_pagina, paginas = await recuperar_contexto("resume desde la página 40 a la 45", *CIENCIAS_9NO)
    assert por_pagina and paginas == list(range(40, 46))
    assert {f["page_num"] for f in ctx} == set(range(40, 46))
    assert [f["page_num"] for f in ctx] == sorted(f["page_num"] for f in ctx)
    assert len(ctx) > TOP_K  # no se recorta al top-5 de la búsqueda semántica


@pytest.mark.asyncio
async def test_rango_de_mas_de_6_usa_las_primeras_6_y_lo_dice():
    pregunta = "resume las páginas 40 a 50"
    ctx, _, paginas = await recuperar_contexto(pregunta, *CIENCIAS_9NO)
    assert paginas == list(range(40, 40 + MAX_PAGINAS_RANGO))
    assert {f["page_num"] for f in ctx} == set(paginas)
    resp = _completar_rango("Página 40: …", len(_detectar_paginas(pregunta)), paginas, [])
    assert resp.startswith("Pediste 11 páginas; resumo solo las primeras 6 (de la 40 a la 45).")
    assert _citas_validas(resp, ctx)  # la línea inicial no cuenta como cita


@pytest.mark.asyncio
async def test_rango_con_pagina_vacia_la_marca_sin_contenido():
    ctx, por_pagina, paginas = await recuperar_contexto("resume de la página 11 a la 13", *CIENCIAS_9NO)
    assert por_pagina and paginas == [11, 12, 13]
    assert {f["page_num"] for f in ctx} == {12, 13}
    # El LLM la omitió: se añade.
    assert _completar_rango("Página 12: …\n\nPágina 13: …", 3, paginas, [11]).endswith(
        "Página 11: sin contenido en tu libro.")
    # El LLM ya la dijo: no se repite, y citarla es válido (no se borra como cita inventada).
    ya = "Página 11: sin contenido en tu libro.\n\nPágina 12: …"
    assert _completar_rango(ya, 3, paginas, [11]) == ya
    assert _citas_validas(ya, ctx + [{"page_num": 11}])


@pytest.mark.asyncio
async def test_una_sola_pagina_no_cambia():
    ctx, por_pagina, paginas = await recuperar_contexto("explícame la página 40", *CIENCIAS_9NO)
    assert por_pagina and paginas == [40]
    assert 0 < len(ctx) <= TOP_K and {f["page_num"] for f in ctx} == {40}


@pytest.mark.asyncio
async def test_pregunta_sin_pagina_sigue_siendo_semantica():
    ctx, por_pagina, paginas = await recuperar_contexto("¿Qué es la simbiosis?", *CIENCIAS_9NO)
    assert not por_pagina and paginas == []
    assert 0 < len(ctx) <= TOP_K and is_context_relevant(ctx)
