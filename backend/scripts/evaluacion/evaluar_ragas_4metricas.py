"""
RAGAS con 4 métricas sobre la configuración de producción (correcciones del jurado, paso 5).

Métricas: Faithfulness, ResponseRelevancy (Answer Relevancy), Context Precision con
referencia (LLMContextPrecisionWithReference) y Answer Correctness.

Entradas:
  respuestas_produccion_e5.json  (generar_respuestas_produccion.py: respuestas del
                                  modelo ajustado v1 en Modal + retrieved_contexts)
  referencias_ragas.json         (respuestas de referencia revisadas por el docente)

Evaluador: openai/gpt-oss-120b (Together). Embeddings (relevancia y corrección):
intfloat/multilingual-e5-small local, prefijo "query: " en ambos textos (comparación
simétrica pregunta↔pregunta y respuesta↔referencia).

Requisitos (venv LOCAL, NO en la imagen del backend):
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    pip install ragas langchain-together sentence-transformers pandas requests "langchain-community<0.4"

Uso:
    TOGETHER_API_KEY=xxx python backend/scripts/evaluacion/evaluar_ragas_4metricas.py --max-usd 3
    # --entrada/--salida para evaluar otras cachés (p. ej. configs A–D)
"""
import argparse
import json
import math
import os
import sys
from datetime import date
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR.parent))  # costos_llm.py
sys.path.insert(0, str(DIR))         # evaluar_ragas._callback_costos

from evaluar_ragas import _callback_costos  # noqa: E402
from costos_llm import Presupuesto, PresupuestoAgotado, agregar_argumento_max_usd  # noqa: E402

MODELO_EVALUADOR = "openai/gpt-oss-120b"
MODELO_EMBEDDINGS = "intfloat/multilingual-e5-small"
UMBRAL = 0.80
METRICAS = ["faithfulness", "answer_relevancy", "llm_context_precision_with_reference", "answer_correctness"]


def embeddings_e5():
    from langchain_core.embeddings import Embeddings
    from sentence_transformers import SentenceTransformer

    modelo = SentenceTransformer(MODELO_EMBEDDINGS)

    class E5(Embeddings):
        def embed_documents(self, texts):
            return modelo.encode(["query: " + t for t in texts], normalize_embeddings=True).tolist()

        def embed_query(self, text):
            return self.embed_documents([text])[0]

    return E5()


