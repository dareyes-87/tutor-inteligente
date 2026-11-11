"""
Preguntas de recuperación para los demás grados (correcciones del jurado, paso 3b).

Para cada libro de 5to y 6to Primaria y 1ro–3ro Básico (Matemáticas y Ciencias
Naturales; en la BD local los grados de básico se llaman 7mo/8vo/9no Básico):
  1. Reconstruye el texto de cada página desde la tabla `fragmento` (el mismo OCR
     que está indexado), quitando el solapamiento entre chunks.
  2. Filtra páginas de contenido: no las primeras 5 (portada, créditos, índice),
     ≥ 700 caracteres, sin pinta de índice, y con mayoría de fragmentos que NO son
     ejercicios (es_ejercicio_del_libro).
  3. Elige al azar 3 páginas por libro con SEMILLA fija (una por tipo: conceptual,
     factual, procedimental).
  4. Pide a un modelo (no gpt-oss-120b, que es el evaluador) una pregunta de
     estudiante del grado SIN copiar frases ni títulos de la página, y si el tema
     sigue en la página siguiente (→ paginas_ref "p-(p+1)").
  5. Mide el solapamiento literal (máx. palabras seguidas en común con la página)
     para que la revisión docente vea si la pregunta copia el texto.

Uso (dentro del contenedor backend):
    python scripts/evaluacion/generar_preguntas_otros_grados.py --max-usd 0.5

Salidas: preguntas_recuperacion_otros_grados.csv (con columna "revisión docente")
y preguntas_recuperacion_otros_grados.json.
"""
import argparse
import asyncio
import csv
import json
import random
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR.parents[1]))  # backend/
sys.path.insert(0, str(DIR.parent))      # scripts/ (costos_llm)

from sqlalchemy import select  # noqa: E402
from together import Together  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models.asignatura import Asignatura  # noqa: E402
from app.models.fragmento import Fragmento  # noqa: E402
from app.models.grado import Grado  # noqa: E402
from app.models.libro import LibroTexto  # noqa: E402
from app.modules.rag.search import es_ejercicio_del_libro  # noqa: E402
from costos_llm import Presupuesto, agregar_argumento_max_usd  # noqa: E402

SEMILLA = 20261110
MODELO = "deepseek-ai/DeepSeek-V4.1-Flash"
GRADOS = ["5to Primaria", "6to Primaria", "7mo Básico", "8vo Básico", "9no Básico"]
NOMBRE_TESIS = {"7mo Básico": "1ro Básico", "8vo Básico": "2do Básico", "9no Básico": "3ro Básico"}
TIPOS = ["conceptual", "factual", "procedimental"]
DESCRIPCION_TIPO = {
    "conceptual": "conceptual (pregunta qué es algo o por qué ocurre)",
    "factual": "factual (pregunta por un dato, una lista, un nombre o una clasificación concreta)",
    "procedimental": "procedimental (pregunta cómo se hace algo o cómo funciona un proceso)",
}
SISTEMA = (
    "Eres un estudiante de {grado} en Guatemala que estudia {asignatura}. Te muestran una página "
    "de tu libro (texto OCR, puede tener ruido) y la página siguiente. Escribe UNA pregunta "
    "{tipo} que le harías a tu tutor y que se responda con el contenido de la PRIMERA página. "
    "Reglas: escríbela con tus propias palabras, como habla un estudiante de {grado}; NO copies "
    "frases, títulos ni subtítulos de la página (máximo 3 palabras seguidas iguales al texto); no "
    "menciones la página ni el libro; una sola pregunta, de una línea. Indica también si el tema "
    "de tu pregunta continúa en la página siguiente. Responde SOLO con JSON: "
    '{{"pregunta": "...", "continua_en_siguiente": true|false}}'
)


def unir_chunks(textos: list[str]) -> str:
    """Concatena los chunks de una página quitando el solapamiento (≤ 300 chars)."""
    out = textos[0] if textos else ""
    for t in textos[1:]:
        k = next((k for k in range(min(300, len(out), len(t)), 19, -1) if out.endswith(t[:k])), 0)
        out += ("" if k else "\n") + t[k:]
    return out


