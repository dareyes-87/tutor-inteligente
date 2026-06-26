"""
Pruebas de INTEGRACIÓN de los endpoints, contra el servidor real
(http://localhost:8000). Requieren el backend levantado y datos sembrados
(usuarios carlos/maria, libro indexado con lecciones).

Las pruebas que llaman al LLM usan timeout de 30s.
"""
import httpx
import pytest

BASE_URL = "http://localhost:8000"
LLM_TIMEOUT = 30


# ----------------------- AUTH -----------------------

@pytest.mark.asyncio
async def test_login_estudiante():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.post(
            "/auth/login", data={"username": "carlos", "password": "carlos123"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("access_token")
    assert body.get("token_type")


@pytest.mark.asyncio
async def test_login_credenciales_invalidas():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.post(
            "/auth/login", data={"username": "carlos", "password": "incorrecta"}
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_con_token(token_estudiante):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token_estudiante}"}
        )
    assert resp.status_code == 200
    assert resp.json()["rol"] == "estudiante"


# ----------------------- CHAT / RAG -----------------------

@pytest.mark.asyncio
async def test_chat_pregunta_en_tema(token_estudiante):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=LLM_TIMEOUT) as client:
        resp = await client.post(
            "/chat/preguntar",
            headers={"Authorization": f"Bearer {token_estudiante}"},
            json={"pregunta": "¿qué es la célula?", "asignatura_id": 1, "conversacion_id": None},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["respuesta"].strip()
    assert isinstance(body["referencias"], list)


@pytest.mark.asyncio
async def test_chat_pregunta_fuera_tema(token_estudiante):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=LLM_TIMEOUT) as client:
        resp = await client.post(
            "/chat/preguntar",
            headers={"Authorization": f"Bearer {token_estudiante}"},
            json={"pregunta": "¿cuánto es 2+2?", "asignatura_id": 1, "conversacion_id": None},
        )
    assert resp.status_code == 200
    respuesta = resp.json()["respuesta"].lower()
    # El tutor rechaza temas fuera del libro con un mensaje fijo.
    assert any(p in respuesta for p in ("no encuentro", "libros", "libro de clase", "clase"))


# ----------------------- ACTIVIDADES -----------------------

@pytest.mark.asyncio
async def test_generar_actividad(token_estudiante):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=LLM_TIMEOUT) as client:
        resp = await client.post(
            "/actividades/generar",
            headers={"Authorization": f"Bearer {token_estudiante}"},
            json={"asignatura_id": 1, "tipo": "opcion_multiple"},
        )
    assert resp.status_code == 200
    contenido = resp.json()["contenido"]
    assert len(contenido.get("opciones", [])) >= 2


@pytest.mark.asyncio
async def test_actividades_sin_auth():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.post(
            "/actividades/generar",
            json={"asignatura_id": 1, "tipo": "opcion_multiple"},
        )
    assert resp.status_code == 401


# ----------------------- LECCIONES -----------------------

@pytest.mark.asyncio
async def test_mi_libro(token_estudiante):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get(
            "/lecciones/mi-libro", headers={"Authorization": f"Bearer {token_estudiante}"}
        )
    assert resp.status_code == 200
    assert resp.json().get("libro_id")


@pytest.mark.asyncio
async def test_ruta_aprendizaje(token_estudiante):
    headers = {"Authorization": f"Bearer {token_estudiante}"}
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        mi = (await client.get("/lecciones/mi-libro", headers=headers)).json()
        resp = await client.get(f"/lecciones/ruta?libro_id={mi['libro_id']}", headers=headers)
    assert resp.status_code == 200
    lecciones = resp.json()["lecciones"]
    assert len(lecciones) >= 1
    assert "nivel_actual" in lecciones[0]
    assert "nivel_completado" in lecciones[0]


@pytest.mark.asyncio
async def test_micro_leccion(token_estudiante):
    headers = {"Authorization": f"Bearer {token_estudiante}"}
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=LLM_TIMEOUT) as client:
        mi = (await client.get("/lecciones/mi-libro", headers=headers)).json()
        ruta = (await client.get(f"/lecciones/ruta?libro_id={mi['libro_id']}", headers=headers)).json()
        leccion_id = ruta["lecciones"][0]["id"]
        resp = await client.get(f"/lecciones/{leccion_id}/micro-leccion", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["tarjetas"]) >= 1


# ----------------------- DOCENTE -----------------------

@pytest.mark.asyncio
async def test_docente_estadisticas(token_docente):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get(
            "/docente/estadisticas", headers={"Authorization": f"Bearer {token_docente}"}
        )
    assert resp.status_code == 200
