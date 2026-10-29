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


@pytest.mark.asyncio
async def test_racha_caducada_se_ve_en_cero_en_ranking_y_panel_docente(token_estudiante, token_docente):
    """Racha guardada de 4 con última actividad hace 5 días: ranking y panel docente muestran 0;
    con última actividad hoy, 4. (La BD no cambia al leer.)"""
    sufijo = uuid.uuid4().hex[:8]
    engine = create_engine(settings.database_url_sync)
    with engine.begin() as c:
        grado_id = c.execute(text("select grado_id from usuario where username = 'carlos'")).scalar()
        ids = {}
        for nombre, dias in (("Caducada", 5), ("Vigente", 0)):
            ids[nombre] = c.execute(text(
                "insert into usuario (nombre, apellido, username, password_hash, rol, grado_id, activo,"
                " racha_actual, mejor_racha, ultima_actividad, fecha_creacion)"
                " values (:n, :a, :u, :h, 'estudiante', :g, true, 4, 4,"
                " (now() at time zone 'America/Guatemala')::date - :d, now()) returning id"
            ), {"n": nombre, "a": f"Racha{sufijo}", "u": f"racha_{nombre.lower()}_{sufijo}", "h": hash_password("x"),
                "g": grado_id, "d": dias}).scalar()
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
            ranking = (await client.get("/gamificacion/ranking",
                                        headers={"Authorization": f"Bearer {token_estudiante}"})).json()["ranking"]
            docente = {"Authorization": f"Bearer {token_docente}"}
            lista = (await client.get("/docente/estudiantes", headers=docente)).json()
            detalle = {n: (await client.get(f"/docente/estudiantes/{i}/detalle", headers=docente)).json()
                       for n, i in ids.items()}
        en_ranking = {e["nombre"]: e["racha_actual"] for e in ranking if e["apellido"] == f"Racha{sufijo}"}
        en_lista = {e["nombre"]: e["racha_actual"] for e in lista if e["apellido"] == f"Racha{sufijo}"}
        assert en_ranking == en_lista == {"Caducada": 0, "Vigente": 4}
        assert detalle["Caducada"]["racha_actual"] == 0 and detalle["Vigente"]["racha_actual"] == 4
        with engine.begin() as c:
            assert c.execute(text("select racha_actual from usuario where id = :i"), {"i": ids["Caducada"]}).scalar() == 4
    finally:
        with engine.begin() as c:  # el detalle docente crea progreso (obtener_ruta)
            c.execute(text("delete from progreso_leccion where estudiante_id = any(:i)"), {"i": list(ids.values())})
            c.execute(text("delete from usuario where id = any(:i)"), {"i": list(ids.values())})