def norm_palabras(s: str) -> list[str]:
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")
    return re.findall(r"[a-zñ0-9]+", s)


def solapamiento(pregunta: str, pagina: str) -> int:
    """Máximo de palabras consecutivas de la pregunta que aparecen tal cual en la página."""
    q, p = norm_palabras(pregunta), " " + " ".join(norm_palabras(pagina)) + " "
    mejor = 0
    for i in range(len(q)):
        for j in range(i + mejor + 1, len(q) + 1):
            if " " + " ".join(q[i:j]) + " " in p:
                mejor = j - i
            else:
                break
    return mejor


def es_contenido(num: int, texto: str, chunks: list[str]) -> bool:
    if num <= 5 or len(texto) < 700:
        return False
    cabeza = texto[:250].lower()
    if "índice" in cabeza or "indice" in cabeza or "contenido" in cabeza[:40]:
        return False
    lineas = [l for l in texto.splitlines() if l.strip()]
    if lineas and sum(bool(re.search(r"\d+\s*$", l)) for l in lineas) / len(lineas) > 0.4:
        return False  # mayoría de líneas que terminan en nº de página: índice
    return sum(not es_ejercicio_del_libro(c) for c in chunks) / len(chunks) > 0.5


async def cargar_libros() -> list[dict]:
    async with AsyncSessionLocal() as db:
        libros = (await db.execute(
            select(LibroTexto.id, Asignatura.nombre, Grado.nombre)
            .join(Asignatura, LibroTexto.asignatura_id == Asignatura.id)
            .join(Grado, LibroTexto.grado_id == Grado.id)
            .where(Grado.nombre.in_(GRADOS)).order_by(LibroTexto.id)
        )).all()
        salida = []
        for libro_id, asignatura, grado in libros:
            filas = (await db.execute(
                select(Fragmento.numero_pagina, Fragmento.contenido_texto)
                .where(Fragmento.libro_id == libro_id).order_by(Fragmento.numero_pagina, Fragmento.id)
            )).all()
            por_pagina = defaultdict(list)
            for n, t in filas:
                por_pagina[n].append(t)
            paginas = {n: unir_chunks(cs) for n, cs in por_pagina.items()}
            elegibles = sorted(n for n, t in paginas.items() if es_contenido(n, t, por_pagina[n]))
            salida.append({"libro_id": libro_id, "asignatura": asignatura, "grado": grado,
                           "paginas": paginas, "elegibles": elegibles})
    return salida


def generar_pregunta(cliente, lb: dict, tipo: str, pag: int) -> dict:
    texto, siguiente = lb["paginas"][pag], lb["paginas"].get(pag + 1, "")
    grado_tesis = NOMBRE_TESIS.get(lb["grado"], lb["grado"])
    for _ in range(3):  # el razonamiento a veces agota max_tokens y devuelve content=None
        r = cliente.chat.completions.create(
            model=MODELO, temperature=0.7, max_tokens=4000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SISTEMA.format(grado=grado_tesis, asignatura=lb["asignatura"],
                                                             tipo=DESCRIPCION_TIPO[tipo])},
                {"role": "user", "content": f"PRIMERA PÁGINA:\n{texto[:4000]}\n\nPÁGINA SIGUIENTE:\n{siguiente[:2500]}"},
            ],
        )
        try:
            d = json.loads(r.choices[0].message.content or "")
            if d.get("pregunta"):
                break
        except json.JSONDecodeError:
            pass
    else:
        raise RuntimeError(f"sin pregunta válida tras 3 intentos (libro {lb['libro_id']}, p{pag})")
    continua = bool(d.get("continua_en_siguiente")) and bool(siguiente)
    x = {
        "pregunta": d["pregunta"].strip(), "asignatura": lb["asignatura"], "grado": lb["grado"],
        "grado_tesis": grado_tesis, "tipo": tipo, "libro_id": lb["libro_id"],
        "pagina_elegida": pag, "paginas_ref": f"{pag}-{pag + 1}" if continua else str(pag),
        "solapamiento_max_palabras": solapamiento(d["pregunta"], texto + " " + siguiente),
        "extracto_pagina": re.sub(r"\s+", " ", texto[:350]),
    }
    print(f"  {tipo:13} p{x['paginas_ref']:7} solap={x['solapamiento_max_palabras']} {x['pregunta']}", flush=True)
    return x


