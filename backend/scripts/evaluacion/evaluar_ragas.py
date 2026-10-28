"""
Evaluación RAGAS (Faithfulness) del tutor inteligente contra producción.

Consulta el endpoint temporal POST /chat/preguntar-debug (que devuelve la
respuesta del tutor + los contextos textuales recuperados por el RAG) para las
50 preguntas de `preguntas_ragas.json`, y calcula la métrica Faithfulness de
RAGAS usando Together AI (Llama-3.3-70B) como LLM evaluador.

NOTA (2026-10-28): el endpoint POST /chat/preguntar-debug ya NO existe; se
eliminó al terminar la evaluación (los resultados están en este directorio).
Su última versión vive en el commit e25142c (chat/router.py::preguntar_debug
y el parámetro `debug` de chat/service.py::procesar_pregunta). Para volver a
correr este script hay que restaurarlo desde ese commit.

--- Requisitos (instalar en un venv LOCAL, NO en la imagen del backend) ---
    pip install ragas langchain-together requests pandas

--- Variables de entorno ---
    TOGETHER_API_KEY   (obligatoria) clave de Together AI para el LLM evaluador
    API_URL            (opcional) URL de la API; por defecto la de Railway
    ADMIN_USERNAME     (opcional, default "admin")
    ADMIN_PASSWORD     (opcional, default "admin123")

--- Uso ---
    TOGETHER_API_KEY=xxx python backend/scripts/evaluacion/evaluar_ragas.py

    Con respuestas ya recolectadas en local (recolectar_respuestas_local.py,
    que reemplaza al endpoint eliminado) en otra carpeta, sin tocar las de
    la configuración B:
    TOGETHER_API_KEY=xxx python backend/scripts/evaluacion/evaluar_ragas.py \
        --salida backend/scripts/evaluacion/ragas_2026-10_deepseek --max-usd 1

    Opciones: --evaluador (modelo de Together), --max-usd (tope de gasto del
    evaluador; tokens y costo por llamada se registran con scripts/costos_llm.py).

Salidas (en --salida; por defecto la misma carpeta del script):
    resultados_ragas.csv    una fila por pregunta con su faithfulness
    resumen_ragas.json      agregados (global, por asignatura, por tipo, umbral)
"""
import argparse
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
sys.path.insert(0, str(DIR.parent))  # costos_llm.py
PREGUNTAS_PATH = DIR / "preguntas_ragas.json"
# Se reasignan en main() según --salida.
CACHE_PATH = DIR / "respuestas_cache.json"
CSV_PATH = DIR / "resultados_ragas.csv"
RESUMEN_PATH = DIR / "resumen_ragas.json"

# --- Configuración ---
API_URL = os.environ.get(
    "API_URL", "https://tutor-inteligente-production.up.railway.app"
).rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "admin123")
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "")
# Configuración B usó meta-llama/Llama-3.3-70B-Instruct-Turbo (ya no es serverless
# en Together desde 2026-10). Por defecto ahora GLM-5.3 (no es de la familia del
# tutor, DeepSeek: evita autoevaluación). Se cambia con --evaluador.
MODELO_EVALUADOR = "zai-org/GLM-5.3"

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


def _callback_costos(presupuesto):
    """Callback de LangChain que registra los tokens de cada llamada del evaluador."""
    from langchain_core.callbacks import BaseCallbackHandler

    class Costos(BaseCallbackHandler):
        def on_llm_end(self, response, **kwargs):
            salida = response.llm_output or {}
            uso = salida.get("token_usage") or {}
            presupuesto.registrar(
                salida.get("model_name") or MODELO_EVALUADOR,
                uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0),
            )

    return Costos()


