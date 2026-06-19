# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"Tutor Inteligente" — a RAG-based intelligent tutoring backend for Guatemalan school students. Teachers upload textbook PDFs; the system OCRs and indexes them, then students chat with an LLM tutor and solve auto-generated activities, all grounded in the indexed textbook content. The codebase, comments, model names, and API responses are in **Spanish** — keep new code and docstrings in Spanish to match.

Everything runs in Docker: a FastAPI backend, PostgreSQL 16 (relational data), and ChromaDB (vector store). The LLM is served remotely by **Together AI** (default model `Qwen/Qwen2.5-7B-Instruct-Turbo`); embeddings run locally on CPU via sentence-transformers.

## Commands

All commands run through Docker Compose from the repo root. The backend mounts `./backend` as a volume with `--reload`, so Python changes hot-reload without rebuilding.

```bash
docker compose up --build        # first run / after requirements.txt changes
docker compose up                # normal start
docker compose down              # stop (add -v to also wipe pgdata/chroma/books volumes)
docker compose logs -f backend   # tail backend logs
docker compose exec backend bash # shell into the backend container
```

Health/smoke checks: `http://localhost:8000/health` (checks Postgres + Chroma), `http://localhost:8000/docs` (Swagger UI). ChromaDB is exposed on host port **8010** (container 8000); Postgres on 5432.

### Database migrations (Alembic)

Run inside the backend container. `alembic/env.py` imports `app.models` and pulls the DB URL from `app.config.settings`, so a new model is only picked up after it's imported in `app/models/__init__.py` **and** in the `env.py` import list.

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic revision --autogenerate -m "descripcion"
docker compose exec backend alembic current
```

### Tests

There is **no test suite** in this repo yet. Verification is manual via `/docs` and `/health`.

## Configuration

All config flows through `app/config.py` (`pydantic-settings`, reads `.env`). Copy `.env.example` → `.env` before first run and set `POSTGRES_PASSWORD`, `TOGETHER_API_KEY`, and `SECRET_KEY`. On startup, `app/seed.py` (via the FastAPI lifespan) creates an admin user from `ADMIN_USERNAME`/`ADMIN_PASSWORD` if one doesn't exist.

## Architecture

The backend is a modular FastAPI app. `app/main.py` wires four routers (`auth`, `ingesta`, `chat`, `actividades`) plus infra endpoints, and CORS is locked to `http://localhost:3000` (the intended frontend origin).

### Module convention

Each feature under `app/modules/<feature>/` follows the same layering: `router.py` (HTTP + auth deps) → `service.py` (business logic, owns the DB session) → `schemas.py` (Pydantic I/O). Routers stay thin; put logic in services. Models live centrally in `app/models/`, not per-module.

### Two-database split

- **PostgreSQL** (SQLAlchemy **async**, `app/database.py`): all relational state — users, books, fragments, conversations, messages, activities, comprehension profiles. Use `AsyncSession`; services are `async` and `await` their queries.
- **ChromaDB** (`app/modules/ingesta/indexer.py`): vector store, single collection `libros_texto`. Every chunk is stored in **both** places — full text + metadata in the `Fragmento` Postgres table, and the embedding + metadata in Chroma keyed by `chunk_id` (`libro_{id}_chunk_{nnnnn}`). RAG filters by `asignatura`/`grado` metadata so a student only retrieves from textbooks matching their subject and grade.

### Ingestion pipeline (the heavy path)

Uploading a book (`POST /ingesta/libros`, teacher/admin only) saves the PDF to disk (`BOOKS_DIR`, the `books` volume), creates a `LibroTexto` row, and returns **HTTP 202 immediately**. The actual processing is fired with `asyncio.create_task(procesar_libro(...))` — it must never run inside the request because a book can take minutes.

