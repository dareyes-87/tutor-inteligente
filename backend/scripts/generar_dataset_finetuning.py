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
from app.modules.chat.service import _citas_validas, _es_rechazo

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
    args = parser.parse_args()

    t0 = time.time()
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
