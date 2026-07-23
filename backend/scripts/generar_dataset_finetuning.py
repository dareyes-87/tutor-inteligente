"""
Generador del dataset de fine-tuning (QLoRA) para el tutor pedagógico.

Formato Together AI: JSONL con `messages` (system / user / assistant). El `system`
es SIEMPRE `build_system_prompt(grado, asignatura)` (el de producción); el CONTEXTO
recuperado va en el turno `user` para que las citas "(página X)" estén respaldadas
por texto visible (no se enseña a citar páginas inventadas).

Pipeline:
  - reales:   conversaciones reales con grounding válido, LIMPIADAS (sin meta-frases
              del RAG) y deduplicadas.
  - completo: sintéticos generados EN PARALELO con Llama-70B, con estilo VÍVIDO, más
              casos de oro; cada sintético pasa por un LLM-JUEZ (checklist a-e). El
              resultado se divide 90/10 (train/val) estratificado por asignatura+grado.

NO lanza fine-tuning ni sube nada a Together AI.

Uso (contenedor backend, PYTHONPATH=/app):
    python scripts/generar_dataset_finetuning.py reales
    python scripts/generar_dataset_finetuning.py completo --objetivo 600
"""
import argparse
import asyncio
import json
import os
import random
import re
import time

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.llm.client import llm_client
from app.models.asignatura import Asignatura
from app.models.conversacion import Conversacion
from app.models.fragmento import Fragmento
from app.models.grado import Grado
from app.models.mensaje import Mensaje, RolMensaje
from app.models.usuario import Usuario
from app.modules.chat.prompts import build_system_prompt
from app.modules.chat.service import _citas_validas, _es_rechazo, RESPUESTA_FUERA_DE_CONTEXTO
from app.modules.rag.search import es_ejercicio_del_libro

MODELO_GEN = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
PRECIO_USD_POR_1M = 0.88
CONCURRENCIA = 4  # conservador para no gatillar rate-limiting de Together AI
REINTENTOS = 4
RATIO_VAL = 0.10
SEED = 42

OUT_DIR = os.path.join(os.path.dirname(__file__), "dataset_out")
GRADOS_VARIADOS = ["4to Primaria", "5to Primaria", "6to Primaria", "8vo Básico"]
# Frases que revelan la "plomería" del RAG y no deben aparecer en la respuesta.
META_FRASES = ("fragmento", "proporcionad", "el contexto", "los textos", "según el texto")

_uso = {"prompt": 0, "completion": 0, "llamadas": 0}
_sem = asyncio.Semaphore(CONCURRENCIA)


# --------------------------- infra LLM (async) ---------------------------

def _sync_chat(messages, max_tokens, temperature):
    # Reintentos con backoff para absorber rate-limiting (429) transitorio.
    for intento in range(REINTENTOS):
        try:
            resp = llm_client._client.chat.completions.create(
                model=MODELO_GEN, messages=messages, max_tokens=max_tokens, temperature=temperature
            )
            u = getattr(resp, "usage", None)
            if u is not None:
                _uso["prompt"] += getattr(u, "prompt_tokens", 0) or 0
                _uso["completion"] += getattr(u, "completion_tokens", 0) or 0
            _uso["llamadas"] += 1
            return resp.choices[0].message.content.strip()
        except Exception:
            if intento == REINTENTOS - 1:
                raise
            time.sleep(3 * (intento + 1))  # 3s, 6s, 9s


async def _achat(messages, max_tokens=500, temperature=0.5) -> str | None:
    async with _sem:
        try:
            return await asyncio.to_thread(_sync_chat, messages, max_tokens, temperature)
        except Exception as e:  # resiliencia: una llamada fallida no tumba el lote
            print(f"    [warn] llamada LLM falló: {e}")
            return None


def _parse_json(raw: str | None):
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# --------------------------- formato ---------------------------

def _fmt_contexto(frags: list[dict]) -> str:
    partes = ["CONTEXTO DEL LIBRO (usa SOLO esta información para responder):"]
    for f in frags:
        partes.append(f"--- (página {f['page_num']}) ---\n{f['text']}")
    return "\n".join(partes)


def _ejemplo(grado, asignatura, contexto, pregunta, respuesta) -> dict:
    return {
        "messages": [
            {"role": "system", "content": build_system_prompt(grado, asignatura)},
            {"role": "user", "content": f"{contexto}\n\nPregunta del estudiante: {pregunta}"},
            {"role": "assistant", "content": respuesta},
        ],
        # metadatos internos para estratificar/reportar (se quitan al exportar)
        "_meta": {"grado": grado, "asignatura": asignatura},
    }


def _exportar(ej: dict) -> dict:
    return {"messages": ej["messages"]}


def _escribir_jsonl(nombre: str, ejemplos: list[dict]) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    ruta = os.path.join(OUT_DIR, nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        for ej in ejemplos:
            f.write(json.dumps(_exportar(ej), ensure_ascii=False) + "\n")
    return ruta


# --------------------------- TAREA 1: reales (limpias) ---------------------------

async def extraer_reales() -> tuple[list[dict], dict]:
    async with AsyncSessionLocal() as db:
        asignaturas = {a.id: a.nombre for a in (await db.execute(select(Asignatura))).scalars()}
        grados = {g.id: g.nombre for g in (await db.execute(select(Grado))).scalars()}
        usuarios = {u.id: grados.get(u.grado_id) for u in (await db.execute(select(Usuario))).scalars()}
        frag_index: dict[tuple, str] = {}
        for f in (await db.execute(select(Fragmento))).scalars():
            frag_index.setdefault((f.libro_id, f.numero_pagina), f.contenido_texto)
        convs = {c.id: c for c in (await db.execute(select(Conversacion))).scalars()}
        msgs = (
            await db.execute(select(Mensaje).order_by(
                Mensaje.conversacion_id, Mensaje.fecha_creacion, Mensaje.id))
        ).scalars().all()

    by_conv: dict[int, list] = {}
    for m in msgs:
        by_conv.setdefault(m.conversacion_id, []).append(m)

    ejemplos: list[dict] = []
    desc = {"sin_referencias": 0, "rechazo": 0, "sin_pregunta": 0,
            "sin_contexto_existente": 0, "citas_invalidas": 0, "meta_frase": 0, "duplicado": 0}
    vistos_preg: set[str] = set()

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
                desc["sin_referencias"] += 1
                continue
            if _es_rechazo(m.contenido):
                desc["rechazo"] += 1
                continue
            # mejora 1a: descartar respuestas que filtran plomería del RAG
            if any(mp in m.contenido.lower() for mp in META_FRASES):
                desc["meta_frase"] += 1
                continue
            pregunta = None
            for j in range(i - 1, -1, -1):
                if lista[j].rol == RolMensaje.usuario:
                    pregunta = lista[j].contenido
                    break
            if not pregunta:
                desc["sin_pregunta"] += 1
                continue
            # mejora 1b: dedup por pregunta normalizada
            clave = re.sub(r"\s+", " ", pregunta.strip().lower())
            if clave in vistos_preg:
                desc["duplicado"] += 1
                continue
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
                desc["sin_contexto_existente"] += 1
                continue
            if not _citas_validas(m.contenido, frags):
                desc["citas_invalidas"] += 1
                continue
            vistos_preg.add(clave)
            ejemplos.append(_ejemplo(grado, asignatura, _fmt_contexto(frags), pregunta, m.contenido))

    return ejemplos, desc


# --------------------------- TAREA 2: seeds + generación vívida ---------------------------

async def _seeds_desde_paginas(db, libro_id, asignatura, max_seeds) -> list[dict]:
    rows = (
        await db.execute(select(Fragmento).where(Fragmento.libro_id == libro_id)
                         .order_by(Fragmento.numero_pagina, Fragmento.id))
    ).scalars().all()
    by_page: dict[int, Fragmento] = {}
    for r in rows:
        by_page.setdefault(r.numero_pagina, r)
    pages = sorted(by_page)
    if len(pages) > max_seeds:  # repartir uniformemente por todo el libro
        step = len(pages) / max_seeds
        pages = [pages[int(i * step)] for i in range(max_seeds)]
    seeds = []
    for idx, p in enumerate(pages):
        txt = (by_page[p].contenido_texto or "").strip()
        if len(txt) < 60:  # saltar fragmentos ruidosos/muy cortos
            continue
        # 2 páginas de contexto (p y la siguiente disponible): más grounding y menos
        # citas inventadas que con una sola página.
        frags = [{"text": txt[:550], "page_num": p}]
        for q in sorted(by_page):
            if q > p and len((by_page[q].contenido_texto or "").strip()) >= 60:
                frags.append({"text": by_page[q].contenido_texto.strip()[:550], "page_num": q})
                break
        seeds.append({"asignatura": asignatura, "frags": frags})
    return seeds


async def _generar_preguntas(seed) -> list[str]:
    asignatura = seed["asignatura"]
    extra = ("Incluye UNA sobre un ejercicio concreto que el estudiante está resolviendo "
             "(para que el tutor tenga que guiar paso a paso). " if "atem" in asignatura else "")
    sys = "Generas datos para entrenar un tutor escolar guatemalteco. Devuelves SOLO JSON válido."
    user = f"""Contenido del libro de {asignatura}:
{_fmt_contexto(seed['frags'])}

Inventa 3 preguntas REALISTAS y VARIADAS que un niño de primaria haría al tutor sobre este contenido: una conceptual ("qué es"/"por qué"), una de aplicación a la vida real, y una más. {extra}Responde SOLO JSON: {{"preguntas":["...","...","..."]}}"""
    data = _parse_json(await _achat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_tokens=350, temperature=0.8))
    if not data or "preguntas" not in data:
        return []
    return [p for p in data["preguntas"] if isinstance(p, str) and len(p) > 5][:3]


