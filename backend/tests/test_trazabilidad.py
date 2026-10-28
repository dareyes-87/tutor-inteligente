"""
Trazabilidad actividad -> libro (Fase 2): leccion_id y fragmentos_fuente_ids.

Integración contra el servidor real (localhost:8000) + lectura directa de la
fila en Postgres (las pruebas corren dentro del contenedor del backend).
Lección 183 = Ciencias 4to, "Alimentación Saludable" (BD local).
"""
import httpx
import pytest
from sqlalchemy import create_engine, text

from app.config import settings

BASE_URL = "http://localhost:8000"
LLM_TIMEOUT = 60
LECCION_CIENCIAS = 183


def _fila(actividad_id: int):
    with create_engine(settings.database_url_sync).connect() as c:
        return c.execute(
            text("select leccion_id, fragmentos_fuente_ids from actividad where id = :id"),
            {"id": actividad_id},
        ).one()


def _fragmentos_existen(ids: list[int]) -> bool:
    with create_engine(settings.database_url_sync).connect() as c:
        n = c.execute(text("select count(*) from fragmento where id = any(:ids)"), {"ids": ids}).scalar()
    return n == len(ids)


async def _generar(token: str, **body) -> dict:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=LLM_TIMEOUT) as client:
        resp = await client.post(
            "/actividades/generar",
            json={"asignatura_id": 1, "tipo": "verdadero_falso", **body},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_actividad_desde_leccion_guarda_leccion_y_fragmentos(token_estudiante):
    act = await _generar(token_estudiante, leccion_id=LECCION_CIENCIAS)
    leccion_id, fragmentos = _fila(act["id"])
    assert leccion_id == LECCION_CIENCIAS
    assert fragmentos and _fragmentos_existen(fragmentos)


@pytest.mark.asyncio
async def test_actividad_por_busqueda_guarda_fragmentos_sin_leccion(token_estudiante):
    act = await _generar(token_estudiante, tema="la célula")
    leccion_id, fragmentos = _fila(act["id"])
    assert leccion_id is None
    assert fragmentos and _fragmentos_existen(fragmentos)
