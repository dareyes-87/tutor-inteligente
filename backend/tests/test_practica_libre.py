"""
Práctica libre / repaso (página Actividades): una actividad de CUALQUIER lección del
libro, incluso bloqueada en la ruta. Integración contra el servidor real (localhost:8000).

Debe: llevar leccion_id y fragmentos_fuente_ids del rango de la lección, contar para el
perfil de comprensión y el mapa de calor, y NO tocar la ruta (estado, niveles, desbloqueos).
"""
import httpx
import pytest
from sqlalchemy import create_engine, text

from app.config import settings

BASE_URL = "http://localhost:8000"
LLM_TIMEOUT = 90


def _estado_ruta(ruta: dict) -> list[tuple]:
    return [(l["id"], l["estado"], l["nivel_actual"], l["nivel_completado"]) for l in ruta["lecciones"]]


@pytest.mark.asyncio
async def test_practica_libre_en_leccion_bloqueada_no_toca_la_ruta(token_estudiante, token_docente):
    h_est = {"Authorization": f"Bearer {token_estudiante}"}
    h_doc = {"Authorization": f"Bearer {token_docente}"}
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=LLM_TIMEOUT) as client:
        libro = (await client.get("/lecciones/mis-libros", headers=h_est)).json()[0]
        ruta = (await client.get(f"/lecciones/ruta?libro_id={libro['libro_id']}", headers=h_est)).json()
        leccion = next(l for l in ruta["lecciones"] if l["estado"] == "bloqueada")
        antes = _estado_ruta(ruta)
        perfil_antes = {p["tema"]: p["total_actividades"]
                        for p in (await client.get("/actividades/perfil", headers=h_est)).json()}

        resp = await client.post("/actividades/generar", headers=h_est, json={
            "asignatura_id": libro["asignatura_id"], "tipo": "verdadero_falso", "leccion_id": leccion["id"],
        })
        assert resp.status_code == 200, resp.text
        act = resp.json()
        resp = await client.post("/actividades/responder", headers=h_est,
                                 json={"actividad_id": act["id"], "respuesta": {"respuesta": True}})
        assert resp.status_code == 200, resp.text

        # La ruta no cambió: la lección sigue bloqueada y ningún nivel se movió.
        despues = (await client.get(f"/lecciones/ruta?libro_id={libro['libro_id']}", headers=h_est)).json()
        assert _estado_ruta(despues) == antes

        # Cuenta para el perfil de comprensión (tema de la lección).
        perfil = {p["tema"]: p["total_actividades"]
                  for p in (await client.get("/actividades/perfil", headers=h_est)).json()}
        assert perfil[act["tema"]] == perfil_antes.get(act["tema"], 0) + 1

        # Y para el mapa de calor del docente, en la celda de esa lección.
        diag = (await client.get(f"/docente/diagnostico?libro_id={libro['libro_id']}", headers=h_doc)).json()
        me = (await client.get("/auth/me", headers=h_est)).json()
        fila = next(f for f in diag["estudiantes"] if f["estudiante_id"] == me["id"])
        celda = next(c for c in fila["celdas"] if c["leccion_id"] == leccion["id"])
        assert celda["total_actividades"] >= 1 and celda["nivel"] != "sin_datos"

    # En la BD: leccion_id y fragmentos fuente dentro de las páginas de la lección.
    with create_engine(settings.database_url_sync).connect() as c:
        leccion_id, fragmentos = c.execute(text(
            "select leccion_id, fragmentos_fuente_ids from actividad where id = :i"), {"i": act["id"]}).one()
        assert leccion_id == leccion["id"]
        assert fragmentos
        libros = c.execute(text("select distinct libro_id from fragmento where id = any(:ids)"),
                           {"ids": fragmentos}).scalars().all()
        assert libros == [libro["libro_id"]]


@pytest.mark.asyncio
async def test_practica_libre_rechaza_leccion_de_otro_grado(token_estudiante):
    h = {"Authorization": f"Bearer {token_estudiante}"}
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        propios = {l["libro_id"] for l in (await client.get("/lecciones/mis-libros", headers=h)).json()}
    with create_engine(settings.database_url_sync).connect() as c:
        ajena, asignatura = c.execute(text(
            "select l.id, b.asignatura_id from leccion l join libro_texto b on b.id = l.libro_id"
            " where b.id <> all(:p) limit 1"), {"p": list(propios)}).one()
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        resp = await client.post("/actividades/generar", headers=h, json={
            "asignatura_id": asignatura, "tipo": "verdadero_falso", "leccion_id": ajena,
        })
    assert resp.status_code == 404