# Pool de analogías para VARIAR el estilo (evita que el modelo repita siempre "el
# mercado"). Se elige una al azar por ejemplo y se prohíbe el resto explícitamente.
ANALOGIAS = [
    "la milpa y la siembra de maíz", "un partido de fútbol en la cancha del barrio",
    "los animales de una finca", "la cocina de la abuela (tamales, tortillas, frijoles)",
    "el río y la lluvia en invierno", "la tienda de la esquina", "una fiesta patronal del pueblo",
    "los pájaros haciendo su nido", "el huerto escolar", "las canicas y los juegos del recreo",
    "armar un rompecabezas", "repartir un pan dulce entre hermanos", "el bus que va llenándose de gente",
    "una mochila con sus útiles", "las estrellas en el cielo de noche",
]
# Aperturas variadas para que no todas empiecen con "¡Hola!".
APERTURAS = ["con una pregunta al estudiante", "yendo directo a la idea principal",
             "con un dato sorprendente", "planteando una mini-situación", "con un saludo breve y distinto"]


async def _generar_respuesta(grado, asignatura, contexto, pregunta) -> str | None:
    system = build_system_prompt(grado, asignatura)
    analogia = random.choice(ANALOGIAS)
    apertura = random.choice(APERTURAS)
    refuerzo = (
        "\n\nADEMÁS DE SEGUIR TODAS LAS REGLAS ANTERIORES (grounding estricto, citar páginas, "
        "en Matemáticas guiar sin dar el resultado final, notación exacta), la respuesta debe ser "
        "VÍVIDA y MEMORABLE para un niño. Para ESTA respuesta:\n"
        f"- Usa UNA analogía concreta relacionada con: {analogia}. NO uses el mercado ni repitas "
        "analogías genéricas.\n"
        f"- Empieza {apertura}: NO empieces con '¡Hola!' ni con 'Imagina que...'. Varía la apertura.\n"
        "- Habla directo al estudiante con calidez; NUNCA menciones que tienes 'fragmentos' o 'contexto'.")
    user = f"{contexto}\n\nPregunta del estudiante: {pregunta}"
    return await _achat(
        [{"role": "system", "content": system + refuerzo}, {"role": "user", "content": user}],
        max_tokens=520, temperature=0.8)


# --------------------------- LLM-juez (checklist a-e) ---------------------------

_MOTIVOS_CANON = ("meta_frase_rag", "resultado_directo_mate", "notacion_incorrecta",
                  "plano_robotico", "cita_inconsistente",
                  "imprecision_conceptual", "analogia_incoherente")
_MOTIVO_LETRA = dict(zip("abcde", _MOTIVOS_CANON[:5]))


def _norm_motivo(m: str) -> str:
    """Normaliza el código de motivo del juez a uno canónico (el modelo varía el formato)."""
    s = str(m).strip().lower()
    s = re.sub(r"^\(?([a-e])\)?[\s:.\-]+", "", s)  # quita prefijos "(a) ", "b) ", "c: "
    for canon in _MOTIVOS_CANON:
        if canon in s:
            return canon
    if s in _MOTIVO_LETRA:  # quedó solo la letra
        return _MOTIVO_LETRA[s]
    return "otro"


def _paginas_contexto(ej: dict) -> set[int]:
    """Páginas presentes en el CONTEXTO del turno user (marcadores '--- (página N) ---')."""
    user = ej["messages"][1]["content"]
    return {int(n) for n in re.findall(r"---\s*\(página\s+(\d+)\)\s*---", user)}


def _gates_deterministicos(ej: dict) -> list[str]:
    """Chequeos EXACTOS (no LLM): citas contra el contexto real y meta-frases del RAG.
    El LLM juzga mal estos casos mecánicos, así que se resuelven en código."""
    from app.modules.chat.service import _paginas_citadas  # import local para evitar ciclos
    motivos = []
    resp = ej["messages"][-1]["content"]
    if any(mp in resp.lower() for mp in META_FRASES):
        motivos.append("meta_frase_rag")
    disponibles = _paginas_contexto(ej)
    citadas = _paginas_citadas(resp)
    if citadas and not all(p in disponibles for p in citadas):
        motivos.append("cita_inconsistente")
    return motivos


async def _juzgar(ej: dict) -> dict:
    """LLM-juez SOLO para lo semántico/subjetivo (b, c, d). Lo mecánico (a, e) ya
    lo filtran los gates determinísticos."""
    m = {x["role"]: x["content"] for x in ej["messages"]}
    sys = ("Eres un evaluador ESTRICTO de calidad de ejemplos para entrenar un tutor infantil "
           "guatemalteco. Devuelves SOLO JSON válido.")
    user = f"""Evalúa la RESPUESTA del tutor contra el checklist.

[SYSTEM DEL TUTOR]
{m['system'][:400]}...

[CONTEXTO + PREGUNTA]
{m['user']}

[RESPUESTA DEL TUTOR A EVALUAR]
{m['assistant']}

CHECKLIST (marca motivo si FALLA). Sé estricto con los conceptuales, indulgente con lo cosmético (ignora typos y fraseo raro que no cambian el significado):
- imprecision_conceptual: la explicación del PROCEDIMIENTO o del concepto es incorrecta o ENGAÑOSA, o induciría a un error si el estudiante la generaliza a otro caso —AUNQUE el resultado numérico final sea correcto—. Pregúntate: "¿esta explicación del procedimiento es correcta y no induce a error si se generaliza?". Ej. FALSO: "multiplicar un decimal por 10 es agregar un cero a la derecha".
- analogia_incoherente: usa una analogía que NO mapea lógicamente al concepto (suena bonita pero no ilustra la idea real). Ej. FALSO: "los divisores de 24 son los caramelos que puedes comprar con 24 centavos".
- resultado_directo_mate: es Matemáticas y da el resultado final de un ejercicio que el estudiante está resolviendo (debió guiar paso a paso). NO apliques esto a preguntas conceptuales.
- notacion_incorrecta: usa notación matemática errónea (p. ej. € en vez de ∈ para pertenencia).
- plano_robotico: es correcto pero PLANO/aburrido; no suena a un buen maestro (sin vida, sin analogía memorable, sin calidez).

NO rechaces por: typos menores (p. ej. "blockadeador"), ni fraseo un poco raro que no cambia el significado.
Responde SOLO JSON usando EXACTAMENTE esos códigos en "motivos".
Formato: {{"aprobado": true|false, "motivos": ["codigo", ...]}}  (aprobado=false si hay al menos un motivo; motivos=[] si aprobado=true)."""
    data = _parse_json(await _achat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_tokens=180, temperature=0.0))
    if not data or "aprobado" not in data:
        return {"aprobado": False, "motivos": ["juez_sin_respuesta"]}
    return {"aprobado": bool(data["aprobado"]), "motivos": data.get("motivos", []) or []}


# --------------------------- casos de oro (vívidos, a mano) ---------------------------

