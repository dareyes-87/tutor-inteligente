"""
Evaluación RAGAS (Faithfulness) del tutor inteligente contra producción.

Consulta el endpoint temporal POST /chat/preguntar-debug (que devuelve la
respuesta del tutor + los contextos textuales recuperados por el RAG) para las
50 preguntas de `preguntas_ragas.json`, y calcula la métrica Faithfulness de
RAGAS usando Together AI (Llama-3.3-70B) como LLM evaluador.

--- Requisitos (instalar en un venv LOCAL, NO en la imagen del backend) ---
    pip install ragas langchain-together requests pandas

--- Variables de entorno ---
    TOGETHER_API_KEY   (obligatoria) clave de Together AI para el LLM evaluador
    API_URL            (opcional) URL de la API; por defecto la de Railway
    ADMIN_USERNAME     (opcional, default "admin")
    ADMIN_PASSWORD     (opcional, default "admin123")

--- Uso ---
    TOGETHER_API_KEY=xxx python backend/scripts/evaluacion/evaluar_ragas.py

Salidas (en la misma carpeta del script):
    resultados_ragas.csv    una fila por pregunta con su faithfulness
    resumen_ragas.json      agregados (global, por asignatura, por tipo, umbral)
"""
import csv
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests

# --- Rutas relativas a la carpeta del script (no dependen del cwd) ---
DIR = Path(__file__).resolve().parent
PREGUNTAS_PATH = DIR / "preguntas_ragas.json"
CSV_PATH = DIR / "resultados_ragas.csv"
RESUMEN_PATH = DIR / "resumen_ragas.json"

# --- Configuración ---
API_URL = os.environ.get(
    "API_URL", "https://tutor-inteligente-production.up.railway.app"
).rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin123")
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "")
MODELO_EVALUADOR = "meta-llama/Llama-3.3-70B-Instruct-Turbo"

UMBRAL = 0.80
TIMEOUT_PREGUNTA = 60      # segundos por request al tutor
REINTENTOS = 2             # reintentos extra si una pregunta falla
PAUSA_ENTRE = 2            # segundos entre preguntas (rate limiting)


