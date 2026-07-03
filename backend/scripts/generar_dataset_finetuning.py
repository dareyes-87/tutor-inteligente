"""
Generador del dataset de fine-tuning (QLoRA) para el tutor pedagógico.

Formato de salida: JSONL de Together AI, una línea por ejemplo con `messages`
(system / user / assistant). El `system` es SIEMPRE `build_system_prompt(grado,
asignatura)` (el mismo de producción) para reforzar el comportamiento pedagógico.

DECISIÓN DE DISEÑO (documentada): el CONTEXTO recuperado (fragmentos del libro) se
incluye en el turno `user`, ANTES de la pregunta. Así el `system` queda exactamente
igual a `build_system_prompt` (como se pidió) y, a la vez, las citas "(página X)" de
la respuesta están respaldadas por texto que el modelo SÍ ve — no se enseña a citar
páginas inventadas. En inferencia el RAG cumple ese mismo rol.

Este script NO lanza fine-tuning ni sube nada a Together AI. Solo escribe .jsonl
locales para revisión.

Uso (dentro del contenedor backend, PYTHONPATH=/app):
    python scripts/generar_dataset_finetuning.py reales
    python scripts/generar_dataset_finetuning.py sinteticos --n 25
"""
import argparse
import asyncio
import json
import os
import re
import time

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.llm.client import llm_client
from app.models.asignatura import Asignatura
from app.models.conversacion import Conversacion
from app.models.fragmento import Fragmento
from app.models.grado import Grado
from app.models.leccion import Leccion
from app.models.mensaje import Mensaje, RolMensaje
from app.models.usuario import Usuario
from app.modules.chat.prompts import build_system_prompt
from app.modules.chat.service import _citas_validas, _es_rechazo, _paginas_citadas

# Modelo potente (ya usado para generar la ruta) para crear preguntas y respuestas ideales.
MODELO_GEN = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
# Precio aproximado Together AI Llama-3.3-70B-Instruct-Turbo (USD por 1M tokens, mezcla in+out).
PRECIO_USD_POR_1M = 0.88

OUT_DIR = os.path.join(os.path.dirname(__file__), "dataset_out")

# Etiquetas de grado para variar el registro en el lote sintético (el system prompt
# se adapta al string). Local solo tiene "1ro Basico", así que la variedad la damos aquí.
GRADOS_VARIADOS = ["4to Primaria", "5to Primaria", "6to Primaria", "8vo Básico"]

_uso_tokens = {"prompt": 0, "completion": 0, "llamadas": 0}


# --------------------------- helpers de formato ---------------------------

def _fmt_contexto(frags: list[dict]) -> str:
    """frags: [{text, page_num}] -> bloque de contexto legible."""
    partes = ["CONTEXTO DEL LIBRO (usa SOLO esta información para responder):"]
    for f in frags:
        partes.append(f"--- (página {f['page_num']}) ---\n{f['text']}")
    return "\n".join(partes)


def _ejemplo(grado, asignatura, contexto: str, pregunta: str, respuesta: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": build_system_prompt(grado, asignatura)},
            {"role": "user", "content": f"{contexto}\n\nPregunta del estudiante: {pregunta}"},
            {"role": "assistant", "content": respuesta},
        ]
    }