def _gold_cases() -> list[dict]:
    ctx_frac = _fmt_contexto([{"page_num": 46, "text": (
        "Una fracción propia tiene el numerador menor que el denominador, como 2/5. Para sumar "
        "fracciones con el mismo denominador se suman los numeradores y se conserva el denominador.")}])
    ctx_conj = _fmt_contexto([{"page_num": 1, "text": (
        "Cuando un elemento está dentro de un conjunto, decimos que pertenece (∈) al conjunto; si "
        "no está, no pertenece (∉). Ejemplo: si A = {manzana, pera}, entonces manzana ∈ A.")}])
    ctx_off = _fmt_contexto([{"page_num": 12, "text": (
        "El sistema respiratorio permite el intercambio de gases: los pulmones toman oxígeno y "
        "expulsan dióxido de carbono.")}])
    return [
        _ejemplo("4to Primaria", "Matemáticas", ctx_frac,
                 "Estoy resolviendo el ejercicio de la página 46 que dice sumar 2/5 + 1/5. ¿Cuál es la respuesta?",
                 ("¡Vas muy bien! Imagínate que 2/5 son 2 tortillas de un canasto que tiene 5, y 1/5 es "
                  "1 tortilla más del mismo canasto. Como el canasto es el mismo (el denominador 5 no "
                  "cambia), solo contamos las tortillas: se suman los numeradores y el 5 se queda igual "
                  "(página 46).\n\nEntonces, paso 1: ¿cuántas tortillas tienes si juntas 2 + 1? Dime ese "
                  "número y seguimos. 🐯")),
        _ejemplo("4to Primaria", "Matemáticas", ctx_conj,
                 "¿Qué símbolo se usa cuando un elemento pertenece a un conjunto?",
                 ("Cuando algo está DENTRO de un conjunto decimos que pertenece, y se escribe con el "
                  "símbolo ∈ (página 1). Es como tu mochila: si tu lápiz está adentro, el lápiz ∈ mochila. "
                  "Si lo dejaste en casa, entonces lápiz ∉ mochila. ¿Quieres que armemos un conjunto con "
                  "las cosas de tu lonchera?")),
        _ejemplo("5to Primaria", "Ciencias Naturales", ctx_off,
                 "¿Quién ganó el Mundial de fútbol de 2022?",
                 ("No encuentro información sobre eso en tus libros de clase. ¿Quieres preguntarme sobre "
                  "los temas que estamos viendo en clase?")),
    ]


# --------------------------- CATEGORÍAS NUEVAS 4-8 (dataset v2) ---------------------------
# Extienden el dataset original (563) con 437 ejemplos más en 5 categorías nuevas.
# Reutilizan build_system_prompt/_fmt_contexto/seeds reales; cada categoría tiene su
# propio gate determinístico + checklist de juez adaptado (ver _juzgar_v2).


def _ejemplo_multiturno(grado, asignatura, contexto, turnos: list[tuple[str, str]]) -> dict:
    """turnos: lista de (pregunta_usuario, respuesta_asistente) en orden. El contexto
    se antepone SOLO al primer turno (como en producción: el RAG se recupera una vez
    por conversación en este dataset controlado, no por turno)."""
    messages = [{"role": "system", "content": build_system_prompt(grado, asignatura)}]
    for i, (preg, resp) in enumerate(turnos):
        contenido_user = f"{contexto}\n\nPregunta del estudiante: {preg}" if i == 0 else preg
        messages.append({"role": "user", "content": contenido_user})
        messages.append({"role": "assistant", "content": resp})
    return {"messages": messages, "_meta": {"grado": grado, "asignatura": asignatura}}


async def _juzgar_v2(ej: dict, checklist: str) -> dict:
    """Juez LLM genérico parametrizado por checklist (categorías 4,5,7,8 del dataset v2).
    La categoría 6 reutiliza el `_juzgar` original (mismo tipo de ejemplo que el v1)."""
    turnos = [m for m in ej["messages"] if m["role"] != "system"]
    transcript = "\n\n".join(f"[{m['role'].upper()}]\n{m['content']}" for m in turnos)
    sys = ("Eres un evaluador ESTRICTO de calidad de ejemplos para entrenar un tutor infantil "
           "guatemalteco. Devuelves SOLO JSON válido.")
    user = f"""Evalúa este ejemplo de entrenamiento contra el checklist.

[CONVERSACIÓN]
{transcript}

CHECKLIST (marca motivo si FALLA):
{checklist}

Responde SOLO JSON: {{"aprobado": true|false, "motivos": ["..."]}} (aprobado=false si hay al menos un motivo)."""
    data = _parse_json(await _achat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_tokens=200, temperature=0.0))
    if not data or "aprobado" not in data:
        return {"aprobado": False, "motivos": ["juez_sin_respuesta"]}
    return {"aprobado": bool(data["aprobado"]), "motivos": data.get("motivos", []) or []}


# --- Categoría 4: rechazo correcto ---

async def _generar_pregunta_fuera_tema(asignatura: str) -> str | None:
    sys = "Generas datos para entrenar un tutor escolar. Devuelves SOLO JSON válido."
    tipo = random.choice([
        "una pregunta de historia o geografía (fuera de la materia actual)",
        "una pregunta de un tema de otro grado que NO está en este contenido",
        "una pregunta personal al tutor (no académica)",
        "una pregunta de otra asignatura distinta a la actual",
    ])
    user = (f"Inventa UNA pregunta que un niño le haría a su tutor de {asignatura}, pero que sea "
            f"{tipo}, de modo que el tutor NO pueda responderla con el libro de {asignatura}. "
            'Responde SOLO JSON: {"pregunta": "..."}')
    data = _parse_json(await _achat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_tokens=120, temperature=0.9))
    return data.get("pregunta") if data else None


async def _generar_rechazo(asignatura: str, pregunta: str) -> str | None:
    sys = ("Eres el Tutor Tigre, un tutor escolar guatemalteco. Un estudiante te preguntó algo "
           "que NO está en su libro de clase. Respondes con calidez, sin regañar, redirigiendo "
           "al estudiante hacia lo que SÍ pueden ver juntos. Devuelves SOLO JSON válido.")
    user = (f'El estudiante preguntó: "{pregunta}"\n\n'
            f"Esa pregunta NO está en su libro de {asignatura}. Escribe una respuesta breve "
            "(1-2 oraciones) que RECHACE responderla —sin dar ningún dato real sobre el tema de "
            f"la pregunta— y redirija al estudiante a preguntar sobre los temas de {asignatura} "
            "que sí están en su libro. Varía la redacción entre ejemplos, no uses siempre la misma "
            "frase. NUNCA respondas ni insinúes la respuesta a la pregunta original. "
            'Responde SOLO JSON: {"respuesta": "..."}')
    data = _parse_json(await _achat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_tokens=150, temperature=0.9))
    return data.get("respuesta") if data else None


def _generar_insistencia() -> str:
    return random.choice([
        "Pero de verdad quiero saber, dime aunque no esté en el libro",
        "¿Y tú no sabes la respuesta?",
        "Ay porfa, solo esta vez",
        "Bueno pero dame una pista aunque sea",
    ])


async def _categoria4_rechazo(n: int) -> list[dict]:
    """~20% de los ejemplos son de 2 turnos: el estudiante insiste tras el rechazo y
    el tutor sostiene la misma negativa (regla 7 de REGLAS_BASE)."""
    async with AsyncSessionLocal() as db:
        seeds_mate = await _seeds_desde_paginas(db, 4, "Matemáticas", max(2, n))
        seeds_cn = await _seeds_desde_paginas(db, 3, "Ciencias Naturales", max(2, n))
    seeds = (seeds_mate + seeds_cn) * 2  # margen: cada seed puede fallar en cualquier paso
    random.shuffle(seeds)
    seeds = seeds[: n * 3]

    preguntas = await asyncio.gather(*[_generar_pregunta_fuera_tema(s["asignatura"]) for s in seeds])
    tareas = [(s, p) for s, p in zip(seeds, preguntas) if p]
    respuestas = await asyncio.gather(*[_generar_rechazo(s["asignatura"], p) for s, p in tareas])
    validos = [(s, p, r) for (s, p), r in zip(tareas, respuestas) if r]

    # ~20% de dos turnos: el estudiante insiste y el tutor sostiene el rechazo (regla 7 de
    # REGLAS_BASE), pero con una SEGUNDA respuesta generada aparte (no reusar texto verbatim,
    # que se lee robótico y el juez lo marca como tono_negativo).
    idx_multiturno = [i for i in range(len(validos)) if random.random() < 0.2]
    insistencias = {i: _generar_insistencia() for i in idx_multiturno}
    segundas = await asyncio.gather(*[
        _generar_rechazo(validos[i][0]["asignatura"], f"{validos[i][1]} (insistiendo: {insistencias[i]})")
        for i in idx_multiturno
    ])
    segunda_por_idx = dict(zip(idx_multiturno, segundas))

    ejemplos = []
    for i, (s, pregunta, respuesta) in enumerate(validos):
        grado = random.choice(GRADOS_VARIADOS)
        contexto = _fmt_contexto(s["frags"])
        if segunda_por_idx.get(i):
            ejemplos.append(_ejemplo_multiturno(grado, s["asignatura"], contexto, [
                (pregunta, respuesta),
                (insistencias[i], segunda_por_idx[i]),
            ]))
        else:
            ejemplos.append(_ejemplo(grado, s["asignatura"], contexto, pregunta, respuesta))
    return ejemplos[:n]


