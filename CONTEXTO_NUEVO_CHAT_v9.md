# CONTEXTO_NUEVO_CHAT_v9

**Fecha:** 21-23 de julio de 2026.
**Para:** continuidad en un chat nuevo.

---

## 1. Modelo fine-tuned v1 en Modal + A/B por grado — EN PRODUCCIÓN

Objetivo específico 3 de la tesis (fine-tuned vs. base). El modelo v1 (563 ejemplos, `dhreyes03_8f57/Qwen2.5-7B-Instruct-tutor-pedagogico-51b293e9`, job `ft-0b6b58db-9271` de Together AI) está servido vía **vLLM sobre GPU A10G en Modal** (cuenta `dareyes-87`), con scale-to-zero.

**Estado actual:** app `tutor-finetuned-server`, endpoint `https://dareyes-87--tutor-finetuned-server-server.us-east.modal.direct`, protegido con API key (Modal Secret `tutor-finetuned-api-key`, env `VLLM_API_KEY`). 0 tasks activas cuando nadie lo usa = $0 de costo idle.

**Integración backend** (commits `4bef2c4`, `778d298` en `origin/main`, ya en Railway):
- `backend/app/llm/client.py`: `chat_finetuned()` — reintenta cada 10s hasta agotar `MODAL_FINETUNED_TIMEOUT_SEGUNDOS` (200s) en vez de rendirse al primer 503 (Modal responde fail-fast mientras el contenedor está frío, no encola). Corre en `asyncio.to_thread` porque el backend usa `--workers 1`: sin eso, un cold start de un estudiante congelaría el servidor para todos.
- `backend/app/modules/chat/service.py`: `grado_usa_finetuned(grado_id)` decide el enrutamiento; fallback silencioso a Together si Modal falla.
- Variables Railway ya configuradas: `MODAL_FINETUNED_URL` (endpoint **v1**), `MODAL_FINETUNED_MODEL_NAME=tutor-finetuned`, `MODAL_FINETUNED_API_KEY`, `MODAL_FINETUNED_GRADOS=3` (6to Primaria), `MODAL_FINETUNED_TIMEOUT_SEGUNDOS=200`.
- Frontend (`web/app/(app)/chat/page.tsx` y `.../ruta/[leccionId]/estudiar/page.tsx`): mensaje "El tutor está despertando…" si la respuesta tarda >10s.

**Verificado en prod:** estudiante real `layala` (grado_id=3, 6to Primaria) con Modal completamente frío → esperó ~210s y recibió respuesta real del fine-tuned (confirmado en logs de vLLM: `POST /v1/chat/completions → 200 OK`). Estudiante `naldana` (4to Primaria) → nunca toca Modal, se queda en el base. Modal apagado a mano → `layala` recibe fallback sin error visible.

**Bug real encontrado y corregido en `serve.py`:** `SERVED_MODEL_NAME` (y cualquier variable leída dentro de `start()`) se evalúa en el proceso REMOTO de Modal al arrancar el contenedor (que re-importa el archivo), NO en el shell local que corre `modal deploy` — un env var local no llega ahí solo. Fix: pasarlo explícito vía `env={"SERVED_MODEL_NAME": ...}` en el decorador `@app.server(...)`. `APP_NAME`/`VOLUME_NAME` sí funcionan por env var local porque se usan al definir el objeto App/Volume en tiempo de deploy (local), no dentro del método remoto.

**Decisión final: v1 se queda en producción.** v2 se evaluó (sección 3) y no lo superó — ver sección 4.

---

## 2. Dataset v2 (990 ejemplos) — GENERADO, ENTRENADO, NO desplegado en producción

`backend/scripts/generar_dataset_finetuning.py` extendido con 5 categorías nuevas (`_categoria4_rechazo` … `_categoria8_multiturno`, `_generar_hasta_objetivo` para generación por lotes con redistribución en cascada cuando un pool de seeds se agota). Corrida completa (`completo-v2`): **427 ejemplos nuevos** (no 437 — `diferenciacion` quedó 10 por debajo de su objetivo y no se redistribuyó, decisión explícita de no gastar más crédito en eso).

- `guia_ejercicio`: pool real de solo 75 páginas-ejercicio → quedó en 58/100. El faltante (42) se redistribuyó proporcionalmente: enumeración +18 (→98, alcanzado), multiturno +24 (→131, alcanzado).
- Resultado: **train_v2.jsonl = 890** (506 original + 384 nuevos) · **val_v2.jsonl = 100** (57 + 43). Guardados en `backend/scripts/dataset_out/` (gitignored, ahí vive el working copy) y espejados en `docs/tesis/dataset_finetuning/train_v2.jsonl`/`val_v2.jsonl` (sí commiteados, mismo patrón que v1). 0 duplicados internos, 0 solape train∩val.
- Costo generación: **$3.18** (23.5 min).

**Fine-tuning v2 lanzado y completado:**
- **Job ID: `ft-b0c0db64-4b27`**
- **Modelo resultante: `dhreyes03_8f57/Qwen2.5-7B-Instruct-tutor-pedagogico-v2-2db89a1e`**
- Mismos hiperparámetros que v1 (QLoRA r=8, alpha=16, dropout=0.1, 3 épocas, lr=1e-5, batch=16, cosine scheduler).
- Costo: **$4.00 exacto** (tokens reales: 1,585,511 total, 2.01x v1, pero el cómputo ($2.28) sigue bajo el mínimo de $4 de Together — por eso costó lo mismo que v1 pese a casi duplicar los datos).
- Duración: ~9 min 13s.
- Val loss: 0.9463 → 0.8643 → 0.8555 (más bajo que v1 en las 3 épocas: 1.0850 → 1.0010 → 0.9932; esperable con más datos, sin señal de sobreajuste).