def _escribir_jsonl(nombre: str, ejemplos: list[dict]) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    ruta = os.path.join(OUT_DIR, nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        for ej in ejemplos:
            f.write(json.dumps(ej, ensure_ascii=False) + "\n")
    return ruta


def _gen_llama(messages: list[dict], max_tokens: int = 700, temperature: float = 0.4) -> str:
    resp = llm_client._client.chat.completions.create(
        model=MODELO_GEN, messages=messages, max_tokens=max_tokens, temperature=temperature
    )
    u = getattr(resp, "usage", None)
    if u is not None:
        _uso_tokens["prompt"] += getattr(u, "prompt_tokens", 0) or 0
        _uso_tokens["completion"] += getattr(u, "completion_tokens", 0) or 0
    _uso_tokens["llamadas"] += 1
    return resp.choices[0].message.content.strip()


# --------------------------- TAREA 1: reales ---------------------------

async def extraer_reales() -> tuple[list[dict], dict]:
    """Reconstruye ejemplos de conversaciones reales con grounding válido."""
    async with AsyncSessionLocal() as db:
        asignaturas = {a.id: a.nombre for a in (await db.execute(select(Asignatura))).scalars()}
        grados = {g.id: g.nombre for g in (await db.execute(select(Grado))).scalars()}
        usuarios = {
            u.id: grados.get(u.grado_id)
            for u in (await db.execute(select(Usuario))).scalars()
        }
        # Índice (libro_id, página) -> primer texto de esa página (para reconstruir contexto).
        frag_index: dict[tuple, str] = {}
        for f in (await db.execute(select(Fragmento))).scalars():
            frag_index.setdefault((f.libro_id, f.numero_pagina), f.contenido_texto)

        convs = {c.id: c for c in (await db.execute(select(Conversacion))).scalars()}
        msgs = (
            await db.execute(
                select(Mensaje).order_by(
                    Mensaje.conversacion_id, Mensaje.fecha_creacion, Mensaje.id
                )
            )
        ).scalars().all()

    by_conv: dict[int, list] = {}
    for m in msgs:
        by_conv.setdefault(m.conversacion_id, []).append(m)

    ejemplos: list[dict] = []
    descartados = {"sin_referencias": 0, "rechazo": 0, "sin_pregunta": 0,
                   "sin_contexto_existente": 0, "citas_invalidas": 0}

    for cid, lista in by_conv.items():
        conv = convs.get(cid)
        if conv is None:
            continue
        asignatura = asignaturas.get(conv.asignatura_id)
        grado = usuarios.get(conv.estudiante_id)
        for i, m in enumerate(lista):
            if m.rol != RolMensaje.asistente:
                continue
            refs = (m.referencias or {}).get("fragmentos") or []
            if not refs:
                descartados["sin_referencias"] += 1
                continue
            if _es_rechazo(m.contenido):
                descartados["rechazo"] += 1
                continue
            # Pregunta = mensaje de usuario inmediatamente anterior.
            pregunta = None
            for j in range(i - 1, -1, -1):
                if lista[j].rol == RolMensaje.usuario:
                    pregunta = lista[j].contenido
                    break
            if not pregunta:
                descartados["sin_pregunta"] += 1
                continue
            # Reconstruir contexto solo con fragmentos que AÚN existen.
            frags, vistos = [], set()
            for r in refs:
                key = (r.get("libro_id"), r.get("page_num"))
                if key in vistos:
                    continue
                vistos.add(key)
                txt = frag_index.get(key)
                if txt:
                    frags.append({"text": txt, "page_num": r.get("page_num")})
            if not frags:
                descartados["sin_contexto_existente"] += 1
                continue
            # Re-chequeo explícito de citas contra el contexto reconstruido.
            if not _citas_validas(m.contenido, frags):
                descartados["citas_invalidas"] += 1
                continue
            ejemplos.append(_ejemplo(grado, asignatura, _fmt_contexto(frags), pregunta, m.contenido))

    return ejemplos, descartados


# --------------------------- TAREA 2: sintéticos ---------------------------

async def _seeds_desde_lecciones(db, libro_id: int, cuantas: int) -> list[dict]:
    """Toma `cuantas` lecciones repartidas del libro y su contexto (fragmentos del rango)."""
    lecs = (
        await db.execute(
            select(Leccion).where(Leccion.libro_id == libro_id).order_by(Leccion.orden)
        )
    ).scalars().all()
    if not lecs:
        return []
    # Repartir uniformemente para cubrir temas distintos.
    paso = max(1, len(lecs) // cuantas)
    elegidas = lecs[::paso][:cuantas]

    seeds = []
    for lec in elegidas:
        rango = _parse_rango(lec.paginas)
        if rango is None:
            continue
        ini, fin = rango
        rows = (
            await db.execute(
                select(Fragmento)
                .where(
                    Fragmento.libro_id == libro_id,
                    Fragmento.numero_pagina >= ini,
                    Fragmento.numero_pagina <= fin,
                )
                .order_by(Fragmento.numero_pagina, Fragmento.id)
            )
        ).scalars().all()
        if not rows:
            continue
        # 2 fragmentos representativos, recortados, como contexto.
        frags = [{"text": r.contenido_texto[:600], "page_num": r.numero_pagina} for r in rows[:2]]
        seeds.append({"leccion": lec.nombre, "frags": frags})
    return seeds


def _parse_rango(paginas: str | None) -> tuple[int, int] | None:
    if not paginas:
        return None
    try:
        a, b = paginas.split("-")
        return int(a), int(b)
    except Exception:
        return None


def _generar_preguntas(tema: str, contexto: str, asignatura: str, n: int = 2) -> list[str]:
    sys = (
        "Eres un generador de datos para entrenar un tutor escolar de Guatemala. "
        "Devuelves SOLO JSON válido."
    )
    user = f"""A partir del siguiente contenido del libro de {asignatura} (tema: {tema}), inventa {n} preguntas REALISTAS que un estudiante de primaria haría al tutor. Mezcla: alguna conceptual y, si es {asignatura} de matemáticas, alguna sobre un ejercicio concreto que el estudiante está resolviendo.

CONTENIDO:
{contexto}

Responde SOLO con JSON: {{"preguntas": ["...", "..."]}}"""
    data = llm_client.generate_json(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_tokens=400,
        model=MODELO_GEN,
    )
    _uso_tokens["llamadas"] += 1  # generate_json no expone usage; contamos la llamada
    if not data or "preguntas" not in data:
        return []
    return [p for p in data["preguntas"] if isinstance(p, str)][:n]


def _generar_respuesta_ideal(grado: str, asignatura: str, contexto: str, pregunta: str) -> str:
    """Genera la respuesta 'ideal' con Llama-70B usando el system prompt REAL + refuerzo."""
    system = build_system_prompt(grado, asignatura)
    refuerzo = (
        "\n\nRECORDATORIO PARA ESTE EJEMPLO: sigue las reglas al pie de la letra. "
        "Cita solo páginas presentes en el contexto. Si es un ejercicio de matemáticas "
        "que el estudiante resuelve, NO des el resultado final: guía el siguiente paso."
    )
    user = f"{contexto}\n\nPregunta del estudiante: {pregunta}"
    return _gen_llama(
        [{"role": "system", "content": system + refuerzo}, {"role": "user", "content": user}],
        max_tokens=500,
        temperature=0.4,
    )


def _gold_cases() -> list[dict]:
    """Casos de oro hechos a mano (comportamiento correcto garantizado)."""
    ctx_frac = _fmt_contexto([{
        "page_num": 46,
        "text": ("Una fracción propia es aquella cuyo numerador es menor que el denominador, "
                 "como 2/5. Para sumar fracciones con el mismo denominador se suman los "
                 "numeradores y se conserva el denominador."),
    }])
    ctx_conj = _fmt_contexto([{
        "page_num": 1,
        "text": ("Cuando un elemento está dentro de un conjunto, decimos que pertenece (∈) al "
                 "conjunto; si no está, no pertenece (∉). Ejemplo: si A = {manzana, pera}, "
                 "entonces manzana ∈ A."),
    }])
    ctx_offtopic = _fmt_contexto([{
        "page_num": 12,
        "text": ("El sistema respiratorio permite el intercambio de gases. Los pulmones toman "
                 "oxígeno y expulsan dióxido de carbono."),
    }])
    return [
        # 1) Matemáticas: ejercicio en resolución -> guía, NO da el resultado.
        _ejemplo(
            "4to Primaria", "Matemáticas", ctx_frac,
            "Estoy resolviendo el ejercicio de la página 46 que dice sumar 2/5 + 1/5. ¿Cuál es la respuesta?",
            ("¡Buen trabajo por intentarlo! Fíjate en lo que dice el libro: cuando el "
             "denominador es el mismo, se suman solo los numeradores y el denominador se "
             "queda igual (página 46).\n\nEntonces, paso 1: ¿cuánto te da si sumas los "
             "numeradores 2 + 1? Cuéntame ese resultado y seguimos con el siguiente paso. 🐯"),
        ),
        # 2) Pertenencia de conjuntos -> usa ∈ correctamente.
        _ejemplo(
            "4to Primaria", "Matemáticas", ctx_conj,
            "¿Qué símbolo se usa cuando un elemento pertenece a un conjunto?",
            ("Cuando un elemento está dentro de un conjunto, decimos que pertenece y se "
             "escribe con el símbolo ∈ (página 1). Por ejemplo, si A = {manzana, pera}, "
             "entonces manzana ∈ A. Si NO está, usamos ∉. ¿Quieres que veamos un ejemplo "
             "con tus propios conjuntos?"),
        ),
        # 3) Fuera de contexto -> rechazo correcto, sin inventar.
        _ejemplo(
            "5to Primaria", "Ciencias Naturales", ctx_offtopic,
            "¿Quién ganó el Mundial de fútbol de 2022?",
            ("No encuentro información sobre eso en tus libros de clase. ¿Quieres "
             "preguntarme sobre los temas que estamos viendo en clase?"),
        ),
    ]


async def generar_sinteticos(n_objetivo: int) -> tuple[list[dict], dict]:
    async with AsyncSessionLocal() as db:
        asignaturas = {a.nombre: a.id for a in (await db.execute(select(Asignatura))).scalars()}
        # Libros locales: Ciencias (3) y Matemáticas (4).
        seeds_cn = await _seeds_desde_lecciones(db, 3, 4)
        seeds_mat = await _seeds_desde_lecciones(db, 4, 4)

    plan = [("Ciencias Naturales", s) for s in seeds_cn] + [("Matemáticas", s) for s in seeds_mat]

    ejemplos: list[dict] = []
    gi = 0
    for asignatura, seed in plan:
        if len(ejemplos) >= n_objetivo - len(_gold_cases()):
            break
        grado = GRADOS_VARIADOS[gi % len(GRADOS_VARIADOS)]
        gi += 1
        contexto = _fmt_contexto(seed["frags"])
        preguntas = _generar_preguntas(seed["leccion"], contexto, asignatura, n=2)
        for preg in preguntas:
            respuesta = _generar_respuesta_ideal(grado, asignatura, contexto, preg)
            ejemplos.append(_ejemplo(grado, asignatura, contexto, preg, respuesta))

    ejemplos.extend(_gold_cases())

    reporte = evaluar_calidad(ejemplos)
    return ejemplos, reporte


# --------------------------- TAREA 3: validación ---------------------------

def _frags_de_ejemplo(ej: dict) -> list[dict]:
    """Extrae [{page_num}] del contexto embebido en el turno user (para _citas_validas)."""
    user = ej["messages"][1]["content"]
    paginas = [int(p) for p in re.findall(r"página\s+(\d+)", user, re.IGNORECASE)]
    return [{"page_num": p} for p in paginas]


def evaluar_calidad(ejemplos: list[dict]) -> dict:
    problemas = {"citas_inventadas": [], "idioma_no_es": [], "posible_resultado_directo": [],
                 "euro_en_conjuntos": []}
    for idx, ej in enumerate(ejemplos):
        resp = ej["messages"][-1]["content"]
        user = ej["messages"][1]["content"]
        system = ej["messages"][0]["content"]
        # Citas: toda página citada debe estar en el contexto.
        if not _citas_validas(resp, _frags_de_ejemplo(ej)):
            problemas["citas_inventadas"].append(idx)
        # Idioma: detectar caracteres CJK (fuga de idioma).
        if re.search(r"[一-鿿]", resp):
            problemas["idioma_no_es"].append(idx)
        # Matemáticas: heurística de "resultado directo" en preguntas de ejercicio.
        es_mate = "matemática" in system.lower() or "matematica" in system.lower()
        parece_ejercicio = bool(re.search(r"cu[aá]nto|resultado|resuelv|calcul|suma|resta|\d\s*[+\-x×]\s*\d", user, re.IGNORECASE))
        if es_mate and parece_ejercicio and re.search(r"=\s*-?\d+(?:[.,/]\d+)?\b", resp):
            problemas["posible_resultado_directo"].append(idx)
        # Conjuntos: no debe aparecer € donde se habla de pertenencia.
        if ("pertenece" in user.lower() or "conjunto" in user.lower()) and "€" in resp:
            problemas["euro_en_conjuntos"].append(idx)
    return problemas


# --------------------------- main ---------------------------

def _costo_estimado() -> dict:
    total = _uso_tokens["prompt"] + _uso_tokens["completion"]
    return {
        "llamadas": _uso_tokens["llamadas"],
        "tokens_prompt": _uso_tokens["prompt"],
        "tokens_completion": _uso_tokens["completion"],
        "tokens_total": total,
        "costo_usd": round(total / 1_000_000 * PRECIO_USD_POR_1M, 4),
    }


async def main():
    parser = argparse.ArgumentParser(description="Genera el dataset de fine-tuning del tutor.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("reales")
    ps = sub.add_parser("sinteticos")
    ps.add_argument("--n", type=int, default=25)
    args = parser.parse_args()

    t0 = time.time()
    if args.cmd == "reales":
        ejemplos, descartados = await extraer_reales()
        ruta = _escribir_jsonl("reales.jsonl", ejemplos)
        print(f"\n=== TAREA 1 · ejemplos reales ===")
        print(f"Ejemplos válidos: {len(ejemplos)}  -> {ruta}")
        print(f"Descartados: {json.dumps(descartados, ensure_ascii=False)}")
    elif args.cmd == "sinteticos":
        ejemplos, problemas = await generar_sinteticos(args.n)
        ruta = _escribir_jsonl("sinteticos_prueba.jsonl", ejemplos)
        dt = time.time() - t0
        print(f"\n=== TAREA 2/3 · lote sintético ===")
        print(f"Ejemplos generados: {len(ejemplos)}  -> {ruta}")
        print(f"Tiempo: {dt:.1f}s")
        print(f"Uso Llama-70B: {json.dumps(_costo_estimado(), ensure_ascii=False)}")
        print("Problemas detectados:")
        for k, v in problemas.items():
            print(f"  {k}: {len(v)}  {v if v else ''}")


if __name__ == "__main__":
    asyncio.run(main())