def _gate_rechazo(ej: dict) -> list[str]:
    """Un rechazo correcto no debe citar páginas (no debe haber respondido con el libro)."""
    motivos = []
    for m in ej["messages"]:
        if m["role"] != "assistant":
            continue
        if re.search(r"p[aá]gina\s+\d+", m["content"], re.IGNORECASE):
            motivos.append("rechazo_cita_pagina")
        if any(mp in m["content"].lower() for mp in META_FRASES):
            motivos.append("meta_frase_rag")
    return motivos


# --- Categoría 5: enumeración fiel al libro ---

async def _detectar_lista(seed) -> dict | None:
    sys = "Analizas contenido de libros de texto. Devuelves SOLO JSON válido."
    user = f"""Contenido:
{_fmt_contexto(seed['frags'])}

¿Este contenido presenta una ENUMERACIÓN clara de elementos (lista de tipos, categorías, pasos, \
propiedades, etc.)? Si SÍ: escribe la pregunta que un estudiante haría para pedir esa lista, y \
copia los ítems TAL CUAL aparecen en el texto (sin parafrasear, sin agregar ítems que no estén). \
Si NO hay una enumeración clara, responde tiene_lista=false.

Responde SOLO JSON: {{"tiene_lista": true|false, "pregunta": "...", "items": ["...", "..."]}}"""
    data = _parse_json(await _achat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_tokens=400, temperature=0.3))
    if not data or not data.get("tiene_lista") or not data.get("items"):
        return None
    return {"pregunta": data.get("pregunta"), "items": data["items"]}


async def _generar_respuesta_enumeracion(grado, asignatura, contexto, pregunta, items) -> str | None:
    system = build_system_prompt(grado, asignatura)
    refuerzo = (
        "\n\nPara ESTA respuesta: presenta la lista de forma clara (puedes numerarla), usando "
        "ÚNICAMENTE los ítems dados abajo, SIN agregar ejemplos propios ni ítems que no estén en "
        f"la lista. No repitas el mismo ítem dos veces.\nÍtems a usar (tal cual, no los cambies): {items}")
    user = f"{contexto}\n\nPregunta del estudiante: {pregunta}"
    return await _achat(
        [{"role": "system", "content": system + refuerzo}, {"role": "user", "content": user}],
        max_tokens=400, temperature=0.5)


async def _pool_seeds_enumeracion() -> list[dict]:
    """Pool de páginas candidatas (no todas tienen una enumeración real; _detectar_lista
    filtra vía LLM en _generar_lote_enumeracion). Tope alto: todas las páginas indexadas."""
    async with AsyncSessionLocal() as db:
        seeds_mate = await _seeds_desde_paginas(db, 4, "Matemáticas", 500)
        seeds_cn = await _seeds_desde_paginas(db, 3, "Ciencias Naturales", 500)
    seeds = seeds_mate + seeds_cn
    random.shuffle(seeds)
    return seeds


async def _generar_lote_enumeracion(seeds_lote: list[dict]) -> list[dict]:
    detecciones = await asyncio.gather(*[_detectar_lista(s) for s in seeds_lote])
    tareas = [(s, d) for s, d in zip(seeds_lote, detecciones) if d]

    grados = [random.choice(GRADOS_VARIADOS) for _ in tareas]
    respuestas = await asyncio.gather(*[
        _generar_respuesta_enumeracion(g, s["asignatura"], _fmt_contexto(s["frags"]), d["pregunta"], d["items"])
        for g, (s, d) in zip(grados, tareas)
    ])
    ejemplos = []
    for g, (s, d), r in zip(grados, tareas, respuestas):
        if not r:
            continue
        ejemplos.append(_ejemplo(g, s["asignatura"], _fmt_contexto(s["frags"]), d["pregunta"], r))
    return ejemplos


async def _categoria5_enumeracion(n: int) -> list[dict]:
    """Usado por el dry-run (un solo lote). El run completo usa _generar_hasta_objetivo
    con _pool_seeds_enumeracion + _generar_lote_enumeracion (ver más abajo)."""
    pool = await _pool_seeds_enumeracion()
    return await _generar_lote_enumeracion(pool[: n * 2])


def _gate_enumeracion(ej: dict) -> list[str]:
    """Heurística ligera de solape léxico con el contexto; el chequeo fino de 'ítems
    inventados' lo hace el juez LLM (ver checklist de la categoría)."""
    motivos = []
    contexto = ej["messages"][1]["content"].lower()
    respuesta = ej["messages"][-1]["content"].lower()
    if any(mp in respuesta for mp in META_FRASES):
        motivos.append("meta_frase_rag")
    palabras_resp = set(re.findall(r"[a-záéíóúñ]{4,}", respuesta))
    palabras_ctx = set(re.findall(r"[a-záéíóúñ]{4,}", contexto))
    solape = len(palabras_resp & palabras_ctx) / max(1, len(palabras_resp))
    if solape < 0.25:
        motivos.append("bajo_solape_contexto")
    return motivos


# --- Categoría 6: diferenciación por asignatura (50/50, mismo pipeline que v1) ---

