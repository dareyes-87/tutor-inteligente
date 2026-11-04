"""
Chat: recuperación, páginas usadas, pie "📖 Basado en tu libro…", título del libro en las fuentes,
lección para "🎯 Pon a prueba lo que aprendiste" e historial de conversaciones.

Las unitarias no necesitan servidor; la de recuperación usa Chroma + embeddings (corre dentro del
contenedor) y las de integración van contra el servidor real con la cuenta de pruebas (carlos).
"""
import httpx
import pytest

from app.modules.chat.service import _fragmentos_usados, recuperar_contexto
from app.modules.rag.search import is_context_relevant

BASE_URL = "http://localhost:8000"
LLM_TIMEOUT = 90
PIE = "📖 Basado en tu libro de "


def _f(pagina, texto):
    return {"page_num": pagina, "libro_id": 1, "text": texto}


def test_usados_son_las_paginas_citadas():
    fr = [_f(10, "fotosíntesis plantas clorofila"), _f(20, "fotosíntesis energía luz"), _f(30, "volcanes")]
    usados = _fragmentos_usados("La fotosíntesis usa la luz (página 20).", fr)
    assert [f["page_num"] for f in usados] == [20]


def test_sin_citas_usa_los_que_comparten_vocabulario():
    fr = [_f(5, "sistema digestivo estomago intestino"), _f(6, "volcanes lava magma"),
          _f(7, "digestivo estomago boca saliva intestino")]
    usados = _fragmentos_usados("El sistema digestivo: la boca, el estómago y el intestino.", fr)
    assert {f["page_num"] for f in usados} == {5, 7}


def test_sin_solape_queda_el_mejor_y_sin_fragmentos_nada():
    fr = [_f(1, "uno dos"), _f(2, "tres cuatro")]
    assert len(_fragmentos_usados("Respuesta sin relación", fr)) == 1
    assert _fragmentos_usados("Lo que sea", []) == []


@pytest.mark.asyncio
async def test_simbiosis_9no_recupera_la_definicion():
    # Antes, "Paso 4 … ¿Qué necesito saber?" se filtraba como ejercicio y el tutor decía que
    # el libro no define la simbiosis, aunque "¿Qué es el mutualismo?" sí encontraba p. 114-115.
    ctx, _, _ = await recuperar_contexto("¿Qué es la simbiosis y qué tipos hay?", "Ciencias Naturales", "9no Básico")
    assert is_context_relevant(ctx)
    assert any(f["page_num"] == 115 and "Simbiosis: relación estrecha" in " ".join(f["text"].split())
               for f in ctx)


@pytest.mark.asyncio
async def test_respuesta_con_fragmentos_lleva_pie_titulo_y_leccion(token_estudiante):
    h = {"Authorization": f"Bearer {token_estudiante}"}
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=LLM_TIMEOUT) as client:
        r = await client.post("/chat/preguntar", headers=h, json={
            "pregunta": "¿Qué es la célula?", "asignatura_id": 1, "conversacion_id": None})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["referencias"], body["respuesta"]
        # Toda respuesta con fragmentos lleva el pie, con las mismas páginas que las fuentes.
        pie = body["respuesta"][body["respuesta"].index(PIE):]
        assert all(str(ref["page_num"]) in pie for ref in body["referencias"])
        assert all(ref["libro_titulo"] for ref in body["referencias"])
        assert body["leccion"] and body["leccion"]["id"]

        # El historial lista la conversación y la devuelve con las mismas fuentes.
        convs = (await client.get("/chat/conversaciones", headers=h)).json()
        assert convs[0]["id"] == body["conversacion_id"]
        conv = (await client.get(f"/chat/conversaciones/{body['conversacion_id']}", headers=h)).json()
        tutor = [m for m in conv["mensajes"] if m["rol"] == "asistente"][-1]
        assert tutor["referencias"]["leccion"] == body["leccion"]
        assert all(ref["libro_titulo"] for ref in tutor["referencias"]["fragmentos"])


@pytest.mark.asyncio
async def test_rechazo_no_lleva_pie(token_estudiante):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=LLM_TIMEOUT) as client:
        r = await client.post("/chat/preguntar", headers={"Authorization": f"Bearer {token_estudiante}"},
                              json={"pregunta": "¿Quién ganó el mundial de fútbol de 2014?", "asignatura_id": 1})
    body = r.json()
    assert body["referencias"] == [] and PIE not in body["respuesta"] and body["leccion"] is None
