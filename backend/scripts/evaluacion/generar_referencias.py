"""
Borradores de respuestas de referencia para RAGAS (correcciones del jurado, paso 4).

Para cada una de las 50 preguntas toma el texto OCR de sus `paginas_ref`
(paginas_4to_ocr.json, salida de process_pdf() de producción sobre los PDFs de
4to) y pide a un modelo de Together un borrador de 2 a 4 oraciones usando SOLO
ese texto. El modelo NO debe ser el evaluador del paso 5.

Uso (dentro del contenedor backend):
    python scripts/evaluacion/generar_referencias.py --max-usd 1

Salidas: referencias_ragas.json y referencias_para_revisar.csv (con la columna
vacía "corrección docente" para la revisión de Daniel).
"""
import argparse
import csv
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR.parents[1]))  # backend/
sys.path.insert(0, str(DIR.parent))      # scripts/ (costos_llm)

from together import Together  # noqa: E402

from app.config import settings  # noqa: E402
from costos_llm import Presupuesto, agregar_argumento_max_usd  # noqa: E402

MODELO = "deepseek-ai/DeepSeek-V4.1-Flash"

SISTEMA = (
    "Eres un docente de primaria en Guatemala. Escribe la respuesta de referencia a una "
    "pregunta de un estudiante de {grado}, en español, de 2 a 4 oraciones, con vocabulario "
    "adecuado a su edad. Usa ÚNICAMENTE la información del texto del libro que se te da; "
    "no agregues datos que no estén en él. Si el texto no alcanza para responder, responde "
    "exactamente: SIN INFORMACIÓN EN LAS PÁGINAS. Devuelve solo la respuesta, sin títulos "
    "ni citas de página."
)


def paginas(ref: str) -> list[int]:
    a, _, b = ref.partition("-")
    return list(range(int(a), int(b or a) + 1))


def main():
    ap = argparse.ArgumentParser()
    agregar_argumento_max_usd(ap, defecto=1.0)
    ap.add_argument("--solo", default="", help="nº de pregunta (1-50) separados por coma: regenera solo esas")
    args = ap.parse_args()
    solo = {int(n) for n in args.solo.split(",") if n}

    preguntas = json.loads((DIR / "preguntas_ragas.json").read_text())
    texto_libro = json.loads((DIR / "paginas_4to_ocr.json").read_text())

    cliente = Together(api_key=settings.TOGETHER_API_KEY)
    presupuesto = Presupuesto(max_usd=args.max_usd)
    presupuesto.instrumentar(cliente)

    previas = json.loads((DIR / "referencias_ragas.json").read_text()) if solo else []
    salida = []
    for i, p in enumerate(preguntas, 1):
        if solo and i not in solo:
            salida.append({**previas[i - 1], **p})  # conserva la referencia previa
            continue
        presupuesto.verificar()
        libro = texto_libro[p["asignatura"]]
        texto = "\n\n".join(f"[Página {n}]\n{libro.get(str(n), '')}" for n in paginas(p["paginas_ref"]))
        r = cliente.chat.completions.create(
            model=MODELO,
            temperature=0.2,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": SISTEMA.format(grado=p["grado"])},
                {"role": "user", "content": f"TEXTO DEL LIBRO:\n{texto}\n\nPREGUNTA: {p['pregunta']}"},
            ],
        )
        borrador = (r.choices[0].message.content or "").strip()
        salida.append({**p, "referencia": borrador, "modelo_borrador": MODELO})
        print(f"{i:2d}/50 {p['pregunta'][:60]} -> {borrador[:80]}", flush=True)

    (DIR / "referencias_ragas.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1))
    with open(DIR / "referencias_para_revisar.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["n", "pregunta", "asignatura", "grado", "tipo", "páginas", "borrador", "corrección docente"])
        for n, s in enumerate(salida, 1):
            w.writerow([n, s["pregunta"], s["asignatura"], s["grado"], s["tipo"], s["paginas_ref"], s["referencia"], ""])
    presupuesto.imprimir_resumen()


if __name__ == "__main__":
    main()