async def _categoria6_diferenciacion(n: int) -> list[dict]:
    mitad = max(1, n // 2)
    async with AsyncSessionLocal() as db:
        seeds_cn = await _seeds_desde_paginas(db, 3, "Ciencias Naturales", mitad)
        seeds_mate = await _seeds_desde_paginas(db, 4, "Matemáticas", mitad)
    seeds = seeds_cn + seeds_mate
    random.shuffle(seeds)

    preguntas = await asyncio.gather(*[_generar_preguntas(s) for s in seeds])
    tareas = []
    for s, pregs in zip(seeds, preguntas):
        contexto = _fmt_contexto(s["frags"])
        for p in pregs:
            tareas.append((random.choice(GRADOS_VARIADOS), s["asignatura"], contexto, p))
    random.shuffle(tareas)
    tareas = tareas[: n * 2]

    respuestas = await asyncio.gather(*[_generar_respuesta(g, a, c, p) for g, a, c, p in tareas])
    ejemplos = [_ejemplo(g, a, c, p, r) for (g, a, c, p), r in zip(tareas, respuestas) if r]
    return ejemplos[:n]


# --- Categoría 7: guía para ejercicios del libro (no resuelve, guía) ---

async def _seeds_ejercicio(db, libro_id, asignatura, max_seeds) -> list[dict]:
    """Empareja una página de EJERCICIO real (es_ejercicio_del_libro) con la página de
    TEORÍA no-ejercicio más cercana hacia atrás, como contexto."""
    rows = (
        await db.execute(select(Fragmento).where(Fragmento.libro_id == libro_id)
                         .order_by(Fragmento.numero_pagina, Fragmento.id))
    ).scalars().all()
    by_page: dict[int, Fragmento] = {}
    for r in rows:
        by_page.setdefault(r.numero_pagina, r)
    pages = sorted(by_page)

    seeds = []
    for p in pages:
        txt = (by_page[p].contenido_texto or "").strip()
        if len(txt) < 60 or not es_ejercicio_del_libro(txt):
            continue
        teoria = None
        for q in sorted((q for q in pages if q < p), reverse=True):
            t = (by_page[q].contenido_texto or "").strip()
            if len(t) >= 60 and not es_ejercicio_del_libro(t):
                teoria = {"text": t[:550], "page_num": q}
                break
        if not teoria:
            continue
        seeds.append({"asignatura": asignatura, "pagina_ejercicio": p,
                       "frags": [teoria, {"text": txt[:550], "page_num": p}]})
        if len(seeds) >= max_seeds:
            break
    return seeds


async def _generar_guia_ejercicio(grado, asignatura, contexto, pagina_ejercicio) -> tuple[str, str] | None:
    pregunta = random.choice([
        f"¿Cómo hago el ejercicio de la página {pagina_ejercicio}?",
        f"Ayúdame con la página {pagina_ejercicio}, no entiendo qué me pide",
        f"Estoy atorado en la página {pagina_ejercicio}",
    ])
    system = build_system_prompt(grado, asignatura)
    refuerzo = (
        "\n\nEl estudiante pide ayuda con un EJERCICIO del libro. NO le des el resultado ni "
        "resuelvas el ejercicio por él. En su lugar: (1) identifica qué concepto de la TEORÍA "
        "(la página de teoría del contexto) aplica, (2) remite a esa página, (3) da UNA pista "
        "concreta sin resolver, (4) anímalo a intentar el siguiente paso él mismo.")
    user = f"{contexto}\n\nPregunta del estudiante: {pregunta}"
    respuesta = await _achat(
        [{"role": "system", "content": system + refuerzo}, {"role": "user", "content": user}],
        max_tokens=400, temperature=0.6)
    return (pregunta, respuesta) if respuesta else None


async def _pool_seeds_ejercicio() -> list[dict]:
    """Pool COMPLETO de páginas-ejercicio reales disponibles (acotado por lo que existe
    en los libros indexados: ~82 en Matemáticas, ~8 en Ciencias — NO por ningún objetivo)."""
    async with AsyncSessionLocal() as db:
        seeds_mate = await _seeds_ejercicio(db, 4, "Matemáticas", 500)
        seeds_cn = await _seeds_ejercicio(db, 3, "Ciencias Naturales", 500)
    seeds = seeds_mate + seeds_cn
    random.shuffle(seeds)
    return seeds


async def _generar_lote_guia_ejercicio(seeds_lote: list[dict]) -> list[dict]:
    grados = [random.choice(GRADOS_VARIADOS) for _ in seeds_lote]
    resultados = await asyncio.gather(*[
        _generar_guia_ejercicio(g, s["asignatura"], _fmt_contexto(s["frags"]), s["pagina_ejercicio"])
        for g, s in zip(grados, seeds_lote)
    ])
    ejemplos = []
    for g, s, res in zip(grados, seeds_lote, resultados):
        if not res:
            continue
        pregunta, respuesta = res
        ejemplos.append(_ejemplo(g, s["asignatura"], _fmt_contexto(s["frags"]), pregunta, respuesta))
    return ejemplos


async def _categoria7_guia_ejercicios(n: int) -> list[dict]:
    """Usado por el dry-run (un solo lote). El run completo usa _generar_hasta_objetivo
    con _pool_seeds_ejercicio + _generar_lote_guia_ejercicio (ver más abajo)."""
    pool = await _pool_seeds_ejercicio()
    return await _generar_lote_guia_ejercicio(pool[: n * 2])


# --- Categoría 8: conversación multi-turno (3-5 turnos, un solo `messages`) ---

async def _generar_seguimiento(historial_texto: str, asignatura: str) -> str | None:
    # IMPORTANTE: los tipos que pedían "ejemplo específico" o "relación con algo ya
    # explicado" empujaban al modelo generador a pedir detalles que NO están en el
    # contexto (2 páginas), y eso disparaba rechazos en cadena (una vez que el tutor
    # rechaza un turno, tiende a seguir rechazando turnos siguientes que sí eran
    # respondibles). Los tipos de acá se quedan DENTRO de lo ya dicho: piden que se
    # reformule, simplifique o profundice lo YA explicado, no información nueva.
    sys = "Generas datos para entrenar un tutor escolar. Devuelves SOLO JSON válido."
    tipo = random.choice([
        "decir que no entendió y pedir que se lo expliquen con otras palabras (más simple)",
        "preguntar '¿por qué pasa eso?' sobre algo que el tutor YA explicó (pedir el porqué de lo dicho, no un dato nuevo)",
        "pedir que resuma en una sola oración lo que acaba de explicar",
        "preguntar qué significa una palabra específica que el tutor usó en su última respuesta",
        "decir 'ah ya entendí' y pedir que le confirme si entendió bien, repitiendo la idea con sus propias palabras",
    ])
    user = f"""Esta es la conversación hasta ahora entre un estudiante y su tutor de {asignatura}:

{historial_texto}

Genera la SIGUIENTE pregunta de seguimiento que el estudiante haría, del tipo: {tipo}. Debe \
poder responderse SOLO con la información que el tutor YA dio arriba (no pidas datos, ejemplos \
ni relaciones nuevas que no estén ya mencionadas). Debe sonar natural, como continuación de lo \
hablado, NO un tema nuevo.
Responde SOLO JSON: {{"pregunta": "..."}}"""
    data = _parse_json(await _achat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        max_tokens=100, temperature=0.8))
    return data.get("pregunta") if data else None


async def _generar_conversacion_multiturno(seed) -> dict | None:
    grado = random.choice(GRADOS_VARIADOS)
    asignatura = seed["asignatura"]
    contexto = _fmt_contexto(seed["frags"])
    system = build_system_prompt(grado, asignatura)

    preguntas_iniciales = await _generar_preguntas(seed)
    if not preguntas_iniciales:
        return None
    pregunta = preguntas_iniciales[0]

    turnos: list[tuple[str, str]] = []
    n_turnos = random.choice([3, 4, 5])
    historial_msgs = [{"role": "system", "content": system}]
    for i in range(n_turnos):
        contenido_user = f"{contexto}\n\nPregunta del estudiante: {pregunta}" if i == 0 else pregunta
        historial_msgs.append({"role": "user", "content": contenido_user})
        respuesta = await _achat(historial_msgs, max_tokens=400, temperature=0.7)
        if not respuesta:
            break
        historial_msgs.append({"role": "assistant", "content": respuesta})
        turnos.append((pregunta, respuesta))
        if i < n_turnos - 1:
            historial_texto = "\n".join(
                f"{'Estudiante' if m['role'] == 'user' else 'Tutor'}: {m['content'][-300:]}"
                for m in historial_msgs[1:])
            siguiente = await _generar_seguimiento(historial_texto, asignatura)
            if not siguiente:
                break
            pregunta = siguiente

    if len(turnos) < 3:
        return None
    return _ejemplo_multiturno(grado, asignatura, contexto, turnos)


async def _pool_seeds_multiturno() -> list[dict]:
    """Pool completo de seeds (páginas de teoría) disponibles para arrancar conversaciones."""
    async with AsyncSessionLocal() as db:
        seeds_mate = await _seeds_desde_paginas(db, 4, "Matemáticas", 500)
        seeds_cn = await _seeds_desde_paginas(db, 3, "Ciencias Naturales", 500)
    seeds = seeds_mate + seeds_cn
    random.shuffle(seeds)
    return seeds


async def _generar_lote_multiturno(seeds_lote: list[dict]) -> list[dict]:
    resultados = await asyncio.gather(*[_generar_conversacion_multiturno(s) for s in seeds_lote])
    return [e for e in resultados if e]


async def _categoria8_multiturno(n: int) -> list[dict]:
    """Usado por el dry-run (un solo lote). El run completo usa _generar_hasta_objetivo
    con _pool_seeds_multiturno + _generar_lote_multiturno (ver más abajo)."""
    pool = await _pool_seeds_multiturno()
    return await _generar_lote_multiturno(pool[: n * 2])


