"""
Comparación de recuperación entre índices (correcciones del jurado, paso 3).

Dos fases:

1) `volcar`: corre DENTRO del contenedor con el índice activo (EMBEDDING_MODEL +
   CHROMA_COLLECTION). Para las 50 preguntas de preguntas_ragas.json y un set de
   preguntas fuera del libro, llama a la búsqueda de producción
   (search_fragments, mismos filtros asignatura/grado y mismo TOP_K) SIN corte por
   distancia, y guarda páginas + distancias del top-5. El corte se aplica
   después, para poder calibrar el umbral de cada modelo.

     docker compose exec backend python scripts/evaluacion/comparar_recuperacion.py volcar minilm
     docker compose exec -e EMBEDDING_MODEL=intfloat/multilingual-e5-small \
         -e CHROMA_COLLECTION=libros_texto_e5 backend \
         python scripts/evaluacion/comparar_recuperacion.py volcar e5

2) `analizar`: calibra los umbrales de e5 por equivalencia de percentiles con los
   de MiniLM y calcula Hit@5 y MRR (global, por asignatura y por tipo).

     python scripts/evaluacion/comparar_recuperacion.py analizar minilm e5

Paso 3b (30 preguntas de 5to–3ro Básico): `volcar <etiqueta> <archivo>` con
preguntas_recuperacion_otros_grados.json y `analizar minilm_3b e5_3b`; agrupa
además por grado (nombre de la tesis) y por grado · asignatura.

Hit@5: al menos un fragmento devuelto (tras el corte MAX_DISTANCE) cae en
paginas_ref. MRR: 1/rango del primer fragmento que cae en paginas_ref (0 si ninguno).
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

DIR = Path(__file__).resolve().parent
PREGUNTAS = DIR / "preguntas_ragas.json"

# Fuera de los libros de 4to (deben quedar SIN contexto relevante).
FUERA_DEL_LIBRO = [
    "¿Quién ganó el mundial de fútbol de 2022?",
    "¿Cómo se programa en Python?",
    "¿Qué es la inflación económica?",
    "¿Cuál es la capital de Francia?",
    "¿Quién escribió Don Quijote de la Mancha?",
    "¿Cómo se juega al ajedrez?",
    "¿Qué es la criptomoneda bitcoin?",
    "¿Cuántos jugadores tiene un equipo de baloncesto?",
    "¿Qué es la diabetes?",
    "¿Cómo funciona un motor de automóvil?",
    "¿Cuál es la receta de los tamales?",
    "¿Quién fue el primer presidente de Guatemala?",
]
ASIGNATURAS_4TO = ["Ciencias Naturales", "Matemáticas"]

# Umbrales de producción de MiniLM (app/modules/rag/search.py).
UMBRALES_MINILM = {"UMBRAL_ESTRICTO": 0.85, "UMBRAL_AMPLIO": 1.5, "MAX_DISTANCE": 1.55}
# Umbrales de e5 fijados en el código (rag/search.py), calibrados el 2026-11-10 con 50 preguntas.
UMBRALES_E5 = {"UMBRAL_ESTRICTO": 0.29, "UMBRAL_AMPLIO": 0.47, "MAX_DISTANCE": 0.49}
MIN_FRAGMENTOS_AMPLIO = 2


def volcar(etiqueta: str, archivo: str = str(PREGUNTAS)) -> None:
    sys.path.insert(0, str(DIR.parents[1]))  # backend/
    from app.modules.rag import search
    from app.modules.ingesta.embeddings import MODEL_NAME
    from app.modules.ingesta.indexer import COLLECTION_NAME

    search.MAX_DISTANCE = float("inf")  # el corte se aplica en `analizar`

    def top(q, asig, grado):
        return [{"page_num": f["page_num"], "distance": f["distance"]}
                for f in search.search_fragments(q, asignatura=asig, grado=grado)]

    preguntas = json.loads(Path(archivo).read_text())
    preguntas = preguntas["preguntas"] if isinstance(preguntas, dict) else preguntas  # 3b: {"semilla", "preguntas"}
    salida = {
        "modelo": MODEL_NAME, "coleccion": COLLECTION_NAME, "top_k": search.TOP_K,
        "en_libro": [{**p, "top": top(p["pregunta"], p["asignatura"], p["grado"])} for p in preguntas],
        "fuera": [{"pregunta": q, "asignatura": a, "top": top(q, a, "4to Primaria")}
                  for q in FUERA_DEL_LIBRO for a in ASIGNATURAS_4TO],
    }
    (DIR / f"recuperacion_{etiqueta}.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1))
    print(f"recuperacion_{etiqueta}.json: {MODEL_NAME} / {COLLECTION_NAME}")


def paginas(ref: str) -> set[int]:
    a, _, b = ref.partition("-")
    return set(range(int(a), int(b or a) + 1))


def relevante(top: list[dict], u: dict) -> bool:
    d = [f["distance"] for f in top]
    return any(x <= u["UMBRAL_ESTRICTO"] for x in d) or \
        sum(x <= u["UMBRAL_AMPLIO"] for x in d) >= MIN_FRAGMENTOS_AMPLIO


def metricas(datos: dict, u: dict) -> dict:
    grupos = defaultdict(list)
    for p in datos["en_libro"]:
        ref = paginas(p["paginas_ref"])
        kept = [f for f in p["top"] if f["distance"] <= u["MAX_DISTANCE"]]
        rr = next((1 / (i + 1) for i, f in enumerate(kept) if f["page_num"] in ref), 0.0)
        fila = (rr > 0, rr, relevante(p["top"], u))
        gt = p.get("grado_tesis", p["grado"])
        for g in ("global", p["asignatura"], p["tipo"], gt, f"{gt} · {p['asignatura']}"):
            grupos[g].append(fila)
    res = {g: {"n": len(v), "hit@5": round(sum(x[0] for x in v) / len(v), 3),
               "mrr": round(sum(x[1] for x in v) / len(v), 3),
               "aceptadas": round(sum(x[2] for x in v) / len(v), 3)}
           for g, v in grupos.items()}
    fuera = datos["fuera"]
    res["fuera_del_libro_rechazadas"] = round(sum(not relevante(p["top"], u) for p in fuera) / len(fuera), 3)
    return res


def cuantil(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, int(round(q * len(s))) - 1))]


def calibrar(base: dict, otro: dict) -> dict:
    """Umbral equivalente: mismo percentil de la distribución conjunta de
    distancias top-5 (preguntas del libro + fuera del libro)."""
    def todas(d):
        return [f["distance"] for p in d["en_libro"] + d["fuera"] for f in p["top"]]
    db, do = todas(base), todas(otro)
    out = {}
    for k, t in UMBRALES_MINILM.items():
        q = sum(x <= t for x in db) / len(db)
        out[k] = round(cuantil(do, q), 4)
        out[f"{k}_percentil"] = round(q, 4)
    return out


def analizar(et_base: str, et_otro: str, sufijo: str = "") -> None:
    base = json.loads((DIR / f"recuperacion_{et_base}.json").read_text())
    otro = json.loads((DIR / f"recuperacion_{et_otro}.json").read_text())
    cal = calibrar(base, otro)  # control: recalibración con los datos actuales
    u_otro = UMBRALES_E5
    resumen = {
        "calibracion": cal,
        et_base: {"modelo": base["modelo"], "umbrales": UMBRALES_MINILM, **metricas(base, UMBRALES_MINILM)},
        et_otro: {"modelo": otro["modelo"], "umbrales": u_otro, **metricas(otro, u_otro)},
        f"{et_otro}_sin_corte": metricas(otro, {k: float("inf") for k in UMBRALES_MINILM}),
    }
    (DIR / f"comparacion_{et_base}_vs_{et_otro}{sufijo}.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1))
    print(json.dumps(resumen, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"volcar": volcar, "analizar": analizar}[sys.argv[1]](*sys.argv[2:])