def login() -> str:
    """Autentica como admin (form-data OAuth2) y devuelve el access_token."""
    resp = requests.post(
        f"{API_URL}/auth/login",
        data={"username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print(f"Login admin OK contra {API_URL}")
    return token


def preguntar_debug(token: str, pregunta: str, asignatura_id: int) -> dict:
    """Llama a /chat/preguntar-debug con reintentos. Devuelve el JSON de la
    respuesta o lanza la última excepción si agota los reintentos."""
    headers = {"Authorization": f"Bearer {token}"}
    body = {"pregunta": pregunta, "asignatura_id": asignatura_id}
    ultima_exc = None
    for intento in range(REINTENTOS + 1):
        try:
            resp = requests.post(
                f"{API_URL}/chat/preguntar-debug",
                json=body,
                headers=headers,
                timeout=TIMEOUT_PREGUNTA,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:  # noqa: BLE001 (queremos capturar timeout/HTTP/red)
            ultima_exc = e
            if intento < REINTENTOS:
                time.sleep(3 * (intento + 1))
    raise ultima_exc


def recolectar_respuestas(token: str, preguntas: list[dict]) -> list[dict]:
    """Consulta el tutor para cada pregunta y arma la lista de resultados crudos.

    Cada resultado: dict con la metadata de la pregunta + status
    (OK / EMPTY / ERROR), respuesta_tutor y retrieved_contexts.
    """
    resultados = []
    total = len(preguntas)
    for i, p in enumerate(preguntas, start=1):
        preview = p["pregunta"][:60]
        registro = {
            "pregunta": p["pregunta"],
            "asignatura": p.get("asignatura"),
            "asignatura_id": p.get("asignatura_id"),
            "tipo": p.get("tipo"),
            "grado": p.get("grado"),
            "respuesta_tutor": "",
            "retrieved_contexts": [],
            "num_contextos": 0,
            "status": "ERROR",
        }
        try:
            data = preguntar_debug(token, p["pregunta"], p["asignatura_id"])
            respuesta = data.get("respuesta", "") or ""
            contextos = [
                c.get("text", "")
                for c in data.get("contextos_recuperados", [])
                if c.get("text")
            ]
            registro["respuesta_tutor"] = respuesta
            registro["retrieved_contexts"] = contextos
            registro["num_contextos"] = len(contextos)
            # Contextos vacíos -> se registrará faithfulness 0.0 (regla del spec).
            registro["status"] = "OK" if contextos else "EMPTY"
            print(f"Pregunta {i}/{total}: {preview}  {'✓' if contextos else '∅ (sin contexto)'}")
        except Exception as e:  # noqa: BLE001
            registro["status"] = "ERROR"
            print(f"Pregunta {i}/{total}: {preview}  ✗ ERROR ({type(e).__name__})", file=sys.stderr)
        resultados.append(registro)
        if i < total:
            time.sleep(PAUSA_ENTRE)
    return resultados


def evaluar_faithfulness(resultados: list[dict]) -> None:
    """Evalúa Faithfulness con RAGAS sobre los resultados con status OK y
    escribe el score numérico en cada registro (clave 'faithfulness').

    - status EMPTY -> 0.0 (sin contexto no puede ser fiel al contexto).
    - status ERROR -> None (se reporta como ERROR, fuera de promedios).
    """
    # Import perezoso: la fase de recolección no requiere ragas instalado.
    from ragas import EvaluationDataset, evaluate
    from ragas.dataset_schema import SingleTurnSample
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness
    from langchain_together import ChatTogether

    # Defaults por status
    for r in resultados:
        if r["status"] == "EMPTY":
            r["faithfulness"] = 0.0
        elif r["status"] == "ERROR":
            r["faithfulness"] = None
        else:
            r["faithfulness"] = None  # se rellena tras evaluar

    evaluables = [r for r in resultados if r["status"] == "OK"]
    if not evaluables:
        print("No hay preguntas evaluables (todas EMPTY/ERROR).", file=sys.stderr)
        return

    llm = ChatTogether(
        model=MODELO_EVALUADOR,
        together_api_key=TOGETHER_API_KEY,
    )
    evaluator_llm = LangchainLLMWrapper(llm)

    samples = [
        SingleTurnSample(
            user_input=r["pregunta"],
            response=r["respuesta_tutor"],
            retrieved_contexts=r["retrieved_contexts"],
        )
        for r in evaluables
    ]
    dataset = EvaluationDataset(samples=samples)

    print(f"\nEvaluando Faithfulness de {len(samples)} preguntas con {MODELO_EVALUADOR}...")
    result = evaluate(
        dataset=dataset,
        metrics=[Faithfulness(llm=evaluator_llm)],
        llm=evaluator_llm,
    )

    df = result.to_pandas()
    # La columna puede llamarse 'faithfulness'; buscarla de forma tolerante.
    col = "faithfulness" if "faithfulness" in df.columns else df.columns[-1]
    scores = list(df[col])
    for r, score in zip(evaluables, scores):
        try:
            valor = float(score)
        except (TypeError, ValueError):
            valor = 0.0
        # RAGAS puede devolver NaN si el LLM no pudo desglosar afirmaciones.
        r["faithfulness"] = 0.0 if valor != valor else valor  # NaN -> 0.0


def _promedio(valores: list[float]) -> float | None:
    vals = [v for v in valores if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def exportar_y_resumir(resultados: list[dict]) -> None:
    """Escribe el CSV por pregunta, imprime la tabla resumen y guarda el JSON."""
    # --- CSV ---
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "pregunta", "asignatura", "tipo", "respuesta_tutor",
            "num_contextos", "faithfulness_score", "paso_umbral",
        ])
        for r in resultados:
            if r["status"] == "ERROR":
                score_cell, paso = "ERROR", ""
            else:
                score = r.get("faithfulness")
                score_cell = round(score, 4) if score is not None else ""
                paso = "SI" if (score is not None and score >= UMBRAL) else "NO"
            writer.writerow([
                r["pregunta"], r["asignatura"], r["tipo"],
                r["respuesta_tutor"].replace("\n", " ").strip(),
                r["num_contextos"], score_cell, paso,
            ])

    # --- Agregados (faithfulness numérico; ERROR queda excluido de promedios) ---
    def scores_de(filtro):
        return [
            r["faithfulness"]
            for r in resultados
            if r["status"] != "ERROR" and r.get("faithfulness") is not None and filtro(r)
        ]

    global_avg = _promedio(scores_de(lambda r: True))
    ciencias = _promedio(scores_de(lambda r: r["asignatura"] == "Ciencias Naturales"))
    matematicas = _promedio(scores_de(lambda r: r["asignatura"] == "Matemáticas"))
    conceptual = _promedio(scores_de(lambda r: r["tipo"] == "conceptual"))
    factual = _promedio(scores_de(lambda r: r["tipo"] == "factual"))
    procedimental = _promedio(scores_de(lambda r: r["tipo"] == "procedimental"))

    total = len(resultados)
    errores = sum(1 for r in resultados if r["status"] == "ERROR")
    sobre = sum(
        1 for r in resultados
        if r["status"] != "ERROR" and r.get("faithfulness") is not None
        and r["faithfulness"] >= UMBRAL
    )
    # Todo lo que no supera el umbral (incluye EMPTY=0.0 y ERROR) cae en "bajo".
    bajo = total - sobre

    def fmt(v):
        return f"{v:.4f}" if v is not None else "N/A"

    print("\n" + "=" * 48)
    print("           RESUMEN RAGAS — Faithfulness")
    print("=" * 48)
    print(f"Total preguntas:            {total}")
    print(f"Faithfulness GLOBAL:        {fmt(global_avg)}")
    print("-" * 48)
    print(f"  Ciencias Naturales:       {fmt(ciencias)}")
    print(f"  Matemáticas:              {fmt(matematicas)}")
    print("-" * 48)
    print(f"  Conceptual:               {fmt(conceptual)}")
    print(f"  Factual:                  {fmt(factual)}")
    print(f"  Procedimental:            {fmt(procedimental)}")
    print("-" * 48)
    print(f"Sobre umbral (>= {UMBRAL}):    {sobre}")
    print(f"Bajo umbral  (<  {UMBRAL}):    {bajo}   (incluye {errores} ERROR)")
    print("=" * 48)
    print(f"\nCSV:    {CSV_PATH}")

    # --- Resumen JSON ---
    resumen = {
        "fecha_evaluacion": date.today().isoformat(),
        "total_preguntas": total,
        "faithfulness_global": global_avg,
        "faithfulness_ciencias": ciencias,
        "faithfulness_matematicas": matematicas,
        "faithfulness_conceptual": conceptual,
        "faithfulness_factual": factual,
        "faithfulness_procedimental": procedimental,
        "preguntas_sobre_umbral": sobre,
        "preguntas_bajo_umbral": bajo,
        "preguntas_error": errores,
        "umbral": UMBRAL,
    }
    with open(RESUMEN_PATH, "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
    print(f"Resumen: {RESUMEN_PATH}")


def main() -> None:
    if not TOGETHER_API_KEY:
        print("ERROR: define TOGETHER_API_KEY (LLM evaluador de RAGAS).", file=sys.stderr)
        sys.exit(1)
    if not PREGUNTAS_PATH.exists():
        print(f"ERROR: no existe {PREGUNTAS_PATH}", file=sys.stderr)
        sys.exit(1)

    preguntas = json.loads(PREGUNTAS_PATH.read_text(encoding="utf-8"))
    print(f"Cargadas {len(preguntas)} preguntas desde {PREGUNTAS_PATH.name}")

    token = login()
    resultados = recolectar_respuestas(token, preguntas)
    evaluar_faithfulness(resultados)
    exportar_y_resumir(resultados)


if __name__ == "__main__":
    main()