def guardar(resultado: list[dict]) -> None:
    (DIR / "preguntas_recuperacion_otros_grados.json").write_text(
        json.dumps({"semilla": SEMILLA, "modelo": MODELO, "preguntas": resultado}, ensure_ascii=False, indent=1))
    with open(DIR / "preguntas_recuperacion_otros_grados.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["n", "grado", "grado (nombre en la BD)", "asignatura", "tipo", "libro_id", "página elegida",
                    "paginas_ref", "pregunta", "solapamiento (máx. palabras seguidas iguales)",
                    "extracto de la página (OCR)", "reemplazo", "revisión docente"])
        for n, x in enumerate(resultado, 1):
            w.writerow([n, x["grado_tesis"], x["grado"], x["asignatura"], x["tipo"], x["libro_id"],
                        x["pagina_elegida"], x["paginas_ref"], x["pregunta"], x["solapamiento_max_palabras"],
                        x["extracto_pagina"], x.get("reemplazo", ""), ""])


def main():
    ap = argparse.ArgumentParser()
    agregar_argumento_max_usd(ap, defecto=0.5)
    ap.add_argument("--reemplazar", default="",
                    help='"n:página,..." regenera solo esas preguntas (nº 1-30 del CSV) con la página indicada')
    ap.add_argument("--motivo", default="", help="motivo del reemplazo (queda en el JSON/CSV)")
    args = ap.parse_args()

    libros = asyncio.run(cargar_libros())
    cliente = Together(api_key=settings.TOGETHER_API_KEY)
    presupuesto = Presupuesto(max_usd=args.max_usd)
    presupuesto.instrumentar(cliente)

    if args.reemplazar:
        # Las páginas nuevas se eligen fuera del script: orden aleatorio de las elegibles del
        # libro con random.Random(f"{SEMILLA}:{libro_id}") y la primera que sea TEORÍA tras
        # revisión manual (ver docs/tesis/resultados_correcciones_jurado.md).
        resultado = json.loads((DIR / "preguntas_recuperacion_otros_grados.json").read_text())["preguntas"]
        por_id = {lb["libro_id"]: lb for lb in libros}
        for par in args.reemplazar.split(","):
            n, pag = (int(v) for v in par.split(":"))
            viejo = resultado[n - 1]
            nuevo = generar_pregunta(cliente, por_id[viejo["libro_id"]], viejo["tipo"], pag)
            nuevo["reemplazo"] = f"reemplaza p{viejo['pagina_elegida']} «{viejo['pregunta']}» ({args.motivo})"
            resultado[n - 1] = nuevo
    else:
        rng = random.Random(SEMILLA)
        resultado = []
        for lb in libros:
            elegidas = rng.sample(lb["elegibles"], 3)
            print(f"libro {lb['libro_id']} {lb['asignatura']} {lb['grado']}: {len(lb['elegibles'])} "
                  f"páginas elegibles de {len(lb['paginas'])}; elegidas {elegidas}", flush=True)
            resultado += [generar_pregunta(cliente, lb, tipo, pag) for tipo, pag in zip(TIPOS, elegidas)]

    guardar(resultado)
    presupuesto.imprimir_resumen()


if __name__ == "__main__":
    # Autocomprobación de los helpers (sin BD ni LLM).
    assert unir_chunks(["hola mundo cruel y frío del norte", "cruel y frío del norte y del sur"]) == \
        "hola mundo cruel y frío del norte y del sur"
    assert unir_chunks(["sin solape aquí", "otro texto"]) == "sin solape aquí\notro texto"
    assert solapamiento("¿Qué es la fotosíntesis de las plantas?", "La fotosíntesis de las plantas verdes") == 5  # «la fotosíntesis de las plantas»
    main()