`app/workers/ingesta_worker.py::procesar_libro` opens its **own** `AsyncSessionLocal` (it outlives the request) and runs: `pdf_processor` (per-page: digital text extraction, falling back to Tesseract OCR with `lang="spa"` for scanned pages, tracking a confidence score) → `chunking` (~800-char chunks, 150 overlap, cut on sentence boundaries) → `embeddings` (sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2`, CPU singleton) → `indexer` (Chroma) → persist `Fragmento` rows → update `LibroTexto.estado_indexacion` (`procesando`→`completado`/`error`). Clients poll `GET /ingesta/libros/{id}/estado`. The OCR system deps (`tesseract-ocr`, `tesseract-ocr-spa`, `libmagic1`) are installed in the Dockerfile, not pip.

### Chat (RAG) flow

`POST /chat/preguntar` → `chat/service.py::procesar_pregunta`: get/create `Conversacion` → `rag/search.py::search_fragments` (embed question, query Chroma with `asignatura`/`grado` filter, drop results past `MAX_DISTANCE=1.5`, top-5) → `chat/prompts.py` builds the pedagogical system prompt + retrieved context + prior message history → `llm_client.chat()` → persist both user and assistant `Mensaje` rows (assistant message stores `referencias` to source fragments/pages).

### Activities flow

`actividades/generator.py` asks the LLM (via `llm_client.generate_json`, low temperature, strips ```json fences) for one of five activity types (`opcion_multiple`, `verdadero_falso`, `completar`, `ordenar`, `respuesta_corta`), grounded in RAG context. The service **splits** the LLM output into `contenido` (shown to the student) and `respuesta_correcta` (hidden) before storing. On answer (`POST /actividades/responder`), `evaluator.py` grades it and `_actualizar_perfil` updates the student's running `PerfilComprension` average per (asignatura, tema) — this is the adaptive/comprehension-tracking layer.

### LLM client

`app/llm/client.py` is a single shared `llm_client` instance wrapping the Together SDK with three methods: `chat()` (free-form tutor replies), `generate_json()` (structured activities, parses + fence-strips, returns `None` on bad JSON), and `hello()` (smoke test). Route all LLM calls through it.

### Auth & roles

JWT (HS256) in `app/security.py`; `app/modules/auth/dependencies.py` exposes `get_current_user` and `require_role(*roles)`. Three roles (`RolUsuario`: `estudiante`, `docente`, `administrador`). Only docentes/administradores can register users and upload/inspect books; chat and activities are per-authenticated-student and scoped to `current_user.id`. There is no public self-registration — `/auth/registro` itself requires a docente/admin token.


## Reglas de desarrollo (NO NEGOCIABLES)

- MODIFICA archivos existentes directamente. NUNCA crees variantes como
  `_v2`, `_new`, `_improved`, `_fixed`. Un archivo, una versión.
- NO toques archivos fuera del módulo que se te pide trabajar, a menos que
  sea estrictamente necesario. Si crees que necesitas tocar otro módulo,
  pregunta primero y explica por qué.
- NO agregues dependencias nuevas a requirements.txt sin decirlo explícitamente
  y explicar por qué lo existente no alcanza.
- NO borres ni renombres funciones existentes sin antes verificar si se
  usan en otro archivo (usa grep/búsqueda antes de cambiar firmas).
- Si necesitas archivos de prueba temporales, créalos en `tmp/` o
  `scripts/debug/`, nunca sueltos dentro de `app/`.
- Antes de cualquier cambio grande, propone un plan corto (3-6 puntos) y
  espera confirmación antes de escribir código.
- Conocidos problemas de compatibilidad ya resueltos en este proyecto
  (no los reintroduzcas):
  - `passlib` requiere `bcrypt==4.2.1` fijo en requirements.txt
    (versiones más nuevas de bcrypt rompen passlib).
  - En `indexer.py`, la variable `_client` debe declararse como
    `_client = None` (sin anotación de tipo `chromadb.HttpClient | None`),
    porque chromadb no expone ese tipo de forma compatible con esa sintaxis.
  - El endpoint `/auth/login` debe usar `OAuth2PasswordRequestForm`
    (form-data), no JSON, porque Swagger UI / OAuth2PasswordBearer lo
    requiere así para el botón "Authorize".
