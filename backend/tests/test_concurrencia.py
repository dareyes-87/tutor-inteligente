"""
Prueba de INTEGRACIÓN de concurrencia: con uvicorn --workers 1, una llamada
bloqueante (LLM, embedding, Chroma) dentro de una corutina congela el event
loop para todos. Mientras una micro-lección y una pregunta de chat están en
curso, /health debe seguir respondiendo rápido.

Requiere el backend levantado (ver conftest.py).
"""
import asyncio
import time

import httpx
import pytest

BASE_URL = "http://localhost:8000"
LLM_TIMEOUT = 120
MAX_SEGUNDOS_HEALTH = 1.0


@pytest.mark.asyncio
async def test_health_responde_durante_llamadas_largas(token_estudiante):
    headers = {"Authorization": f"Bearer {token_estudiante}"}
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=LLM_TIMEOUT) as client:
        mi = (await client.get("/lecciones/mi-libro", headers=headers)).json()
        ruta = (await client.get(f"/lecciones/ruta?libro_id={mi['libro_id']}", headers=headers)).json()
        leccion_id = ruta["lecciones"][0]["id"]
        mis_libros = (await client.get("/lecciones/mis-libros", headers=headers)).json()
        asignatura_id = mis_libros[0]["asignatura_id"]

        largas = [
            asyncio.create_task(
                client.get(f"/lecciones/{leccion_id}/micro-leccion?nivel=1", headers=headers)
            ),
            asyncio.create_task(
                client.post(
                    "/chat/preguntar",
                    headers=headers,
                    json={"pregunta": "¿Qué es la célula?", "asignatura_id": asignatura_id},
                )
            ),
        ]
        await asyncio.sleep(1.5)  # dar tiempo a que ambas entren al LLM/RAG

        tiempos = []
        for _ in range(5):
            if all(t.done() for t in largas):
                break
            inicio = time.monotonic()
            resp = await client.get("/health")
            tiempos.append(time.monotonic() - inicio)
            assert resp.status_code == 200
            await asyncio.sleep(0.5)

        resultados = await asyncio.gather(*largas)

    assert tiempos, "las llamadas largas terminaron antes de medir /health"
    assert max(tiempos) < MAX_SEGUNDOS_HEALTH, f"/health tardó {max(tiempos):.2f}s: event loop bloqueado"
    assert all(r.status_code == 200 for r in resultados)
