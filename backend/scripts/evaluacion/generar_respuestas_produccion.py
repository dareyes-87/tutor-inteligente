"""
Respuestas de la configuración de producción para RAGAS (correcciones del jurado, paso 5).

Recorre el mismo camino que POST /chat/preguntar (chat/service.py) sin BD:
recuperar_contexto() (RAG con el índice activo: EMBEDDING_MODEL + CHROMA_COLLECTION,
filtro de ejercicios incluido) → is_context_relevant() → build_messages() (system
prompt del grado/asignatura + contexto, sin historial) → llm_client.chat_finetuned()
(modelo ajustado v1 en Modal). Sin el fallback a Together: si Modal falla, la
pregunta queda en ERROR y se reporta (así se mide SOLO el modelo ajustado).

Uso (dentro del contenedor, con el índice adoptado):
    docker compose exec -e EMBEDDING_MODEL=intfloat/multilingual-e5-small \
        -e CHROMA_COLLECTION=libros_texto_e5 backend \
        python scripts/evaluacion/generar_respuestas_produccion.py

Salida: respuestas_produccion_e5.json (cache: si existe, solo completa las que faltan).
"""
import asyncio
import json
import sys
import time
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR.parents[1]))  # backend/

from app.config import settings  # noqa: E402
from app.llm.client import llm_client  # noqa: E402
from app.modules.chat.prompts import build_context_prompt, build_messages  # noqa: E402
from app.modules.chat.service import recuperar_contexto  # noqa: E402
from app.modules.ingesta.embeddings import MODEL_NAME  # noqa: E402
from app.modules.ingesta.indexer import COLLECTION_NAME  # noqa: E402
from app.modules.rag.search import is_context_relevant  # noqa: E402

SALIDA = DIR / "respuestas_produccion_e5.json"


async def main():
    preguntas = json.loads((DIR / "preguntas_ragas.json").read_text())
    previas = {r["pregunta"]: r for r in json.loads(SALIDA.read_text())} if SALIDA.exists() else {}
    resultados = []
    t0 = time.time()
    for i, p in enumerate(preguntas, 1):
        previa = previas.get(p["pregunta"])
        if previa and previa["status"] == "OK":
            resultados.append(previa)
            continue
        frags, _, _ = await recuperar_contexto(p["pregunta"], p["asignatura"], p["grado"])
        r = {**p, "retrieved_contexts": [f["text"] for f in frags],
             "paginas_recuperadas": [f["page_num"] for f in frags],
             "modelo_generador": f"{settings.MODAL_FINETUNED_MODEL_NAME} (Modal)",
             "embeddings": MODEL_NAME, "coleccion": COLLECTION_NAME,
             "respuesta_tutor": "", "status": "ERROR"}
        if not is_context_relevant(frags):
            r["status"] = "RECHAZADA"  # producción responde el mensaje fijo, sin LLM
        else:
            mensajes = build_messages(build_context_prompt(frags), [], p["pregunta"],
                                      p["grado"], p["asignatura"])
            try:
                t = time.time()
                r["respuesta_tutor"] = await asyncio.to_thread(llm_client.chat_finetuned, mensajes) or ""
                r["latencia_s"] = round(time.time() - t, 1)
                r["status"] = "OK" if r["respuesta_tutor"] else "EMPTY"
            except Exception as e:  # noqa: BLE001
                r["error"] = f"{type(e).__name__}: {e}"
        resultados.append(r)
        print(f"{i:2d}/50 {r['status']:9} {p['pregunta'][:60]}", flush=True)
        SALIDA.write_text(json.dumps(resultados + [x for x in previas.values()
                                                   if x["pregunta"] not in {y["pregunta"] for y in resultados}],
                                     ensure_ascii=False, indent=1))
    SALIDA.write_text(json.dumps(resultados, ensure_ascii=False, indent=1))
    print(f"{sum(r['status'] == 'OK' for r in resultados)}/50 OK en {time.time() - t0:.0f} s → {SALIDA.name}")


if __name__ == "__main__":
    asyncio.run(main())