def promedio(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def main():
    ap = argparse.ArgumentParser()
    agregar_argumento_max_usd(ap, defecto=3.0)
    ap.add_argument("--entrada", default=str(DIR / "respuestas_produccion_e5.json"))
    ap.add_argument("--salida", default=str(DIR / "ragas_2026-11_produccion_e5"))
    ap.add_argument("--metricas", default=",".join(METRICAS))
    ap.add_argument("--reasoning-effort", default="low")
    args = ap.parse_args()

    import ragas
    from langchain_together import ChatTogether
    from ragas import EvaluationDataset, evaluate
    from ragas.dataset_schema import SingleTurnSample
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (AnswerCorrectness, Faithfulness,
                               LLMContextPrecisionWithReference, ResponseRelevancy)

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    cache = salida / "resultados.json"
    respuestas = json.loads(Path(args.entrada).read_text())
    referencias = {r["pregunta"]: r["referencia"] for r in json.loads((DIR / "referencias_ragas.json").read_text())}
    # Solo las preguntas vigentes (Q41 se retiró: el libro no desarrolla propiedades de la división).
    respuestas = [r for r in respuestas if r["pregunta"] in referencias]
    hechos = {r["pregunta"]: r for r in json.loads(cache.read_text())} if cache.exists() else {}

    key = os.environ["TOGETHER_API_KEY"]
    presupuesto = Presupuesto(args.max_usd, api_key=key)
    llm = LangchainLLMWrapper(ChatTogether(model=MODELO_EVALUADOR, together_api_key=key,
                                           reasoning_effort=args.reasoning_effort,
                                           callbacks=[_callback_costos(presupuesto)]))
    emb = LangchainEmbeddingsWrapper(embeddings_e5())
    disponibles = {
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": ResponseRelevancy(llm=llm, embeddings=emb),
        "llm_context_precision_with_reference": LLMContextPrecisionWithReference(llm=llm),
        "answer_correctness": AnswerCorrectness(llm=llm, embeddings=emb),
    }
    nombres = args.metricas.split(",")
    metricas = [disponibles[n] for n in nombres]

    resultados, pendientes = [], []
    for r in respuestas:
        fila = {k: r[k] for k in ("pregunta", "asignatura", "tipo", "grado", "status")}
        if r["pregunta"] in hechos and all(hechos[r["pregunta"]].get(m) is not None for m in nombres):
            fila = hechos[r["pregunta"]]
        elif r["status"] != "OK":
            # EMPTY: respuesta vacía cuenta como 0; ERROR/RECHAZADA quedan fuera de promedios.
            fila |= {m: 0.0 if r["status"] == "EMPTY" else None for m in nombres}
        else:
            pendientes.append((fila, r))
        resultados.append(fila)

    # Lotes de LOTE muestras (RAGAS las evalúa en paralelo); el tope se revisa entre lotes.
    LOTE = 10
    for i in range(0, len(pendientes), LOTE):
        try:
            presupuesto.verificar()
        except PresupuestoAgotado as e:
            print(f"DETENIDO: {e}", file=sys.stderr)
            break
        lote = pendientes[i:i + LOTE]
        muestras = [SingleTurnSample(user_input=r["pregunta"], response=r["respuesta_tutor"],
                                     retrieved_contexts=r["retrieved_contexts"],
                                     reference=referencias[r["pregunta"]]) for _, r in lote]
        df = evaluate(EvaluationDataset(samples=muestras), metrics=metricas, llm=llm,
                      embeddings=emb, show_progress=False).to_pandas()
        for j, (fila, _) in enumerate(lote):
            for m in nombres:
                v = float(df[m].iloc[j]) if m in df.columns else float("nan")
                fila[m] = None if math.isnan(v) else round(v, 4)  # NaN = el evaluador no pudo puntuar
        print(f"{min(i + LOTE, len(pendientes))}/{len(pendientes)} evaluadas  (${presupuesto.total_usd:.4f})", flush=True)
        cache.write_text(json.dumps(resultados, ensure_ascii=False, indent=1))
    cache.write_text(json.dumps(resultados, ensure_ascii=False, indent=1))

    def agregado(filtro):
        sel = [x for x in resultados if filtro(x)]
        return {m: promedio([x.get(m) for x in sel]) for m in nombres} | {"n": len(sel)}

    resumen = {
        "fecha": date.today().isoformat(),
        "ragas": ragas.__version__,
        "evaluador": MODELO_EVALUADOR,
        "reasoning_effort": args.reasoning_effort,
        "embeddings_metricas": MODELO_EMBEDDINGS,
        "entrada": Path(args.entrada).name,
        "evaluadas": sum(all(x.get(m) is not None for m in nombres) for x in resultados),
        "status": {s: sum(x["status"] == s for x in resultados) for s in {x["status"] for x in resultados}},
        "nan_por_metrica": {m: sum(x["status"] == "OK" and x.get(m) is None for x in resultados) for m in nombres},
        "global": agregado(lambda x: True),
        "por_asignatura": {a: agregado(lambda x, a=a: x["asignatura"] == a) for a in ("Ciencias Naturales", "Matemáticas")},
        "por_tipo": {t: agregado(lambda x, t=t: x["tipo"] == t) for t in ("conceptual", "factual", "procedimental")},
        "faithfulness_sobre_umbral": sum((x.get("faithfulness") or 0) >= UMBRAL for x in resultados)
        if "faithfulness" in nombres else None,
        "umbral_faithfulness": UMBRAL,
        "costo_usd": round(presupuesto.total_usd, 4),
        "costo_por_modelo": presupuesto.por_modelo,
    }
    (salida / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1))
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    presupuesto.imprimir_resumen()


if __name__ == "__main__":
    main()
