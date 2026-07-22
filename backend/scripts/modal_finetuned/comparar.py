"""Compara 3 respuestas del modelo fine-tuned (Modal/vLLM) vs el modelo base
(Together AI, Qwen2.5-7B-Instruct-Turbo) usando el mismo system prompt de
producción y el mismo contexto RAG real (extraído de scripts/debug/).

Uso: python backend/scripts/modal_finetuned/comparar.py
"""
import json
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))
from app.modules.chat.prompts import build_context_prompt, build_system_prompt  # noqa: E402

MODAL_URL = "https://dareyes-87--tutor-finetuned-server-server.us-east.modal.direct/v1/chat/completions"
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
]


def preguntar(url, headers, model, messages, timeout=120):
    resp = requests.post(
        url,
        headers=headers,
        json={"model": model, "messages": messages, "max_tokens": 400, "temperature": 0.7},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


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

        try:
            r_ft = preguntar(MODAL_URL, {}, "tutor-finetuned", messages)
        except Exception as e:
            r_ft = f"[ERROR: {e}]"
        print(f"\n--- FINE-TUNED ---\n{r_ft}")

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

        resultados.append({"caso": caso["nombre"], "fine_tuned": r_ft, "base": r_base})

    out_path = os.path.join(os.path.dirname(__file__), "comparacion_resultado.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado en {out_path}")


if __name__ == "__main__":
    main()