async def _generar_hasta_objetivo(nombre: str, objetivo: int, pool_fn, generar_lote_fn,
                                   tamano_lote: int = 15) -> tuple[list[dict], dict]:
    """Genera por LOTES hasta alcanzar `objetivo` ejemplos aprobados o agotar el pool real
    de seeds disponible (no hay 'inventar' seeds: son páginas reales de los libros). Si se
    agota el pool antes de llegar al objetivo, se detiene y lo reporta explícitamente en vez
    de forzar el número — el objetivo puede no ser alcanzable con el contenido indexado hoy
    (ver: guía_ejercicio solo tiene ~90 páginas-ejercicio reales en total)."""
    pool = await pool_fn()
    print(f"[{nombre}] pool de seeds reales disponibles: {len(pool)}")

    aprobados: list[dict] = []
    rechazos_totales: dict[str, int] = {}
    i = 0
    lote_num = 0
    while len(aprobados) < objetivo and i < len(pool):
        lote_num += 1
        seeds_lote = pool[i: i + tamano_lote]
        i += tamano_lote
        crudos = await generar_lote_fn(seeds_lote)
        nuevos, rechazos = await _validar_categoria(nombre, crudos)
        aprobados.extend(nuevos)
        for k, v in rechazos.items():
            rechazos_totales[k] = rechazos_totales.get(k, 0) + v
        print(f"[{nombre}] lote {lote_num} (seeds {i}/{len(pool)}): +{len(nuevos)} aprobados "
              f"(total {len(aprobados)}/{objetivo}) | costo acumulado={_costo()['costo_usd']}$")

    if len(aprobados) < objetivo:
        print(f"[{nombre}] ADVERTENCIA: se agotó el pool real ({len(pool)} seeds) antes de "
              f"alcanzar el objetivo. Aprobados finales: {len(aprobados)}/{objetivo}")

    return aprobados[:objetivo], rechazos_totales


CATEGORIAS_V2 = {
    # Sin juez LLM (checklist=None): tras 3 intentos de calibrar el checklist (incluido
    # few-shot), el juez seguía marcando como "respondió la pregunta" respuestas de rechazo
    # correctas de forma sistemática (sesgo del modelo a esperar que el contexto se use).
    # El gate determinístico (sin citas de página + sin meta-frases) es lo que de verdad
    # predice la calidad acá — inspección manual de ~15 ejemplos confirmó que el generador
    # produce rechazos correctos de forma consistente.
    "rechazo": (_categoria4_rechazo, _gate_rechazo, None),
    "enumeracion": (_categoria5_enumeracion, _gate_enumeracion,
        "- item_inventado: la respuesta incluye un ítem que NO aparece en el contexto dado.\n"
        "- item_faltante_grave: omite ítems importantes presentes en el contexto sin razón aparente.\n"
        "- meta_frase_rag: menciona 'fragmento' o jerga interna del pipeline RAG."),
    "diferenciacion": (_categoria6_diferenciacion, None, None),  # usa gate+juez originales
    "guia_ejercicio": (_categoria7_guia_ejercicios, lambda ej: [],
        "- dio_resultado_directo: el tutor resolvió el ejercicio o dio la respuesta final en vez de guiar.\n"
        "- no_referencia_teoria: no menciona ni remite a la página de teoría del contexto.\n"
        "- sin_pista: no da ninguna pista concreta y útil para avanzar."),
    "multiturno": (_categoria8_multiturno, lambda ej: [],
        "- inconsistencia_entre_turnos: el tutor se contradice o cambia de tema sin relación con turnos previos.\n"
        "- cita_pagina_no_disponible: cita una página que no está en el contexto original.\n"
        "- perdida_contexto: en un turno posterior ignora o contradice lo ya hablado."),
}


async def _validar_categoria(nombre: str, ejemplos: list[dict]) -> tuple[list[dict], dict]:
    _, gate_fn, checklist = CATEGORIAS_V2[nombre]
    rechazos: dict[str, int] = {}

    if nombre == "diferenciacion":  # reutiliza gate + juez ORIGINALES (mismo tipo que v1)
        sobreviven = []
        for ej in ejemplos:
            dets = _gates_deterministicos(ej)
            if dets:
                for c in dets:
                    rechazos[c] = rechazos.get(c, 0) + 1
            else:
                sobreviven.append(ej)
        veredictos = await asyncio.gather(*[_juzgar(ej) for ej in sobreviven])
        aprobados = []
        for ej, v in zip(sobreviven, veredictos):
            if v["aprobado"]:
                aprobados.append(ej)
            else:
                for mot in (v["motivos"] or ["otro"]):
                    c = _norm_motivo(mot)
                    rechazos[c] = rechazos.get(c, 0) + 1
        return aprobados, rechazos

    sobreviven = []
    for ej in ejemplos:
        dets = gate_fn(ej) if gate_fn else []
        if dets:
            for c in dets:
                rechazos[c] = rechazos.get(c, 0) + 1
        else:
            sobreviven.append(ej)

    if checklist is None:  # sin juez LLM: el gate determinístico es la única validación
        return sobreviven, rechazos

    veredictos = await asyncio.gather(*[_juzgar_v2(ej, checklist) for ej in sobreviven])
    aprobados = []
    for ej, v in zip(sobreviven, veredictos):
        if v["aprobado"]:
            aprobados.append(ej)
        else:
            for mot in (v["motivos"] or ["otro"]):
                rechazos[mot] = rechazos.get(mot, 0) + 1
    return aprobados, rechazos


async def dryrun_nuevas(n_por_categoria: int = 5) -> None:
    random.seed(SEED)
    resumen: dict[str, dict] = {}
    todos: dict[str, list[dict]] = {}
    for nombre, (generador, _, _) in CATEGORIAS_V2.items():
        print(f"\n[dry-run] generando {nombre} (objetivo={n_por_categoria})...")
        crudos = await generador(n_por_categoria)
        aprobados, rechazos = await _validar_categoria(nombre, crudos)
        todos[nombre] = aprobados
        resumen[nombre] = {"generados": len(crudos), "aprobados": len(aprobados), "rechazos": rechazos}
        print(f"[dry-run] {nombre}: {len(crudos)} generados -> {len(aprobados)} aprobados "
              f"| rechazos={rechazos}")

    os.makedirs(OUT_DIR, exist_ok=True)
    ruta = os.path.join(OUT_DIR, "dryrun_categorias_v2.jsonl")
    with open(ruta, "w", encoding="utf-8") as f:
        for nombre, ejs in todos.items():
            for ej in ejs:
                f.write(json.dumps({"_categoria": nombre, **_exportar(ej)}, ensure_ascii=False) + "\n")

    print(f"\n{'='*70}\n=== DRY-RUN COMPLETO ===")
    print(f"Guardado en: {ruta}")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(f"Costo: {json.dumps(_costo(), ensure_ascii=False)}")

    print(f"\n{'='*70}\n=== MUESTRA LEGIBLE (1 ejemplo por categoría) ===")
    for nombre, ejs in todos.items():
        print(f"\n--- {nombre} ---")
        if not ejs:
            print("(ninguno aprobado)")
            continue
        for m in ejs[0]["messages"]:
            if m["role"] == "system":
                continue
            print(f"[{m['role'].upper()}] {m['content'][:400]}")


OBJETIVOS_V2_DEFAULT = {
    "rechazo": 50, "enumeracion": 80, "diferenciacion": 100,
    "guia_ejercicio": 100, "multiturno": 107,
}


