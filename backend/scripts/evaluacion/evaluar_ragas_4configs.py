"""
Evaluación RAGAS (Faithfulness) de 4 configuraciones sobre las mismas 50 preguntas:

  A) Base 7B (Together) SIN RAG — control: el modelo responde sin fragmentos del
     libro. Se evalúa igual contra los retrieved_contexts REALES (los mismos que
     usaron B/C/D) para medir qué tan lejos se va sin grounding, no un 0.0 trivial.
  B) Base 7B (Together) + RAG — YA EVALUADO (backend/scripts/evaluacion/
     respuestas_cache.json + resumen_ragas.json, corrida del 2026-07-11). No se
     vuelve a correr: mismo modelo, mismo RAG, mismo contenido indexado.
  C) Fine-tuned v1 (563 ejemplos, Modal) + RAG — mismos retrieved_contexts que B.
  D) Fine-tuned v2 (990 ejemplos, Modal) + RAG — mismos retrieved_contexts que B.

Para A/C/D se reconstruye el mismo system prompt de producción
(build_system_prompt) y el mismo formato de contexto (build_context_prompt) que
usó B, tomando los retrieved_contexts ya guardados en el cache de B (mismo
contenido indexado, misma pregunta -> mismo contexto real).

--- Uso ---
    TOGETHER_API_KEY=xxx MODAL_FINETUNED_API_KEY=xxx \\
    python backend/scripts/evaluacion/evaluar_ragas_4configs.py

Salidas: respuestas_cache_configA.json / _configC.json / _configD.json (cache,
igual que el original) y resumen_4configs.json + tabla en stdout.
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR.parent.parent))  # backend/ para importar app.*
from app.modules.chat.prompts import build_context_prompt, build_system_prompt  # noqa: E402

CACHE_B_PATH = DIR / "respuestas_cache.json"
RESUMEN_B_PATH = DIR / "resumen_ragas.json"

MODAL_V1_URL = "https://dareyes-87--tutor-finetuned-server-server.us-east.modal.direct/v1/chat/completions"
MODAL_V2_URL = "https://dareyes-87--tutor-finetuned-server-v2-server.us-east.modal.direct/v1/chat/completions"
MODAL_API_KEY = os.environ["MODAL_FINETUNED_API_KEY"]
TOGETHER_URL = "https://api.together.xyz/v1/chat/completions"
TOGETHER_API_KEY = os.environ["TOGETHER_API_KEY"]
BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct-Turbo"
MODELO_EVALUADOR = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
UMBRAL = 0.80


def preguntar(url, headers, model, messages, timeout=30, plazo_total=240, intervalo=10):
    """Igual que en comparar.py: Modal responde 503 fail-fast en cold start (no
    encola), así que se reintenta cada `intervalo`s hasta agotar `plazo_total`."""
    inicio = time.monotonic()
    while True:
        try:
            resp = requests.post(
                url, headers=headers,
                json={"model": model, "messages": messages, "max_tokens": 600, "temperature": 0.7},
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            transcurrido = time.monotonic() - inicio
            if transcurrido + intervalo >= plazo_total:
                raise
            time.sleep(intervalo)


def generar_config(nombre_config, base_b, generador_respuesta) -> list[dict]:
    """generador_respuesta(messages) -> str. Usa los mismos retrieved_contexts de
    B para cada pregunta (mismo contenido indexado); solo cambia quién y con qué
    prompt/contexto genera la respuesta."""
    cache_path = DIR / f"respuestas_cache_config{nombre_config}.json"
    if cache_path.exists():
        resultados = json.loads(cache_path.read_text(encoding="utf-8"))
        print(f"[{nombre_config}] {len(resultados)} respuestas desde cache ({cache_path.name})")
        return resultados

    resultados = []
    total = len(base_b)
    for i, rb in enumerate(base_b, start=1):
        registro = {
            "pregunta": rb["pregunta"], "asignatura": rb["asignatura"],
            "asignatura_id": rb["asignatura_id"], "tipo": rb["tipo"], "grado": rb["grado"],
            "retrieved_contexts": rb["retrieved_contexts"],
            "respuesta_tutor": "", "status": "ERROR",
        }
        try:
            system = build_system_prompt(None, rb["asignatura"])  # admin sin grado, igual que B
            if nombre_config == "A":
                # SIN RAG: no se le pasa contexto del libro al modelo.
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": rb["pregunta"]},
                ]
            else:
                frags = [{"page_num": "?", "text": t} for t in rb["retrieved_contexts"]]
                contexto = build_context_prompt(frags)
                messages = [
                    {"role": "system", "content": f"{system}\n\n{contexto}"},
                    {"role": "user", "content": rb["pregunta"]},
                ]
            respuesta = generador_respuesta(messages)
            registro["respuesta_tutor"] = respuesta or ""
            registro["status"] = "OK" if respuesta else "EMPTY"
            print(f"[{nombre_config}] {i}/{total}: {rb['pregunta'][:55]}  {'OK' if respuesta else 'vacío'}")
        except Exception as e:
            registro["status"] = "ERROR"
            print(f"[{nombre_config}] {i}/{total}: {rb['pregunta'][:55]}  ERROR ({type(e).__name__}: {e})",
                  file=sys.stderr)
        resultados.append(registro)

    cache_path.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{nombre_config}] guardado en {cache_path.name}")
    return resultados


def evaluar_faithfulness(resultados: list[dict]) -> None:
    """Igual criterio que evaluar_ragas.py: EMPTY/ERROR no se evalúan con RAGAS."""
    from ragas import EvaluationDataset, evaluate
    from ragas.dataset_schema import SingleTurnSample
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness
    from langchain_together import ChatTogether

    for r in resultados:
        if r["status"] == "EMPTY":
            r["faithfulness"] = 0.0
        elif r["status"] == "ERROR":
            r["faithfulness"] = None
        else:
            r["faithfulness"] = None

    evaluables = [r for r in resultados if r["status"] == "OK" and r["retrieved_contexts"]]
    if not evaluables:
        print("No hay preguntas evaluables.", file=sys.stderr)
        return

    llm = ChatTogether(model=MODELO_EVALUADOR, together_api_key=TOGETHER_API_KEY)
    evaluator_llm = LangchainLLMWrapper(llm)
    samples = [
        SingleTurnSample(
            user_input=r["pregunta"], response=r["respuesta_tutor"],
            retrieved_contexts=r["retrieved_contexts"],
        )
        for r in evaluables
    ]
    dataset = EvaluationDataset(samples=samples)
    print(f"Evaluando Faithfulness de {len(samples)} respuestas con {MODELO_EVALUADOR}...")
    result = evaluate(dataset=dataset, metrics=[Faithfulness(llm=evaluator_llm)], llm=evaluator_llm)
    df = result.to_pandas()
    col = "faithfulness" if "faithfulness" in df.columns else df.columns[-1]
    for r, score in zip(evaluables, df[col]):
        try:
            valor = float(score)
        except (TypeError, ValueError):
            valor = 0.0
        r["faithfulness"] = 0.0 if valor != valor else valor


def _promedio(valores):
    vals = [v for v in valores if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def resumen_de(resultados: list[dict]) -> dict:
    def scores(filtro):
        return [r["faithfulness"] for r in resultados
                if r["status"] != "ERROR" and r.get("faithfulness") is not None and filtro(r)]

    return {
        "global": _promedio(scores(lambda r: True)),
        "ciencias": _promedio(scores(lambda r: r["asignatura"] == "Ciencias Naturales")),
        "matematicas": _promedio(scores(lambda r: r["asignatura"] == "Matemáticas")),
        "conceptual": _promedio(scores(lambda r: r["tipo"] == "conceptual")),
        "factual": _promedio(scores(lambda r: r["tipo"] == "factual")),
        "procedimental": _promedio(scores(lambda r: r["tipo"] == "procedimental")),
        "errores": sum(1 for r in resultados if r["status"] == "ERROR"),
    }


def main():
    if not CACHE_B_PATH.exists():
        print(f"ERROR: falta {CACHE_B_PATH} (Config B, ya debería existir).", file=sys.stderr)
        sys.exit(1)
    base_b = json.loads(CACHE_B_PATH.read_text(encoding="utf-8"))
    resumen_b = json.loads(RESUMEN_B_PATH.read_text(encoding="utf-8")) if RESUMEN_B_PATH.exists() else None

    modal_headers = {"Authorization": f"Bearer {MODAL_API_KEY}"}
    together_headers = {"Authorization": f"Bearer {TOGETHER_API_KEY}"}

    resultados_a = generar_config("A", base_b, lambda m: preguntar(TOGETHER_URL, together_headers, BASE_MODEL, m))
    resultados_c = generar_config("C", base_b, lambda m: preguntar(MODAL_V1_URL, modal_headers, "tutor-finetuned", m))
    resultados_d = generar_config("D", base_b, lambda m: preguntar(MODAL_V2_URL, modal_headers, "tutor-finetuned-v2", m))

    print("\nEvaluando faithfulness de las 3 configuraciones nuevas...")
    evaluar_faithfulness(resultados_a)
    evaluar_faithfulness(resultados_c)
    evaluar_faithfulness(resultados_d)

    for nombre, resultados in (("A", resultados_a), ("C", resultados_c), ("D", resultados_d)):
        path = DIR / f"respuestas_cache_config{nombre}.json"
        path.write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")

    resumenes = {
        "A_base_sin_rag": resumen_de(resultados_a),
        "B_base_con_rag": {
            "global": resumen_b["faithfulness_global"], "ciencias": resumen_b["faithfulness_ciencias"],
            "matematicas": resumen_b["faithfulness_matematicas"], "conceptual": resumen_b["faithfulness_conceptual"],
            "factual": resumen_b["faithfulness_factual"], "procedimental": resumen_b["faithfulness_procedimental"],
            "errores": resumen_b["preguntas_error"],
        } if resumen_b else None,
        "C_v1_con_rag": resumen_de(resultados_c),
        "D_v2_con_rag": resumen_de(resultados_d),
    }

    def fmt(v):
        return f"{v:.4f}" if v is not None else "N/A"

    print("\n" + "=" * 90)
    print(f"{'':22}{'A) Base sin RAG':>16}{'B) Base+RAG':>16}{'C) v1+RAG':>16}{'D) v2+RAG':>16}")
    print("=" * 90)
    filas = [
        ("Faithfulness GLOBAL", "global"), ("  Ciencias Naturales", "ciencias"),
        ("  Matemáticas", "matematicas"), ("  Conceptual", "conceptual"),
        ("  Factual", "factual"), ("  Procedimental", "procedimental"),
    ]
    for etiqueta, clave in filas:
        fila = [fmt(resumenes[c][clave]) if resumenes[c] else "N/A"
                for c in ("A_base_sin_rag", "B_base_con_rag", "C_v1_con_rag", "D_v2_con_rag")]
        print(f"{etiqueta:22}{fila[0]:>16}{fila[1]:>16}{fila[2]:>16}{fila[3]:>16}")
    print("=" * 90)

    out_path = DIR / "resumen_4configs.json"
    out_path.write_text(json.dumps(resumenes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGuardado: {out_path}")


if __name__ == "__main__":
    main()