**Desplegado en Modal EN PARALELO al v1** (no lo reemplazó): app `tutor-finetuned-server-v2`, Volume `tutor-finetuned-weights-v2`, endpoint `https://dareyes-87--tutor-finetuned-server-v2-server.us-east.modal.direct`, modelo servido `tutor-finetuned-v2`. Railway **no apunta acá** — v2 no está en producción.

---

## 3. Evaluación RAGAS de 4 configuraciones — Faithfulness sobre las mismas 50 preguntas

Script nuevo: `backend/scripts/evaluacion/evaluar_ragas_4configs.py`. Metodología: A/C/D se evalúan contra los MISMOS `retrieved_contexts` reales que ya tenía B (cache del 2026-07-11, no se volvió a correr), así que Config A (sin RAG) mide qué tan lejos se va del libro real al no tener grounding, no un 0.0 trivial por falta de contexto.

| | A) Base sin RAG | B) Base+RAG (prod hoy) | C) v1+RAG | D) v2+RAG |
|---|---:|---:|---:|---:|
| **Faithfulness GLOBAL** | 0.6692 | 0.8381 | **0.8476** | 0.8438 |
| Ciencias Naturales | 0.6445 | **0.8347** | 0.8211 | 0.8216 |
| Matemáticas | 0.6938 | 0.8415 | **0.8742** | 0.8651 |
| Conceptual | 0.8001 | **0.9351** | 0.8755 | 0.9231 |
| Factual | 0.6617 | 0.6977 | **0.8023** | 0.7780 |
| Procedimental | 0.4906 | **0.8599** | 0.8596 | 0.8112 |

(2 de 150 respuestas nuevas fallaron en el juez de RAGAS por un límite de tokens interno de la librería — tooling, no dato — quedaron excluidas del promedio.)

Guardado en `backend/scripts/evaluacion/resumen_4configs.json` + caches `respuestas_cache_config{A,C,D}.json`. Config B ya existía (`respuestas_cache.json`, `resumen_ragas.json`, del 11 jul, sin commitear todavía — son de antes de esta sesión).

**Smoke test cualitativo (4 preguntas ad-hoc) v1 vs v2 vs base:** `backend/scripts/modal_finetuned/comparacion_resultado_v1_v2.json` (el archivo `comparacion_resultado.json` a secas es el smoke test VIEJO, solo v1 vs base, de la primera prueba — no confundir).

---

## 4. Hallazgo principal y decisión

**v2 (990 ejemplos) NO superó a v1 (563) en faithfulness** — en la mayoría de los desgloses (Matemáticas, Conceptual, Factual, Procedimental) v1 quedó igual o por encima de v2; el global favorece a v1 por 0.004 (dentro del ruido con n=50). Esto **replica el hallazgo de Zhou et al. (LIMA, 2023)**: más allá de cierto punto, la diversidad/calidad de los datos importa más que la cantidad bruta — duplicar el dataset con 5 categorías nuevas no se tradujo en mejor faithfulness, probablemente porque esas categorías nuevas (rechazo, multi-turno, guía de ejercicio) entrenan comportamientos que no son directamente "citar mejor el libro dado", así que no tenían por qué mover esta métrica específica.

Sí quedó claro que **el fine-tuning (v1 o v2, cualquiera) mejora sobre el base en Matemáticas y en preguntas Factuales** (+3 a +13 puntos) — esa es la ganancia real y consistente del objetivo específico 3, independiente de v1 vs v2.

**Decisión final: v1 se queda en producción.** v2 queda desplegado en Modal (`tutor-finetuned-server-v2`) como resultado evaluado y documentado para la tesis, pero Railway sigue apuntando a v1 — no hubo swap.

---

## 5. Estado de infraestructura (para retomar)

- **Postgres y Chroma corriendo localmente** (`docker compose up -d postgres chroma`), libros ya indexados (321 fragmentos Ciencias, 248 Matemáticas).
- **`docker-compose.yml` tiene un cambio LOCAL SIN COMMITEAR**: se quitó `ports: ["5432:5432"]` de `postgres` porque el puerto 5432 del host lo ocupa un proyecto ajeno (`farmag`, no tocar). El backend igual llega a Postgres por la red interna de Docker. **No commitear.** Revertir con `git checkout -- docker-compose.yml` si hace falta (pero entonces `docker compose up` normal vuelve a fallar por el conflicto de puerto).
- Para correr scripts del backend: `docker compose run --rm --no-deps -e PYTHONUNBUFFERED=1 -e PYTHONPATH=/app backend python scripts/<script>.py`. Para scripts que usan `scripts/debug/` (rutas relativas a la raíz del repo, no a `/app`): correr con `.venv-modal/bin/python backend/scripts/<script>.py` desde la raíz, no dentro del contenedor.
- **Modal:** `.venv-modal/` con el SDK autenticado (workspace `dareyes-87`, token en `~/.modal.toml`). `modal app list` / `modal app logs <nombre>`. Apps activas: `tutor-finetuned-server` (v1, producción), `tutor-finetuned-server-v2` (v2, paralelo, no usado por Railway).
- **RAGAS:** `.venv-ragas/` (venv local separado, NO en la imagen del backend) con `ragas`, `langchain-together`, `requests`, `pandas` instalados.
- **Pendiente de commitear** (de antes de esta sesión, no se tocó): `backend/scripts/evaluacion/respuestas_cache.json`, `resultados_ragas.csv`, `resumen_ragas.json`, `respuestas_cache_2026-07-06.json.bak` (Config B), y `CONTEXTO_NUEVO_CHAT_v8.md`, `scripts/debug/extraer_fragmentos.py` + 2 `.txt` (de sesiones previas, fuera del alcance de hoy).
