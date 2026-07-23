"""Compara respuestas del fine-tuned v1, el fine-tuned v2 (Modal/vLLM) y el modelo
base (Together AI, Qwen2.5-7B-Instruct-Turbo) usando el mismo system prompt de
producción y el mismo contexto RAG real (extraído de scripts/debug/).

Uso: python backend/scripts/modal_finetuned/comparar.py
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))
from app.modules.chat.prompts import build_context_prompt, build_system_prompt  # noqa: E402

MODAL_V1_URL = "https://dareyes-87--tutor-finetuned-server-server.us-east.modal.direct/v1/chat/completions"
MODAL_V2_URL = "https://dareyes-87--tutor-finetuned-server-v2-server.us-east.modal.direct/v1/chat/completions"
MODAL_API_KEY = os.environ["MODAL_FINETUNED_API_KEY"]
TOGETHER_URL = "https://api.together.xyz/v1/chat/completions"
TOGETHER_KEY = os.environ["TOGETHER_API_KEY"]
BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct-Turbo"


def leer_fragmento(path, marcador, n_lineas=25):
    with open(path, encoding="utf-8") as f:
        lineas = f.readlines()
    for i, linea in enumerate(lineas):
        if marcador.lower() in linea.lower():
            inicio = max(0, i - 2)
            return "".join(lineas[inicio : inicio + n_lineas])
    return ""


CASOS = [
    {
        "nombre": "Ciencias — célula",
        "grado": "4to Primaria",
        "asignatura": "Ciencias Naturales",
        "pregunta": "¿Qué es la célula?",
        "contexto_txt": leer_fragmento(
            "scripts/debug/fragmentos_ciencias_4to.txt", "La célula"
        ),
    },
    {
        "nombre": "Matemáticas — conjunto",
        "grado": "4to Primaria",
        "asignatura": "Matemáticas",
        "pregunta": "¿Qué es un conjunto?",
        "contexto_txt": leer_fragmento(
            "scripts/debug/fragmentos_matematicas_4to.txt", "conjunto A"
        ),
    },
    {
        "nombre": "Fuera de contexto — capital de Francia",
        "grado": "4to Primaria",
        "asignatura": "Ciencias Naturales",
        "pregunta": "¿Cuál es la capital de Francia?",
        "contexto_txt": leer_fragmento(
            "scripts/debug/fragmentos_ciencias_4to.txt", "La célula"
        ),
    },
    {
        "nombre": "Guía de ejercicio — Matemáticas",
        "grado": "6to Primaria",
        "asignatura": "Matemáticas",
        "pregunta": "¿Cómo hago el ejercicio de la página 29?",
        "contexto_txt": leer_fragmento(
            "scripts/debug/fragmentos_matematicas_4to.txt", "conjunto A"
        ),
    },
]


def preguntar(url, headers, model, messages, timeout=30, plazo_total=240, intervalo=10):
    """Modal responde 503 fail-fast (no encola) mientras el contenedor está
    despertando de un cold start, en vez de hacer esperar al cliente. Reintenta
    cada `intervalo` segundos hasta agotar `plazo_total` (igual que chat_finetuned()
    en producción) en vez de rendirse al primer 503."""
    inicio = time.monotonic()
    while True:
        try:
            resp = requests.post(
                url,
                headers=headers,
                json={"model": model, "messages": messages, "max_tokens": 400, "temperature": 0.7},
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            transcurrido = time.monotonic() - inicio
            if transcurrido + intervalo >= plazo_total:
                raise
            time.sleep(intervalo)


def main():
    resultados = []
    for caso in CASOS:
        system = build_system_prompt(caso["grado"], caso["asignatura"])
        contexto = build_context_prompt([{"page_num": "?", "text": caso["contexto_txt"]}])
        messages = [
            {"role": "system", "content": f"{system}\n\n{contexto}"},
            {"role": "user", "content": caso["pregunta"]},
        ]

        print(f"\n{'=' * 70}\n{caso['nombre']}\n{'=' * 70}")

        modal_headers = {"Authorization": f"Bearer {MODAL_API_KEY}"}

        try:
            r_v1 = preguntar(MODAL_V1_URL, modal_headers, "tutor-finetuned", messages)
        except Exception as e:
            r_v1 = f"[ERROR: {e}]"
        print(f"\n--- FINE-TUNED v1 (563 ejemplos) ---\n{r_v1}")

        try:
            r_v2 = preguntar(MODAL_V2_URL, modal_headers, "tutor-finetuned-v2", messages)
        except Exception as e:
            r_v2 = f"[ERROR: {e}]"
        print(f"\n--- FINE-TUNED v2 (990 ejemplos) ---\n{r_v2}")

        try:
            r_base = preguntar(
                TOGETHER_URL,
                {"Authorization": f"Bearer {TOGETHER_KEY}"},
                BASE_MODEL,
                messages,
            )
        except Exception as e:
            r_base = f"[ERROR: {e}]"
        print(f"\n--- BASE (Together) ---\n{r_base}")

        resultados.append({"caso": caso["nombre"], "fine_tuned_v1": r_v1, "fine_tuned_v2": r_v2, "base": r_base})

    out_path = os.path.join(os.path.dirname(__file__), "comparacion_resultado_v1_v2.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado en {out_path}")


if __name__ == "__main__":
    main()
