"""
Panel docente (Fase 2), integración contra el servidor real (localhost:8000).
BD local: libros 3 (Ciencias 4to) y 4 (Matemáticas 4to), ambos escaneados (OCR).
"""
import httpx
import pytest

BASE_URL = "http://localhost:8000"


@pytest.mark.asyncio
async def test_libros_incluyen_metodo_y_confianza_ocr(token_docente):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get("/docente/libros", headers={"Authorization": f"Bearer {token_docente}"})
    assert resp.status_code == 200
    libros = resp.json()
    assert libros
    for libro in libros:
        assert libro["metodo"] in ("digital", "ocr", "mixto", None)
        assert "confianza_ocr_promedio" in libro
    escaneados = [l for l in libros if l["metodo"] == "ocr"]
    assert escaneados and all(0 < l["confianza_ocr_promedio"] <= 100 for l in escaneados)


# ----------------------- Diagnóstico (mapa de calor) -----------------------

import uuid  # noqa: E402

from sqlalchemy import create_engine, text  # noqa: E402

from app.config import settings  # noqa: E402
from app.models.leccion import Leccion  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402
from app.modules.docente.service import construir_matriz  # noqa: E402
from app.security import hash_password  # noqa: E402


def test_construir_matriz_clasifica_y_marca_sin_datos():
    estudiantes = [Usuario(id=1, nombre="Ana", apellido="López"), Usuario(id=2, nombre="Beto", apellido="Paz")]
    lecciones = [Leccion(id=10, orden=1, nombre="L1"), Leccion(id=11, orden=2, nombre="L2")]
    agregados = {(1, 10): (85.0, 3), (1, 11): (50.0, 2), (2, 10): (49.9, 1)}
    filas = construir_matriz(estudiantes, lecciones, agregados)
    assert [[c.nivel for c in f.celdas] for f in filas] == [
        ["domina", "en_proceso"],
        ["refuerzo", "sin_datos"],
    ]
    assert filas[1].celdas[1].puntaje_promedio is None and filas[1].celdas[1].total_actividades == 0


@pytest.mark.asyncio
async def test_diagnostico_forma_de_la_matriz(token_docente):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.get(
            "/docente/diagnostico?asignatura_id=1", headers={"Authorization": f"Bearer {token_docente}"}
        )
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["asignatura_id"] == 1 and d["lecciones"] and d["estudiantes"]
    ids = [l["id"] for l in d["lecciones"]]
    for fila in d["estudiantes"]:
        assert [c["leccion_id"] for c in fila["celdas"]] == ids
        assert all(c["nivel"] in ("domina", "en_proceso", "refuerzo", "sin_datos") for c in fila["celdas"])


@pytest.mark.asyncio
async def test_diagnostico_docente_de_otro_grado_no_ve_el_libro():
    """Un docente de un grado sin libros no ve el libro del grado 1 (404)."""
    sufijo = uuid.uuid4().hex[:8]
    engine = create_engine(settings.database_url_sync)
    with engine.begin() as c:
        grado_id = c.execute(text(
            "insert into grado (nombre, nivel) values (:n, 'primaria') returning id"
        ), {"n": f"9no Prueba {sufijo}"}).scalar()
        c.execute(text(
            "insert into usuario (nombre, apellido, username, password_hash, rol, grado_id, activo, fecha_creacion)"
            " values ('Doc', 'Prueba', :u, :h, 'docente', :g, true, now())"
        ), {"u": f"doc_{sufijo}", "h": hash_password("clave-prueba-123"), "g": grado_id})
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
            login = await client.post("/auth/login", data={"username": f"doc_{sufijo}", "password": "clave-prueba-123"})
            token = login.json()["access_token"]
            resp = await client.get("/docente/diagnostico?libro_id=3", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404
    finally:
        with engine.begin() as c:
            c.execute(text("delete from usuario where username = :u"), {"u": f"doc_{sufijo}"})
            c.execute(text("delete from grado where id = :g"), {"g": grado_id})