async def generar_completo_v2(objetivos: dict[str, int] | None = None) -> None:
    """Genera las 5 categorías nuevas (437 por defecto) y las combina con train.jsonl +
    val.jsonl ORIGINALES (sin sobrescribirlos) en train_v2.jsonl / val_v2.jsonl.

    Las 3 categorías de pool acotado (guia_ejercicio, enumeracion, multiturno) usan
    _generar_hasta_objetivo (por lotes, hasta agotar su pool real de seeds). El pool de
    guia_ejercicio es chico (75 páginas-ejercicio reales) y se sabe que puede quedar por
    debajo de su objetivo de 100 (techo real ~30-55): su faltante se redistribuye
    PROPORCIONALMENTE entre enumeración y multiturno (según sus pesos por defecto). Si
    enumeración TAMPOCO alcanza su objetivo ajustado, ese resto también se redirige
    íntegro a multiturno (pool más grande y flexible, ~269 seeds).

    NO se invoca automáticamente desde ningún otro comando. Correr con:
        python scripts/generar_dataset_finetuning.py completo-v2
    """
    random.seed(SEED)
    objetivos = dict(objetivos or OBJETIVOS_V2_DEFAULT)
    nuevos: list[dict] = []
    resumen: dict[str, dict] = {}
    t0 = time.time()

    for nombre in ("rechazo", "diferenciacion"):
        generador, _, _ = CATEGORIAS_V2[nombre]
        print(f"\n[v2] generando {nombre} (objetivo={objetivos[nombre]})...")
        crudos = await generador(objetivos[nombre])
        aprobados, rechazos = await _validar_categoria(nombre, crudos)
        nuevos.extend(aprobados)
        resumen[nombre] = {"generados": len(crudos), "aprobados": len(aprobados), "rechazos": rechazos}
        print(f"[v2] {nombre}: {len(crudos)} generados -> {len(aprobados)} aprobados | "
              f"costo acumulado={_costo()['costo_usd']}$")
        if len(aprobados) < objetivos[nombre]:
            print(f"[v2] ADVERTENCIA: {nombre} quedó por debajo del objetivo "
                  f"({len(aprobados)}/{objetivos[nombre]}).")

    # guia_ejercicio primero: su pool (75) es el más chico y ya sabemos que puede quedar
    # corto frente al objetivo de 100.
    print(f"\n[v2] generando guia_ejercicio (objetivo={objetivos['guia_ejercicio']}, por lotes)...")
    aprob_guia, rech_guia = await _generar_hasta_objetivo(
        "guia_ejercicio", objetivos["guia_ejercicio"], _pool_seeds_ejercicio, _generar_lote_guia_ejercicio)
    nuevos.extend(aprob_guia)
    faltante_guia = max(0, objetivos["guia_ejercicio"] - len(aprob_guia))
    resumen["guia_ejercicio"] = {"aprobados": len(aprob_guia), "objetivo": objetivos["guia_ejercicio"],
                                  "faltante_redistribuido": faltante_guia, "rechazos": rech_guia}

    peso_enum = objetivos["enumeracion"] / (objetivos["enumeracion"] + objetivos["multiturno"])
    extra_enum = round(faltante_guia * peso_enum)
    extra_multi = faltante_guia - extra_enum
    objetivo_enum = objetivos["enumeracion"] + extra_enum
    objetivo_multi_base = objetivos["multiturno"] + extra_multi
    if faltante_guia:
        print(f"[v2] guia_ejercicio quedó {faltante_guia} por debajo del objetivo -> redistribuido: "
              f"enumeración +{extra_enum} (objetivo {objetivo_enum}), "
              f"multiturno +{extra_multi} (objetivo base {objetivo_multi_base})")

    print(f"\n[v2] generando enumeracion (objetivo={objetivo_enum}, por lotes)...")
    aprob_enum, rech_enum = await _generar_hasta_objetivo(
        "enumeracion", objetivo_enum, _pool_seeds_enumeracion, _generar_lote_enumeracion)
    nuevos.extend(aprob_enum)
    faltante_enum = max(0, objetivo_enum - len(aprob_enum))
    resumen["enumeracion"] = {"aprobados": len(aprob_enum), "objetivo": objetivo_enum,
                               "faltante_redistribuido_a_multiturno": faltante_enum, "rechazos": rech_enum}

    # multiturno absorbe también lo que enumeración no haya podido cubrir de su objetivo ajustado.
    objetivo_multi = objetivo_multi_base + faltante_enum
    if faltante_enum:
        print(f"[v2] enumeración quedó {faltante_enum} por debajo de su objetivo ajustado -> "
              f"se suma a multiturno (objetivo final {objetivo_multi})")
    print(f"\n[v2] generando multiturno (objetivo={objetivo_multi}, por lotes)...")
    aprob_multi, rech_multi = await _generar_hasta_objetivo(
        "multiturno", objetivo_multi, _pool_seeds_multiturno, _generar_lote_multiturno)
    nuevos.extend(aprob_multi)
    resumen["multiturno"] = {"aprobados": len(aprob_multi), "objetivo": objetivo_multi, "rechazos": rech_multi}
    if len(aprob_multi) < objetivo_multi:
        print(f"[v2] ADVERTENCIA: multiturno también quedó por debajo del objetivo final "
              f"({len(aprob_multi)}/{objetivo_multi}) — el faltante total del dataset v2 no se pudo cubrir.")

    # split 90/10 SOLO de los nuevos, estratificado igual que el v1 (por asignatura+grado)
    train_nuevos, val_nuevos = _split_estratificado(nuevos)

    # cargar originales (train.jsonl/val.jsonl ya son {"messages": [...]}, sin _meta)
    tr_orig = [json.loads(l) for l in open(os.path.join(OUT_DIR, "train.jsonl"), encoding="utf-8")]
    va_orig = [json.loads(l) for l in open(os.path.join(OUT_DIR, "val.jsonl"), encoding="utf-8")]

    train_final = tr_orig + [_exportar(e) for e in train_nuevos]
    val_final = va_orig + [_exportar(e) for e in val_nuevos]
    random.shuffle(train_final)
    random.shuffle(val_final)

    ruta_tr = os.path.join(OUT_DIR, "train_v2.jsonl")
    ruta_va = os.path.join(OUT_DIR, "val_v2.jsonl")
    with open(ruta_tr, "w", encoding="utf-8") as f:
        for ej in train_final:
            f.write(json.dumps(ej, ensure_ascii=False) + "\n")
    with open(ruta_va, "w", encoding="utf-8") as f:
        for ej in val_final:
            f.write(json.dumps(ej, ensure_ascii=False) + "\n")

    dt = time.time() - t0
    print(f"\n{'='*70}\n=== DATASET V2 COMPLETO ===")
    print(f"Tiempo total: {dt/60:.1f} min · {json.dumps(_costo(), ensure_ascii=False)}")
    print(f"Resumen por categoría: {json.dumps(resumen, ensure_ascii=False, indent=2)}")
    print(f"Nuevos: {len(nuevos)} (train +{len(train_nuevos)}, val +{len(val_nuevos)})")
    print(f"TRAIN_V2: {len(train_final)} -> {ruta_tr}  (original {len(tr_orig)} + nuevos {len(train_nuevos)})")
    print(f"VAL_V2:   {len(val_final)} -> {ruta_va}  (original {len(va_orig)} + nuevos {len(val_nuevos)})")
    print("NOTA: train.jsonl / val.jsonl originales NO se tocaron.")


# --------------------------- orquestación completa ---------------------------

