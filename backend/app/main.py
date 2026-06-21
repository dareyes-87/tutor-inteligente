"""
Punto de entrada de la API del Tutor Inteligente.
Sprint 0: /health, /llm/hello
Sprint 1: /auth/*, /ingesta/*
Sprint 2: /chat/*, /actividades/*
"""
import logging
import httpx
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine, AsyncSessionLocal
from app.llm.client import llm_client
from app.seed import seed_admin

# Importar routers
from app.modules.auth.router import router as auth_router
from app.modules.ingesta.router import router as ingesta_router
from app.modules.chat.router import router as chat_router
from app.modules.actividades.router import router as actividades_router
from app.modules.lecciones.router import router as lecciones_router
from app.modules.docente.router import router as docente_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as db:
        await seed_admin(db)
    yield
    await engine.dispose()


app = FastAPI(
    title="Tutor Inteligente API",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar todos los routers
app.include_router(auth_router)
app.include_router(ingesta_router)
app.include_router(chat_router)
app.include_router(actividades_router)
app.include_router(lecciones_router)
app.include_router(docente_router)


# ---- Endpoints de infraestructura ----

async def _check_postgres() -> str:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as e:
        return f"error: {type(e).__name__}"


async def _check_chroma() -> str:
    url = f"http://{settings.CHROMA_HOST}:{settings.CHROMA_PORT}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            for path in ("/api/v2/heartbeat", "/api/v1/heartbeat"):
                r = await client.get(url + path)
                if r.status_code == 200:
                    return "ok"
        return "down"
    except Exception as e:
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
    if not settings.TOGETHER_API_KEY:
        return {"error": "Falta TOGETHER_API_KEY en el .env"}
    try:
        return {"model": settings.LLM_MODEL, "respuesta": llm_client.hello()}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
