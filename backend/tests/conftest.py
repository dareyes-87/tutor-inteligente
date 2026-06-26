"""
Fixtures para las pruebas de integración.

Las pruebas corren CONTRA EL SERVIDOR REAL (http://localhost:8000), así que el
backend debe estar levantado (docker compose up) antes de ejecutarlas.
"""
import httpx
import pytest
import pytest_asyncio

BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


async def _login(username: str, password: str) -> str:
    """Hace login (OAuth2 form-urlencoded) y devuelve el access_token."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.post(
            "/auth/login",
            data={"username": username, "password": password},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


@pytest_asyncio.fixture
async def token_estudiante() -> str:
    """Token de un estudiante (carlos)."""
    return await _login("carlos", "carlos123")


@pytest_asyncio.fixture
async def token_docente() -> str:
    """Token de una docente (maria)."""
    return await _login("maria", "maria123")