async def generar_completo(objetivo: int) -> tuple[list[dict], list[dict], dict]:
    random.seed(SEED)
    gold = _gold_cases()
    objetivo_sint = max(0, objetivo - len(gold))
    raw_objetivo = int(objetivo_sint / 0.82) + 1  # margen por rechazos del juez
    seeds_necesarios = max(1, raw_objetivo // 3)  # 3 preguntas por seed
    # Sesgo hacia Matemáticas (subrepresentada en reales): ~45% Mate / 55% Ciencias.
    n_mate = int(seeds_necesarios * 0.45)
    n_cn = seeds_necesarios - n_mate

    async with AsyncSessionLocal() as db:
        seeds_mate = await _seeds_desde_paginas(db, 4, "Matemáticas", n_mate)
        seeds_cn = await _seeds_desde_paginas(db, 3, "Ciencias Naturales", n_cn)
    seeds = seeds_mate + seeds_cn
    random.shuffle(seeds)
    print(f"[plan] objetivo={objetivo} · seeds={len(seeds)} (mate={len(seeds_mate)}, cn={len(seeds_cn)}) · raw≈{raw_objetivo}")

    aprobados: list[dict] = list(gold)  # los gold entran directo (curados a mano)
    rechazos: dict[str, int] = {}
    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = os.path.join(OUT_DIR, "_completo_parcial.jsonl")
    open(tmp, "w").close()

    LOTE = 24  # seeds por lote (progreso + resiliencia)
    gi = 0
    for b in range(0, len(seeds), LOTE):
        if len(aprobados) >= objetivo:
            break
        lote = seeds[b:b + LOTE]
        # 1) preguntas (paralelo)
        preguntas = await asyncio.gather(*[_generar_preguntas(s) for s in lote])
        tareas_pregs = []  # (grado, asignatura, contexto, pregunta)
        for s, pregs in zip(lote, preguntas):
            contexto = _fmt_contexto(s["frags"])
            for p in pregs:
                grado = GRADOS_VARIADOS[gi % len(GRADOS_VARIADOS)]
                gi += 1
                tareas_pregs.append((grado, s["asignatura"], contexto, p))
        # 2) respuestas (paralelo)
        respuestas = await asyncio.gather(
            *[_generar_respuesta(g, a, c, p) for (g, a, c, p) in tareas_pregs])
        candidatos = [
            _ejemplo(g, a, c, p, r)
            for (g, a, c, p), r in zip(tareas_pregs, respuestas) if r
        ]
        # 3a) gates determinísticos (exactos, sin LLM): citas + meta-frases.
        sobreviven = []
        for ej in candidatos:
            dets = _gates_deterministicos(ej)
            if dets:
                for c in dets:
                    rechazos[c] = rechazos.get(c, 0) + 1
            else:
                sobreviven.append(ej)
        # 3b) juez LLM solo para lo semántico (b/c/d), en paralelo.
        veredictos = await asyncio.gather(*[_juzgar(ej) for ej in sobreviven])
        nuevos = 0
        with open(tmp, "a", encoding="utf-8") as fh:
            for ej, v in zip(sobreviven, veredictos):
                if v["aprobado"]:
                    aprobados.append(ej)
                    fh.write(json.dumps(_exportar(ej), ensure_ascii=False) + "\n")
                    nuevos += 1
                else:
                    for mot in (v["motivos"] or ["otro"]):
                        c = _norm_motivo(mot)
                        rechazos[c] = rechazos.get(c, 0) + 1
        print(f"[lote {b//LOTE + 1}] cand={len(candidatos)} aprobados+={nuevos} "
              f"total={len(aprobados)} | uso={_costo()['costo_usd']}$")

    train, val = _split_estratificado(aprobados)
    return train, val, rechazos


# --------------------------- split estratificado 90/10 ---------------------------

def _split_estratificado(ejemplos: list[dict]) -> tuple[list[dict], list[dict]]:
    random.seed(SEED)
    buckets: dict[tuple, list] = {}
    for ej in ejemplos:
        k = (ej["_meta"]["asignatura"], ej["_meta"]["grado"])
        buckets.setdefault(k, []).append(ej)
    train, val = [], []
    for k, items in buckets.items():
        random.shuffle(items)
        n_val = max(1, round(len(items) * RATIO_VAL)) if len(items) >= 2 else 0
        val.extend(items[:n_val])
        train.extend(items[n_val:])
    random.shuffle(train)
    random.shuffle(val)
    return train, val


# --------------------------- reportes ---------------------------

def _costo() -> dict:
    total = _uso["prompt"] + _uso["completion"]
    return {"llamadas": _uso["llamadas"], "tokens_total": total,
            "costo_usd": round(total / 1_000_000 * PRECIO_USD_POR_1M, 3)}


def _distribucion(ejemplos: list[dict]) -> dict:
    d: dict[str, int] = {}
    for ej in ejemplos:
        k = f"{ej['_meta']['asignatura']} · {ej['_meta']['grado']}"
        d[k] = d.get(k, 0) + 1
    return d


# --------------------------- re-juzgar (juez endurecido, sin regenerar) ---------------------------

# Corrección ORTOGRÁFICA puntual (no regenera, no bloquea): typos conocidos. No es un
# corrector completo (eso requeriría una dependencia); solo mapea errores frecuentes.
_TYPOS = {r"blockadeador": "bloqueador", r"bloqueadora\s+solar": "bloqueador solar"}


def _corregir_typos(ej: dict) -> None:
    t = ej["messages"][-1]["content"]
    for bad, good in _TYPOS.items():
        t = re.sub(bad, good, t, flags=re.IGNORECASE)
    ej["messages"][-1]["content"] = t


def _recuperar_meta(ej: dict) -> dict:
    """Recupera grado/asignatura desde la 1ª línea del system (los .jsonl no llevan _meta)."""
    linea = ej["messages"][0]["content"].split("\n")[0]
    m = re.search(r"tutor de (.+?) para estudiantes de (.+?) del", linea)
    asign, grado = (m.group(1), m.group(2)) if m else ("Ciencias Naturales", "4to Primaria")
    ej["_meta"] = {"grado": grado, "asignatura": asign}
    return ej


async def rejuzgar() -> None:
    """Re-juzga train.jsonl+val.jsonl con el juez ENDURECIDO (sin regenerar), aplica
    corrección de typos a los que pasan, y re-divide 90/10 estratificado."""
    tr = [json.loads(l) for l in open(os.path.join(OUT_DIR, "train.jsonl"), encoding="utf-8")]
    va = [json.loads(l) for l in open(os.path.join(OUT_DIR, "val.jsonl"), encoding="utf-8")]
    pool = [_recuperar_meta(e) for e in tr + va]
    print(f"[rejuzgar] pool={len(pool)} (train {len(tr)} + val {len(va)})")

    keep: list[dict] = []
    rechazos: dict[str, int] = {}
    CH = 30
    for i in range(0, len(pool), CH):
        chunk = pool[i:i + CH]
        # gates determinísticos primero
        survivors = []
        for ej in chunk:
            d = _gates_deterministicos(ej)
            if d:
                for c in d:
                    rechazos[c] = rechazos.get(c, 0) + 1
            else:
                survivors.append(ej)
        veredictos = await asyncio.gather(*[_juzgar(ej) for ej in survivors])
        for ej, v in zip(survivors, veredictos):
            if v["aprobado"]:
                _corregir_typos(ej)
                keep.append(ej)
            else:
                for mot in (v["motivos"] or ["otro"]):
                    c = _norm_motivo(mot)
                    rechazos[c] = rechazos.get(c, 0) + 1
        print(f"  [chunk {i//CH + 1}] mantenidos={len(keep)} | uso={_costo()['costo_usd']}$")

    train, val = _split_estratificado(keep)
    _escribir_jsonl("train.jsonl", train)
    _escribir_jsonl("val.jsonl", val)
    conceptuales = rechazos.get("imprecision_conceptual", 0) + rechazos.get("analogia_incoherente", 0)
    otros = sum(v for k, v in rechazos.items() if k not in ("imprecision_conceptual", "analogia_incoherente"))
    print(f"\n{'='*70}\n=== RE-JUZGADO (juez endurecido) ===")
    print(f"{json.dumps(_costo(), ensure_ascii=False)}")
    print(f"Mantenidos: {len(keep)} de {len(pool)}")
    print(f"TRAIN: {len(train)} · VAL: {len(val)} ({100*len(val)/max(1,len(keep)):.0f}% val)")
    print(f"Rechazos CONCEPTUALES (imprecision+analogia): {conceptuales} · otros: {otros}")
    print(f"Rechazos detallados: {json.dumps(rechazos, ensure_ascii=False)}")
    print(f"Distribución TRAIN: {json.dumps(_distribucion(train), ensure_ascii=False)}")


async def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("reales")
    sub.add_parser("rejuzgar")
    pc = sub.add_parser("completo")
    pc.add_argument("--objetivo", type=int, default=600)
    pd = sub.add_parser("dryrun-v2")
    pd.add_argument("--n", type=int, default=5)
    sub.add_parser("completo-v2")  # usa OBJETIVOS_V2_DEFAULT (437 en total); no sobrescribe v1
    args = parser.parse_args()

    t0 = time.time()
    if args.cmd == "dryrun-v2":
        await dryrun_nuevas(args.n)
        return
    if args.cmd == "completo-v2":
        await generar_completo_v2()
        return
    if args.cmd == "rejuzgar":
        await rejuzgar()
        return
    if args.cmd == "reales":
        ejemplos, desc = await extraer_reales()
        ruta = _escribir_jsonl("reales_limpias.jsonl", ejemplos)
        print(f"\n=== reales limpias: {len(ejemplos)} -> {ruta}")
        print(f"Descartados: {json.dumps(desc, ensure_ascii=False)}")
        print(f"Distribución: {json.dumps(_distribucion(ejemplos), ensure_ascii=False)}")
        return

    # completo: reales limpias + sintéticos juzgados, split 90/10
    reales, _ = await extraer_reales()
    train_s, val_s, rechazos = await generar_completo(args.objetivo)
    # inyectar reales en el split (estratificado junto con lo demás)
    train, val = _split_estratificado(train_s + val_s + reales)
    ruta_tr = _escribir_jsonl("train.jsonl", train)
    ruta_va = _escribir_jsonl("val.jsonl", val)
    dt = time.time() - t0
    print(f"\n{'='*70}\n=== DATASET COMPLETO ===")
    print(f"Tiempo total: {dt/60:.1f} min · {json.dumps(_costo(), ensure_ascii=False)}")
    print(f"Reales limpias incluidas: {len(reales)}")
    print(f"TRAIN: {len(train)} -> {ruta_tr}")
    print(f"VAL:   {len(val)} -> {ruta_va}")
    print(f"Rechazos del juez (agrupados): {json.dumps(rechazos, ensure_ascii=False)}")
    print(f"Distribución TRAIN: {json.dumps(_distribucion(train), ensure_ascii=False)}")
    print(f"Distribución VAL:   {json.dumps(_distribucion(val), ensure_ascii=False)}")


if __name__ == "__main__":
    asyncio.run(main())
