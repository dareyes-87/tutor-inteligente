"""
Punto de entrada de la API del Tutor Inteligente.

Endpoints del Sprint 0:
  GET /health     -> verifica que la API, PostgreSQL y ChromaDB estén vivos.
  GET /llm/hello  -> prueba la conexión con Together AI (modelo base).
  GET /docs       -> documentación interactiva automática (la da FastAPI).
"""
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.llm.client import llm_client

app = FastAPI(title="Tutor Inteligente API", version="0.1.0")

# CORS: por ahora permitimos el front web en desarrollo (Next.js en :3000).
# En el Sprint 3 se ajusta a los dominios reales de producción.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _check_postgres() -> str:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}"


async def _check_chroma() -> str:
    url = f"http://{settings.CHROMA_HOST}:{settings.CHROMA_PORT}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            # ChromaDB cambió de /api/v1 a /api/v2 según versión; probamos ambos.
            for path in ("/api/v2/heartbeat", "/api/v1/heartbeat"):
                r = await client.get(url + path)
                if r.status_code == 200:
                    return "ok"
        return "down"
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}"


@app.get("/health")
async def health():
    postgres = await _check_postgres()
    chroma = await _check_chroma()
    todo_ok = postgres == "ok" and chroma == "ok"
    return {
        "estado_general": "ok" if todo_ok else "degradado",
        "api": "ok",
        "postgres": postgres,
        "chroma": chroma,
    }


@app.get("/llm/hello")
def llm_hello():
    # Endpoint síncrono a propósito: el SDK de Together es síncrono y FastAPI
    # lo ejecuta en un hilo aparte para no bloquear el servidor.
    if not settings.TOGETHER_API_KEY:
        return {"error": "Falta TOGETHER_API_KEY en el .env"}
    try:
        return {"model": settings.LLM_MODEL, "respuesta": llm_client.hello()}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
