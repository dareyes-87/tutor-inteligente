"""
Chat: rangos de páginas ("resume desde la página 40 a la 45").

Detección y armado de la respuesta son unitarias (LLM simulado); las de recuperación usan Chroma +
embeddings con el libro de Ciencias Naturales 9no Básico (corren dentro del contenedor) y la de
integración llama además al LLM real. En ese libro las páginas 1–11 no tienen fragmentos.
"""
import asyncio
import re
import time

import pytest

from app.modules.chat import service
from app.modules.chat.service import (
    MAX_PAGINAS_RANGO, NO_SE_PUDO_RESUMIR, _citas_validas, _detectar_paginas,
    _resumir_rango, recuperar_contexto,
)
from app.modules.rag.search import TOP_K, is_context_relevant

CIENCIAS_9NO = ("Ciencias Naturales", "9no Básico")


def _f(pagina, texto):
    return {"page_num": pagina, "libro_id": 14, "text": texto}


def _secciones(respuesta: str) -> dict[int, str]:
    """'Página N: …' -> {N: texto de la sección}."""
    partes = re.split(r"(?m)^Página (\d+): ", respuesta)
    return {int(n): t for n, t in zip(partes[1::2], partes[2::2])}


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


# --- Resumen por página (LLM simulado) ---------------------------------------------------------

@pytest.fixture
def llm_falso(monkeypatch):
    """Sustituye llm_client.chat: registra cada llamada y responde 'resumen de la N'."""
    llamadas = []

    def chat(messages, max_tokens=1024, temperature=0.7, rol="chat"):
        contexto = messages[0]["content"]
        paginas = sorted({int(p) for p in re.findall(r"--- Página (\d+) ---", contexto)})
        llamadas.append({"paginas": paginas, "temperature": temperature})
        time.sleep(0.3)
        if paginas == [13]:
            raise RuntimeError("Together caído")
        return f"Página {paginas[0]}: resumen de la {paginas[0]}."  # el título se quita

    monkeypatch.setattr(service.llm_client, "chat", chat)
    return llamadas


@pytest.mark.asyncio
async def test_una_llamada_por_pagina_en_paralelo_y_en_orden(llm_falso):
    frags = [_f(40, "a"), _f(41, "b"), _f(40, "c"), _f(42, "d")]
    t0 = time.monotonic()
    resp = await _resumir_rango([40, 41, 42], frags, "9no Básico", "Ciencias Naturales", 3)
    assert time.monotonic() - t0 < 0.6  # 3 × 0.3 s en serie serían 0.9 s
    assert sorted(c["paginas"] for c in llm_falso) == [[40], [41], [42]]  # cada una solo con la suya
    assert all(c["temperature"] <= 0.2 for c in llm_falso)
    assert resp == "Página 40: resumen de la 40.\n\nPágina 41: resumen de la 41.\n\nPágina 42: resumen de la 42."


@pytest.mark.asyncio
async def test_pagina_vacia_sin_llm_y_pagina_fallida_no_tumba_el_resto(llm_falso):
    resp = await _resumir_rango([11, 12, 13], [_f(12, "x"), _f(13, "y")], "9no Básico", "Ciencias Naturales", 3)
    assert [c["paginas"] for c in llm_falso if c["paginas"] == [11]] == []
    assert _secciones(resp) == {11: "sin contenido en tu libro.\n\n", 12: "resumen de la 12.\n\n",
                                13: NO_SE_PUDO_RESUMIR}
    # "Página 11" no tiene fragmentos pero citarla es válido (no se borra como cita inventada).
    assert _citas_validas(resp, [_f(12, "x"), _f(13, "y"), {"page_num": 11}])


@pytest.mark.asyncio
async def test_rango_de_mas_de_6_lo_dice_en_una_linea(llm_falso):
    pregunta = "resume las páginas 40 a 50"
    paginas = _detectar_paginas(pregunta)[:MAX_PAGINAS_RANGO]
    resp = await _resumir_rango(paginas, [_f(p, "t") for p in paginas], None, None, len(_detectar_paginas(pregunta)))
    assert resp.startswith("Pediste 11 páginas; resumo solo las primeras 6 (de la 40 a la 45).\n\nPágina 40:")
    assert len(llm_falso) == 6


# --- Recuperación (Chroma real) -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_rango_normal_trae_todas_las_paginas_en_orden():
    ctx, por_pagina, paginas = await recuperar_contexto("resume desde la página 40 a la 45", *CIENCIAS_9NO)
    assert por_pagina and paginas == list(range(40, 46))
    assert {f["page_num"] for f in ctx} == set(range(40, 46))
    assert [f["page_num"] for f in ctx] == sorted(f["page_num"] for f in ctx)
    assert len(ctx) > TOP_K  # no se recorta al top-5 de la búsqueda semántica


@pytest.mark.asyncio
async def test_rango_de_mas_de_6_recupera_solo_las_primeras_6():
    ctx, _, paginas = await recuperar_contexto("resume las páginas 40 a 50", *CIENCIAS_9NO)
    assert paginas == list(range(40, 40 + MAX_PAGINAS_RANGO))
    assert {f["page_num"] for f in ctx} == set(paginas)


@pytest.mark.asyncio
async def test_rango_con_pagina_vacia():
    ctx, por_pagina, paginas = await recuperar_contexto("resume de la página 11 a la 13", *CIENCIAS_9NO)
    assert por_pagina and paginas == [11, 12, 13]
    assert {f["page_num"] for f in ctx} == {12, 13}


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


# --- Integración con el LLM real ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_resumen_40_45_cada_pagina_solo_con_lo_suyo():
    """Prod (rango en una sola llamada): lo de la 42 aparecía bajo la 41 y lo de la 44 bajo la 43."""
    pregunta = "resume desde la página 40 a la 45"
    ctx, _, paginas = await recuperar_contexto(pregunta, *CIENCIAS_9NO)
    t0 = time.monotonic()
    resp = await _resumir_rango(paginas, ctx, *reversed(CIENCIAS_9NO), len(paginas))
    assert time.monotonic() - t0 < 15
    secciones = _secciones(resp)
    assert list(secciones) == paginas and all(NO_SE_PUDO_RESUMIR not in t for t in secciones.values())
    # Términos distintivos y las únicas páginas del rango donde están en el libro (consultado en la
    # BD). Una comparación palabra por palabra no sirve: marca paráfrasis ("investigar" por
    # "investigamos", "población" por "nacimientos por cada 1000 habitantes").
    terminos = {
        "agenda 2030": {40}, "milenio": {40}, "haití": {41}, "japón": {41}, "alemania": {41},
        "saludable": {42}, "ecnt": {42}, "acróstico": {42}, "diabetes": {42},
        "encuesta mundial": {43}, "parkinson": {44}, "epilepsia": {44, 45}, "alzheimer": {44, 45},
        "meningitis": {44, 45}, "demencia": {44, 45}, "47.5": {45}, "oms": {40, 45},
        "sobrepeso": {42, 43},
    }
    tiene = lambda texto, termino: re.search(rf"\b{re.escape(termino)}\b", texto.lower())  # noqa: E731
    for termino, propias in terminos.items():
        donde = {p for p, t in secciones.items() if tiene(t, termino)}
        assert donde <= propias, f"'{termino}' en {donde}, solo está en {propias}\n{resp}"
    # Y cada página se reconoce por lo suyo (si no, el chequeo de arriba pasaría con resúmenes vacíos).
    for p in paginas:
        assert any(tiene(secciones[p], t) for t, propias in terminos.items() if p in propias), \
            f"Página {p} sin sus términos\n{resp}"
