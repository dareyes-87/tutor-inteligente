"""Ranking del grado (gamificación), integración contra el servidor real (localhost:8000)."""
import uuid

import httpx
import pytest
from sqlalchemy import create_engine, text

from app.config import settings
from app.security import hash_password

BASE_URL = "http://localhost:8000"


@pytest.mark.asyncio
async def test_ranking_no_incluye_estudiantes_inactivos(token_estudiante):
    """Una cuenta desactivada (soft-delete) del grado de carlos no aparece en su ranking."""
    sufijo = uuid.uuid4().hex[:8]
    engine = create_engine(settings.database_url_sync)
    with engine.begin() as c:
        grado_id = c.execute(text("select grado_id from usuario where username = 'carlos'")).scalar()
        c.execute(text(
            "insert into usuario (nombre, apellido, username, password_hash, rol, grado_id, activo,"
            " puntos_totales, fecha_creacion)"
            " values ('Inactivo', :a, :u, :h, 'estudiante', :g, false, 9999, now())"
        ), {"a": f"Prueba{sufijo}", "u": f"inactivo_{sufijo}", "h": hash_password("x"), "g": grado_id})
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
            resp = await client.get("/gamificacion/ranking",
                                    headers={"Authorization": f"Bearer {token_estudiante}"})
        assert resp.status_code == 200
        apellidos = [e["apellido"] for e in resp.json()["ranking"]]
        assert f"Prueba{sufijo}" not in apellidos
        assert apellidos  # carlos (activo) sí está
    finally:
        with engine.begin() as c:
            c.execute(text("delete from usuario where username = :u"), {"u": f"inactivo_{sufijo}"})
