"""
Pruebas de seguridad mínima.

- Unitarias (sin servidor): detección de secretos por defecto en producción.
- Integración (servidor real en localhost:8000): /auth/registro y /llm/hello.
"""
import httpx
import pytest

from app.config import Settings, secretos_inseguros

BASE_URL = "http://localhost:8000"

_DEFAULT_SECRET = Settings.model_fields["SECRET_KEY"].default
_DEFAULT_ADMIN = Settings.model_fields["ADMIN_PASSWORD"].default


# ----------------------- Unitarias -----------------------

def test_local_sin_database_url_no_exige_secretos():
    s = Settings(_env_file=None, DATABASE_URL="", SECRET_KEY=_DEFAULT_SECRET, ADMIN_PASSWORD=_DEFAULT_ADMIN)
    assert secretos_inseguros(s) == []


def test_produccion_con_defaults_reporta_ambas_variables():
    s = Settings(_env_file=None, DATABASE_URL="postgres://x", SECRET_KEY=_DEFAULT_SECRET, ADMIN_PASSWORD=_DEFAULT_ADMIN)
    assert secretos_inseguros(s) == ["SECRET_KEY", "ADMIN_PASSWORD"]


def test_produccion_con_secreto_vacio_lo_reporta():
    s = Settings(_env_file=None, DATABASE_URL="postgres://x", SECRET_KEY="", ADMIN_PASSWORD="otra-clave-propia")
    assert secretos_inseguros(s) == ["SECRET_KEY"]


def test_produccion_con_valores_propios_es_valida():
    s = Settings(_env_file=None, DATABASE_URL="postgres://x", SECRET_KEY="clave-propia-larga", ADMIN_PASSWORD="otra-clave-propia")
    assert secretos_inseguros(s) == []


# ----------------------- Integración -----------------------

@pytest.mark.asyncio
async def test_docente_no_puede_registrar_administrador(token_docente):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.post(
            "/auth/registro",
            headers={"Authorization": f"Bearer {token_docente}"},
            json={
                "nombre": "Intento", "apellido": "Escalada", "username": "intento_admin_test",
                "password": "clave123456", "rol": "administrador",
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_llm_hello_sin_token_401():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get("/llm/hello")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_llm_hello_estudiante_403(token_estudiante):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get("/llm/hello", headers={"Authorization": f"Bearer {token_estudiante}"})
    assert resp.status_code == 403