def evaluar_faithfulness(resultados: list[dict], presupuesto=None) -> None:
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
        callbacks=[_callback_costos(presupuesto)] if presupuesto else None,
    )
    evaluator_llm = LangchainLLMWrapper(llm)

    def evaluar_lote(registros):
        dataset = EvaluationDataset(samples=[
            SingleTurnSample(
                user_input=r["pregunta"],
                response=r["respuesta_tutor"],
                retrieved_contexts=r["retrieved_contexts"],
            )
            for r in registros
        ])
        df = evaluate(
            dataset=dataset,
            metrics=[Faithfulness(llm=evaluator_llm)],
            llm=evaluator_llm,
        ).to_pandas()
        # La columna puede llamarse 'faithfulness'; buscarla de forma tolerante.
        col = "faithfulness" if "faithfulness" in df.columns else df.columns[-1]
        return list(df[col])

    print(f"\nEvaluando Faithfulness de {len(evaluables)} preguntas con {MODELO_EVALUADOR}...")
    if presupuesto is None:
        scores = evaluar_lote(evaluables)
    else:
        # Una pregunta a la vez para poder cortar en el tope de gasto (--max-usd).
        from costos_llm import PresupuestoAgotado
        scores = []
        for r in evaluables:
            try:
                presupuesto.verificar()
            except PresupuestoAgotado as e:
                print(f"DETENIDO: {e}", file=sys.stderr)
                break
            scores += evaluar_lote([r])
            print(f"  {len(scores)}/{len(evaluables)} faithfulness={scores[-1]}  (${presupuesto.total_usd:.4f})", flush=True)
        for r in evaluables[len(scores):]:
            r["status"] = "ERROR"  # sin evaluar por tope: fuera de promedios
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
        "modelo_evaluador": MODELO_EVALUADOR,
    }
    # Comparación justa: configuración B sobre las MISMAS preguntas (si se evalúa en otra carpeta).
    csv_b = DIR / "resultados_ragas.csv"
    if CSV_PATH != csv_b and csv_b.exists():
        with open(csv_b, encoding="utf-8") as fh:
            b = {f["pregunta"]: f["faithfulness_score"] for f in csv.DictReader(fh)}
        mismas = [float(b[r["pregunta"]]) for r in resultados if b.get(r["pregunta"], "ERROR") not in ("ERROR", "")]
        resumen["faithfulness_config_b_mismas_preguntas"] = _promedio(mismas)
        print(f"Config. B (Llama-70B evaluador) en las mismas preguntas: {fmt(resumen['faithfulness_config_b_mismas_preguntas'])}")
    with open(RESUMEN_PATH, "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2)
    print(f"Resumen: {RESUMEN_PATH}")


def main() -> None:
    global CACHE_PATH, CSV_PATH, RESUMEN_PATH, MODELO_EVALUADOR
    parser = argparse.ArgumentParser(description="Evaluación RAGAS (Faithfulness)")
    parser.add_argument("--salida", default=str(DIR), help="carpeta de cache y resultados")
    parser.add_argument("--evaluador", default=MODELO_EVALUADOR)
    parser.add_argument("--max-usd", type=float, default=None, help="tope de gasto del evaluador (USD)")
    args = parser.parse_args()
    salida = Path(args.salida).resolve()
    CACHE_PATH = salida / "respuestas_cache.json"
    CSV_PATH = salida / "resultados_ragas.csv"
    RESUMEN_PATH = salida / "resumen_ragas.json"
    MODELO_EVALUADOR = args.evaluador
    if salida != DIR and (CSV_PATH.exists() or RESUMEN_PATH.exists()):
        print(f"ERROR: ya hay resultados en {salida}; no se sobrescriben.", file=sys.stderr)
        sys.exit(1)

    if not TOGETHER_API_KEY:
        print("ERROR: define TOGETHER_API_KEY (LLM evaluador de RAGAS).", file=sys.stderr)
        sys.exit(1)
    if not PREGUNTAS_PATH.exists():
        print(f"ERROR: no existe {PREGUNTAS_PATH}", file=sys.stderr)
        sys.exit(1)

    preguntas = json.loads(PREGUNTAS_PATH.read_text(encoding="utf-8"))
    print(f"Cargadas {len(preguntas)} preguntas desde {PREGUNTAS_PATH.name}")

    # Cache: si ya se recolectaron las respuestas del tutor en una corrida
    # previa, se reutilizan y NO se vuelve a consultar el API (las 50 llamadas
    # al tutor son la parte lenta/costosa). Borra respuestas_cache.json para
    # forzar una recolección nueva.
    if CACHE_PATH.exists():
        resultados = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        print(f"Cargadas {len(resultados)} respuestas desde cache (no se consultó el API)")
    else:
        print("Consultando API... (las respuestas se guardarán en cache)")
        token = login()
        resultados = recolectar_respuestas(token, preguntas)
        CACHE_PATH.write_text(
            json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Respuestas guardadas en cache: {CACHE_PATH}")

    presupuesto = None
    if args.max_usd is not None:
        from costos_llm import Presupuesto
        presupuesto = Presupuesto(args.max_usd, api_key=TOGETHER_API_KEY)
    evaluar_faithfulness(resultados, presupuesto)
    exportar_y_resumir(resultados)
    if presupuesto:
        presupuesto.imprimir_resumen()


if __name__ == "__main__":
    main()
