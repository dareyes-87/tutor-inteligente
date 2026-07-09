"""
Lógica de negocio de la ruta de aprendizaje y la gamificación.

Expone: ruta del estudiante (con progreso por lección), iniciar/completar
lecciones, y la capa de gamificación (rachas + ranking) integrada con las
lecciones. Las funciones son async y son dueñas del commit.
"""
import logging
import math
import random
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import llm_client, modelo_para_asignatura
from app.models.asignatura import Asignatura
from app.models.fragmento import Fragmento
from app.models.grado import Grado
from app.models.leccion import Leccion
from app.models.libro import EstadoIndexacion, LibroTexto
from app.models.progreso_leccion import EstadoLeccion, ProgresoLeccion
from app.models.usuario import RolUsuario, Usuario
from app.modules.lecciones.emoji_map import get_emoji_for_topic
from app.modules.lecciones.schemas import (
    CompletarNivelResponse,
    LeccionEnRuta,
    LibroDisponible,
    MicroLeccionResponse,
    MiGradoResponse,
    MiLibroResponse,
    RachaResponse,
    RankingEstudiante,
    RankingResponse,
    RutaAprendizaje,
)
from app.modules.rag.search import es_ejercicio_del_libro, search_fragments

logger = logging.getLogger(__name__)

# Puntaje mínimo (promedio) para dar una lección por completada.
PUNTAJE_MINIMO_COMPLETAR = 70

# --- Sistema de 3 niveles tipo Duolingo ---
# Cuántos fragmentos (Top-K) usa la micro-lección en cada nivel.
NIVEL_TOPK = {1: 5, 2: 8, 3: 10}
# Fracción de la sesión que hay que aprobar (>=70) para superar el nivel. Es
# PROPORCIONAL al nº de actividades REALMENTE generadas, no un conteo fijo: una
# sesión puede generar menos de 5 (si algún tipo falla o el guardrail lo
# descarta), y un umbral fijo mayor que el total hacía IMPOSIBLE aprobar (bug
# real: 3/3 correctas pero "necesitas 4"). ceil(0.8·total): 3→3, 4→4, 5→4.
FRACCION_APROBAR_NIVEL = 0.8
# Fallback (solo si el cliente no envía total_actividades): conteo fijo viejo.
NIVEL_APROBADAS_REQUERIDAS = {1: 3, 2: 4, 3: 4}
# Puntos por nivel superado (gratificación inmediata, no esperar a dominar la
# lección completa). Suman 100 por lección, igual que el esquema viejo, pero
# repartidos: el nivel 3 lleva un bonus por completar. Se otorgan UNA sola vez
# por nivel (idempotente vía `nivel_completado`): rehacer un nivel no re-suma.
PUNTOS_POR_NIVEL = {1: 30, 2: 30, 3: 40}
# Tamaño del pool de candidatos del que se muestrea Top-K (da variedad por intento).
POOL_CANDIDATOS_FRAGMENTOS = 15


def _aprobadas_requeridas(nivel: int, total_actividades: int | None) -> int:
    """Cuántas actividades hay que aprobar para superar el nivel. Proporcional
    al total real de la sesión (ceil(0.8·total), mínimo 1) para que SIEMPRE sea
    alcanzable; si el cliente no manda el total, cae al conteo fijo viejo."""
    if total_actividades and total_actividades > 0:
        return max(1, math.ceil(FRACCION_APROBAR_NIVEL * total_actividades))
    return NIVEL_APROBADAS_REQUERIDAS.get(nivel, 3)


def _seleccionar_fragmentos_nivel(
    fragments: list[dict], leccion_id: int, nivel: int
) -> list[dict]:
    """Muestrea Top-K fragmentos del pool según el nivel, con semilla por día.

    La semilla (leccion_id, nivel, día del año) hace que el muestreo sea estable
    dentro del mismo día pero cambie al día siguiente: cada intento/día trae
    tarjetas con énfasis distintos. Se mantiene el orden por página para que el
    contexto que ve el LLM sea coherente.
    """
    k = NIVEL_TOPK.get(nivel, 5)
    if len(fragments) <= k:
        seleccion = list(fragments)
    else:
        seed = leccion_id * 100 + nivel + date.today().timetuple().tm_yday
        seleccion = random.Random(seed).sample(fragments, k)
    return sorted(seleccion, key=lambda f: (f.get("page_num") is None, f.get("page_num") or 0))


def _parsear_rango_paginas(paginas: str | None) -> tuple[int, int] | None:
    """Convierte un rango de páginas tipo '3-7' (o '3') a (ini, fin)."""
    if not paginas:
        return None
    partes = paginas.replace(" ", "").split("-")
    try:
        nums = [int(p) for p in partes if p]
    except ValueError:
        return None
    if not nums:
        return None
    return (min(nums), max(nums))


# Umbral mínimo de cobertura: una tarjeta cuyo texto comparte menos de este
# porcentaje de palabras (>5 letras) con los fragmentos del libro se descarta
# (capa de seguridad contra contenido que no viene de la lección).
COBERTURA_MINIMA = 0.3
MIN_TARJETAS_VALIDAS = 4


def _filtrar_tarjetas_por_cobertura(tarjetas: list, fragmentos_texto: str) -> list:
    """Descarta tarjetas cuyo contenido no se apoya en los fragmentos usados.

    Para cada tarjeta toma las palabras de >5 letras de su `contenido` y mide
    cuántas aparecen (como subcadena) en el texto de los fragmentos. Si la
    cobertura < COBERTURA_MINIMA, la tarjeta se descarta.
    """
    conservadas = []
    for t in tarjetas:
        palabras = [
            w for w in re.findall(r"[^\W\d_]+", (t.contenido or "").lower(), re.UNICODE)
            if len(w) > 5
        ]
        if not palabras:
            conservadas.append(t)
            continue
        en_fragmento = sum(1 for w in palabras if w in fragmentos_texto)
        cobertura = en_fragmento / len(palabras)
        if cobertura < COBERTURA_MINIMA:
            logger.warning(
                "[MicroLeccion] Tarjeta descartada por baja cobertura (%.0f%%): %s",
                cobertura * 100, t.titulo_concepto or t.tipo,
            )
            continue
        conservadas.append(t)
    return conservadas


async def _get_or_create_progreso(
    estudiante_id: int, leccion: Leccion, db: AsyncSession
) -> ProgresoLeccion:
    """Obtiene el progreso del estudiante en una lección; lo crea si no existe.

    La primera lección (orden=1) nace 'disponible'; las demás 'bloqueada'.
    Usa flush (no commit) — el commit lo hace la función que orquesta.
    """
    result = await db.execute(
        select(ProgresoLeccion).where(
            ProgresoLeccion.estudiante_id == estudiante_id,
            ProgresoLeccion.leccion_id == leccion.id,
        )
    )
    progreso = result.scalar_one_or_none()
    if progreso is None:
        progreso = ProgresoLeccion(
            estudiante_id=estudiante_id,
            leccion_id=leccion.id,
            estado=(
                EstadoLeccion.disponible if leccion.orden == 1 else EstadoLeccion.bloqueada
            ),
        )
        db.add(progreso)
        await db.flush()
    return progreso


def _to_leccion_en_ruta(leccion: Leccion, progreso: ProgresoLeccion) -> LeccionEnRuta:
    return LeccionEnRuta(
        id=leccion.id,
        nombre=leccion.nombre,
        descripcion=leccion.descripcion,
        orden=leccion.orden,
        tema_clave=leccion.tema_clave,
        paginas=leccion.paginas,
        estado=progreso.estado.value,
        puntaje_promedio=round(progreso.puntaje_promedio, 1),
        actividades_completadas=progreso.actividades_completadas,
        actividades_requeridas=progreso.actividades_requeridas,
        nivel_actual=progreso.nivel_actual,
        nivel_completado=progreso.nivel_completado,
        tiene_corona=progreso.nivel_completado >= 3,
    )


async def obtener_ruta(
    estudiante_id: int, libro_id: int, db: AsyncSession
) -> RutaAprendizaje:
    """Ruta completa del libro con el progreso del estudiante (inicializa lo que falte)."""
    fila = (
        await db.execute(
            select(LibroTexto, Asignatura.nombre)
            .join(Asignatura, LibroTexto.asignatura_id == Asignatura.id)
            .where(LibroTexto.id == libro_id)
        )
    ).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Libro no encontrado")
    _libro, asignatura_nombre = fila

    lecciones = list(
        (
            await db.execute(
                select(Leccion).where(Leccion.libro_id == libro_id).order_by(Leccion.orden)
            )
        ).scalars().all()
    )

    items: list[LeccionEnRuta] = []
    completadas = 0
    for leccion in lecciones:
        progreso = await _get_or_create_progreso(estudiante_id, leccion, db)
        if progreso.estado == EstadoLeccion.completada:
            completadas += 1
        items.append(_to_leccion_en_ruta(leccion, progreso))

    await db.commit()

    total = len(lecciones)
    pct = round((completadas / total) * 100, 1) if total else 0.0
    return RutaAprendizaje(
        libro_id=libro_id,
        asignatura=asignatura_nombre,
        total_lecciones=total,
        lecciones_completadas=completadas,
        progreso_porcentaje=pct,
        lecciones=items,
    )


async def obtener_mi_libro(estudiante: Usuario, db: AsyncSession) -> MiLibroResponse:
    """
    Resuelve el libro activo del estudiante a partir de su grado.

    Busca el primer libro (por id) que esté indexado (`completado`), sea del
    grado del estudiante y tenga al menos una lección generada. Así el frontend
    no necesita un `libro_id` hardcodeado.
    """
    if estudiante.grado_id is None:
        raise HTTPException(
            status_code=404,
            detail="El estudiante no tiene un grado asignado.",
        )

    total_lecciones = func.count(Leccion.id)
    fila = (
        await db.execute(
            select(LibroTexto, total_lecciones)
            .join(Leccion, Leccion.libro_id == LibroTexto.id)
            .where(
                LibroTexto.grado_id == estudiante.grado_id,
                LibroTexto.estado_indexacion == EstadoIndexacion.completado,
            )
            .group_by(LibroTexto.id)
            .having(total_lecciones > 0)
            .order_by(LibroTexto.id)
            .limit(1)
        )
    ).first()
    if fila is None:
        raise HTTPException(
            status_code=404,
            detail="No hay un libro con lecciones disponible para tu grado.",
        )

    libro, total = fila
    return MiLibroResponse(
        libro_id=libro.id,
        titulo=libro.titulo,
        total_lecciones=total,
    )


async def obtener_mis_libros(
    estudiante: Usuario, db: AsyncSession
) -> list[LibroDisponible]:
    """
    TODOS los libros `completado` con lecciones del grado del estudiante, cada uno
    con su asignatura. A diferencia de `obtener_mi_libro` (que resuelve uno solo),
    esto devuelve la lista completa para poder ofrecer un selector de asignatura.

    Devuelve lista vacía (no 404) si el estudiante no tiene grado o no hay libros.
    """
    if estudiante.grado_id is None:
        return []

    total_lecciones = func.count(Leccion.id)
    filas = (
        await db.execute(
            select(LibroTexto, Asignatura.id, Asignatura.nombre, total_lecciones)
            .join(Leccion, Leccion.libro_id == LibroTexto.id)
            .join(Asignatura, LibroTexto.asignatura_id == Asignatura.id)
            .where(
                LibroTexto.grado_id == estudiante.grado_id,
                LibroTexto.estado_indexacion == EstadoIndexacion.completado,
            )
            .group_by(LibroTexto.id, Asignatura.id, Asignatura.nombre)
            .having(total_lecciones > 0)
            .order_by(LibroTexto.id)
        )
    ).all()

    return [
        LibroDisponible(
            libro_id=libro.id,
            titulo=libro.titulo,
            asignatura_id=asignatura_id,
            asignatura_nombre=asignatura_nombre,
            total_lecciones=total,
        )
        for libro, asignatura_id, asignatura_nombre, total in filas
    ]


# Enfoque pedagógico de cada nivel (se inyecta en el prompt de la micro-lección).
_ENFOQUE_NIVEL = {
    1: "Explica los conceptos fundamentales de forma introductoria. Usa lenguaje simple para niños de 8-12 años.",
    2: "El estudiante ya conoce los conceptos base. Ahora profundiza con ejemplos concretos, aplicaciones en la vida real y relaciones entre los conceptos del tema.",
    3: "El estudiante domina el tema. Presenta síntesis, conexiones entre subtemas, casos especiales y detalles avanzados del contenido del libro.",
}


# Bloque de reglas SOLO para Matemáticas: el LLM comete errores de posición
# numérica y de aritmética que confunden al estudiante. La micro-lección es
# texto libre (no JSON verificable como las actividades), así que reforzar el
# prompt es la única capa disponible aquí. Cubre Bug 2 (nomenclatura posicional)
# y Bug 5 (ejemplos matemáticos correctos + redondeo).
_REGLAS_MATEMATICAS_MICRO = """
- NOMENCLATURA POSICIONAL EXACTA: de derecha a izquierda las posiciones son unidades, decenas, centenas, unidades de millar (NO "mil"), decenas de millar, centenas de millar, unidades de millón. Una centena de millar vale 100,000 (NO 1,000). Al comparar dos números, identifica con cuidado la posición EXACTA donde difieren (ejemplo: 1,234 y 1,243 comparten millar y centena, pero difieren en las DECENAS: 3 vs 4).
- CADA ejemplo numérico que incluyas DEBE ser matemáticamente correcto. Verifica mentalmente cada operación (suma, resta, comparación, redondeo) antes de escribirla. Si no estás seguro del resultado, usa números más simples donde el resultado sea obvio. NO uses ejemplos cuyo resultado no puedas verificar con certeza.
- REDONDEO/APROXIMACIÓN, mira SIEMPRE el dígito de la posición inmediatamente menor (0-4 se redondea hacia abajo, 5-9 hacia arriba): a la decena → mira las unidades; a la centena → mira las decenas; a la unidad de millar → mira las centenas; a la decena de millar → mira las unidades de millar. Ejemplo CORRECTO: 45,678 a la decena de millar más cercana → miramos las unidades de millar (5); como 5 ≥ 5, redondeamos hacia arriba: 50,000 (NO 45,000 ni 87,000)."""


def _build_micro_leccion_messages(
    nombre_leccion: str, fragmentos: str, nivel: int = 1, asignatura_nombre: str | None = None
) -> list[dict]:
    """Prompt para generar la micro-lección (tarjetas educativas) de una lección.

    `nivel` (1-3) cambia el enfoque pedagógico (base / profundización / síntesis).
    `asignatura_nombre` activa reglas extra para Matemáticas (posiciones, aritmética).
    """
    enfoque = _ENFOQUE_NIVEL.get(nivel, _ENFOQUE_NIVEL[1])
    # "matem" evita el problema del acento ("Matemáticas".lower() conserva la á).
    es_matematicas = bool(asignatura_nombre and "matem" in asignatura_nombre.lower())
    reglas_matematicas = _REGLAS_MATEMATICAS_MICRO if es_matematicas else ""
    user = f"""Eres un tutor para niños de 8-12 años. Genera una micro-lección estructurada sobre el tema "{nombre_leccion}" usando EXCLUSIVAMENTE el contenido del siguiente libro de texto.

ENFOQUE DE ESTA LECCIÓN (NIVEL {nivel} de 3): {enfoque}

CONTENIDO DEL LIBRO:
{fragmentos}

Genera un JSON con esta estructura exacta:
{{
  "titulo": "título atractivo para niños",
  "tarjetas": [
    {{
      "tipo": "introduccion",
      "contenido": "Texto introductorio breve y amigable (2-3 oraciones)"
    }},
    {{
      "tipo": "concepto",
      "titulo_concepto": "Nombre del concepto",
      "contenido": "Explicación clara y simple del concepto (3-4 oraciones, como si le explicaras a un niño de 10 años)",
      "dato_curioso": "Un dato interesante relacionado (opcional)",
      "pregunta": {{
        "texto": "Pregunta de comprensión sobre lo explicado",
        "tipo": "verdadero_falso | opcion_multiple",
        "opciones": ["opción 1", "opción 2", "opción 3", "opción 4"],
        "respuesta_correcta": "la opción correcta",
        "explicacion": "Por qué esa es la respuesta correcta"
      }}
    }},
    {{
      "tipo": "resumen",
      "contenido": "Resumen de todo lo aprendido (3-4 oraciones)"
    }}
  ]
}}

REGLAS:
- Genera entre 8 y 10 tarjetas (1 intro + 6-8 conceptos + 1 resumen)
- SIEMPRE en español
- Lenguaje simple, frases cortas, como si hablaras con un niño
- Usa analogías relacionadas con la naturaleza, los animales, el cuerpo humano o la vida cotidiana de un niño (juegos, comida, escuela). NUNCA uses analogías con tecnología (teléfonos, computadoras, robots).
- Cada concepto debe tener una pregunta de comprensión
- Las preguntas deben ser respondibles con lo explicado en ESA tarjeta, y la "respuesta_correcta" DEBE ser coherente con el "contenido" de esa misma tarjeta (no te contradigas).
- "respuesta_correcta" debe ser SIEMPRE uno de los textos EXACTOS de "opciones".
- NO antepongas letras ni números de inciso ("A.", "B)", "1.", etc.) a las opciones: escribe SOLO el texto de la opción.
- Si "tipo" es "verdadero_falso": "texto" DEBE ser una AFIRMACIÓN que el estudiante juzga como verdadera o falsa (ejemplo: "Las células animales tienen pared celular"). NUNCA una pregunta: no empiece con "¿", ni use "¿Qué...?", "¿Cuál...?" ni "¿Cómo...?". "opciones" debe ser exactamente ["Verdadero", "Falso"] y "respuesta_correcta" debe ser "Verdadero" o "Falso".
- Si "tipo" es "opcion_multiple": "texto" es una pregunta con 4 opciones distintas y plausibles. Las opciones incorrectas (distractores) deben ser CLARAMENTE diferentes a la respuesta correcta: no uses sinónimos ni frases que signifiquen lo mismo con otras palabras. Cada distractor debe referirse a un concepto diferente.
- Si necesitas hacer una pregunta abierta ("¿Qué...?", "¿Cuál...?"), usa SIEMPRE "tipo": "opcion_multiple" con 4 opciones, NUNCA "verdadero_falso".
- NO uses información que no esté en el libro
- IGNORA cualquier ejercicio, actividad resuelta, ejemplo resuelto o sección tipo "Mesa lista", "Ahora es tu turno", "Ejercicio", "Practica" que aparezca en el libro. Explica ÚNICAMENTE la TEORÍA: definiciones, conceptos y explicaciones del tema. NO copies ni reformules un ejercicio del libro como si fuera un concepto.
- NO incluyas "emoji" en el JSON: se asigna aparte
- NUNCA uses las palabras "fragmento", "contexto", "chunk" ni ningún término técnico de procesamiento de datos en el contenido: refiérete siempre al material como "el libro" o "tu libro de texto".
- Cuando escribas números de 4 o más dígitos, SIEMPRE usa comas como separador de miles para facilitar la lectura a un niño (1000 → 1,000; 45678 → 45,678; 5746252 → 5,746,252; 1000000 → 1,000,000). NUNCA escribas números grandes sin separador de miles.{reglas_matematicas}
- Responde SOLO con el JSON, sin texto adicional"""
    return [
        {
            "role": "system",
            "content": "Eres un tutor educativo en Guatemala para niños. Respondes SIEMPRE en español y SOLO con JSON válido.",
        },
        {"role": "user", "content": user},
    ]


_PATRON_INCISO = re.compile(r"^\s*[A-Da-d]\s*[\.\):]\s*")


def _quitar_inciso(texto: str) -> str:
    """Quita un inciso ("A.", "b)", "C:") que el LLM haya antepuesto a una
    opción de opción múltiple (ver mismo guardrail en actividades/generator.py):
    el estudiante solo toca la opción, no necesita letras de inciso."""
    return _PATRON_INCISO.sub("", texto or "", count=1).strip()


def _corregir_preguntas(micro: MicroLeccionResponse) -> None:
    """Safety net: arregla preguntas mal tipadas por el LLM (muta `micro`).

    Si una pregunta está marcada como 'verdadero_falso' pero su texto es una
    pregunta abierta (empieza con '¿'), es incoherente mostrar botones V/F.
    - Si ya trae 3+ opciones reales, solo se reetiqueta a 'opcion_multiple'.
    - Si trae menos de 3 opciones (típicamente solo V/F), no se pueden fabricar
      distractores válidos en Python sin inventar respuestas, así que se quita
      la pregunta (la tarjeta queda solo con la explicación). Es preferible a
      mostrar una pregunta abierta con opciones Verdadero/Falso.
    """
    for tarjeta in micro.tarjetas:
        p = tarjeta.pregunta
        if p is None:
            continue
        if p.tipo == "verdadero_falso" and p.texto.lstrip().startswith("¿"):
            opciones_validas = [o for o in p.opciones if o.strip()]
            if len(opciones_validas) >= 3 and p.respuesta_correcta in opciones_validas:
                p.tipo = "opcion_multiple"
            else:
                tarjeta.pregunta = None
                continue
        if tarjeta.pregunta.tipo == "opcion_multiple":
            # Guardrail determinístico: quitar incisos que el LLM haya antepuesto.
            tarjeta.pregunta.opciones = [_quitar_inciso(o) for o in tarjeta.pregunta.opciones]
            tarjeta.pregunta.respuesta_correcta = _quitar_inciso(tarjeta.pregunta.respuesta_correcta)
            # Mezclar las opciones: el LLM tiende a poner la correcta de primera.
            # respuesta_correcta guarda el TEXTO (no el índice), así que es seguro;
            # el frontend compara texto contra texto. No se mezcla V/F (Verdadero/Falso
            # debe quedar en ese orden).
            random.shuffle(tarjeta.pregunta.opciones)


# Números "pegados" (sin coma ni punto alrededor) → con coma de miles. El
# prompt ya pide comas (Bug 3), pero el modelo 7B las omite seguido cuando copia
# números del libro (que vienen mal por el OCR): esta es la capa determinística.
# Solo aplica a las micro-lecciones (texto de solo lectura); en las actividades
# se evita porque tocaría la respuesta correcta y rompería la comparación exacta
# al calificar.
#   - En Matemáticas se formatean números de 4+ dígitos (1000 → 1,000).
#   - En otras materias, solo 5+ dígitos: los de 4 dígitos incluyen años
#     (1860, 1970) que NO deben llevar coma, y en historia/ciencias son comunes.
_RE_NUMERO_PEGADO_4 = re.compile(r"(?<![\d.,])\d{4,}(?![\d.,])")
_RE_NUMERO_PEGADO_5 = re.compile(r"(?<![\d.,])\d{5,}(?![\d.,])")


def _con_coma_de_miles(texto: str | None, patron: re.Pattern) -> str | None:
    if not texto:
        return texto
    return patron.sub(lambda m: f"{int(m.group()):,}", texto)


def _formatear_miles(micro: MicroLeccionResponse, es_matematicas: bool) -> None:
    """Inserta comas de miles en los números grandes de cada tarjeta (muta
    `micro`). En las preguntas rápidas formatea opciones y respuesta_correcta
    con la MISMA función, así el emparejamiento exacto opción↔respuesta no se
    rompe."""
    patron = _RE_NUMERO_PEGADO_4 if es_matematicas else _RE_NUMERO_PEGADO_5
    fmt = lambda s: _con_coma_de_miles(s, patron)
    for t in micro.tarjetas:
        t.contenido = fmt(t.contenido)
        t.titulo_concepto = fmt(t.titulo_concepto)
        t.dato_curioso = fmt(t.dato_curioso)
        p = t.pregunta
        if p is not None:
            p.texto = fmt(p.texto) or p.texto
            p.explicacion = fmt(p.explicacion) or p.explicacion
            p.opciones = [fmt(o) or o for o in p.opciones]
            p.respuesta_correcta = fmt(p.respuesta_correcta) or p.respuesta_correcta


def _asignar_emojis(micro: MicroLeccionResponse, tema_leccion: str, asignatura_nombre: str) -> None:
    """Asigna el emoji de cada tarjeta con el mapeo curado (muta `micro`).

    El LLM ya no elige el emoji (ver `_build_micro_leccion_messages`): se asigna
    SIEMPRE aquí para evitar casos como 🧬 en un tema de Matemáticas. Las
    tarjetas de concepto usan su propio `titulo_concepto` (más específico); las
    de introducción/resumen usan el tema de la lección completa.
    """
    emoji_leccion = get_emoji_for_topic(tema_leccion, asignatura_nombre)
    for tarjeta in micro.tarjetas:
        if tarjeta.titulo_concepto:
            tarjeta.emoji = get_emoji_for_topic(tarjeta.titulo_concepto, asignatura_nombre)
        else:
            tarjeta.emoji = emoji_leccion


async def generar_micro_leccion(
    leccion_id: int, db: AsyncSession, nivel: int = 1
) -> MicroLeccionResponse:
    """
    Genera on-demand una micro-lección (secuencia de tarjetas) para una lección.

    Usa los fragmentos del libro (RAG por tema_clave + asignatura/grado del libro)
    y el LLM base (Qwen 7B). No se cachea.

    `nivel` (1-3) ajusta Top-K (5/8/10), el enfoque del prompt, y muestrea los
    fragmentos con semilla por día para variar el énfasis entre intentos.
    """
    nivel = nivel if nivel in NIVEL_TOPK else 1
    fila = (
        await db.execute(
            select(Leccion, Asignatura.nombre, Grado.nombre)
            .join(LibroTexto, Leccion.libro_id == LibroTexto.id)
            .join(Asignatura, LibroTexto.asignatura_id == Asignatura.id)
            .join(Grado, LibroTexto.grado_id == Grado.id)
            .where(Leccion.id == leccion_id)
        )
    ).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Lección no encontrada")
    leccion, asignatura_nombre, grado_nombre = fila

    # Pool de fragmentos: PRIMERO por el rango de páginas de la lección (0% de
    # leak de otras secciones del libro). La búsqueda semántica en ChromaDB queda
    # solo como FALLBACK si el rango no tiene fragmentos (caso raro).
    rango = _parsear_rango_paginas(leccion.paginas)
    pool: list[dict] = []
    if rango is not None:
        ini, fin = rango
        rows = (
            await db.execute(
                select(Fragmento)
                .where(
                    Fragmento.libro_id == leccion.libro_id,
                    Fragmento.numero_pagina >= ini,
                    Fragmento.numero_pagina <= fin,
                )
                .order_by(Fragmento.numero_pagina, Fragmento.id)
            )
        ).scalars().all()
        pool = [
            {"text": r.contenido_texto, "page_num": r.numero_pagina, "chunk_id": r.chunk_id_vectordb}
            for r in rows
        ]
        # Filtrar ejercicios del libro (Mesa lista, Ahora es tu turno…): el LLM
        # los copia como si fueran teoría. No cambia qué se recupera, solo qué
        # de lo recuperado se usa como contexto.
        pool = [f for f in pool if not es_ejercicio_del_libro(f["text"])]
    if not pool:
        logger.info(
            "[MicroLeccion] Lección %s sin fragmentos en el rango %s; usando búsqueda semántica (fallback)",
            leccion_id, leccion.paginas,
        )
        pool = search_fragments(
            query=leccion.tema_clave or leccion.nombre,
            asignatura=asignatura_nombre,
            grado=grado_nombre,
            top_k=POOL_CANDIDATOS_FRAGMENTOS,
        )
        pool = [f for f in pool if not es_ejercicio_del_libro(f["text"])]
    if not pool:
        raise HTTPException(
            status_code=502,
            detail="No se encontró contenido del libro para esta lección.",
        )
    # Muestreo Top-K por nivel (usa todos si hay menos fragmentos que Top-K).
    fragments = _seleccionar_fragmentos_nivel(pool, leccion_id, nivel)

    # Etiquetado SOLO con el número de página (nunca "Fragmento"): el LLM
    # repite literalmente las etiquetas que ve en su propio input (ver mismo
    # fix en chat/prompts.py::build_context_prompt).
    contexto = "\n\n".join(
        f"--- Página {f.get('page_num', '?')} ---\n{f['text']}" for f in fragments
    )
    fragmentos_texto = " ".join((f["text"] or "").lower() for f in fragments)

    # IDs de los fragmentos usados, para que /practicar use el MISMO contenido.
    chunk_ids = [f["chunk_id"] for f in fragments if f.get("chunk_id")]
    fragment_ids: list[int] = []
    if chunk_ids:
        fragment_ids = list(
            (
                await db.execute(
                    select(Fragmento.id).where(Fragmento.chunk_id_vectordb.in_(chunk_ids))
                )
            ).scalars().all()
        )

    # Generación con verificación de cobertura: 1 intento + 1 reintento si quedan
    # pocas tarjetas válidas tras descartar las que no se apoyan en los fragmentos.
    # Matemáticas usa el 70B (más confiable en aritmética); el resto, el Qwen 7B.
    modelo = modelo_para_asignatura(asignatura_nombre)
    micro: MicroLeccionResponse | None = None
    for intento in range(2):
        messages = _build_micro_leccion_messages(leccion.nombre, contexto, nivel, asignatura_nombre)
        if intento > 0:
            messages[-1]["content"] += "\n\nIMPORTANTE: Responde ÚNICAMENTE con el JSON válido, sin markdown ni explicaciones."
        data = llm_client.generate_json(messages, max_tokens=4096, model=modelo)
        if data is None:
            continue
        try:
            candidato = MicroLeccionResponse.model_validate(data)
        except ValidationError as e:
            logger.warning("[MicroLeccion] JSON no cumple el schema (lección %s): %s", leccion_id, e)
            continue
        if not candidato.tarjetas:
            continue
        _corregir_preguntas(candidato)
        # La cobertura es una red SECUNDARIA (el prompt ya obliga a usar solo el
        # libro). Si dejara la lección con CERO tarjetas, es peor el remedio que
        # la enfermedad: mejor devolver las tarjetas sin filtrar que un 502. Pasa
        # en rangos de portada/índice/presentación (p. ej. la lección 1 de un
        # libro completo, páginas 2-6), donde la teoría no aparece textualmente
        # en el rango y el filtro descarta todo.
        tarjetas_corregidas = list(candidato.tarjetas)
        candidato.tarjetas = _filtrar_tarjetas_por_cobertura(candidato.tarjetas, fragmentos_texto)
        if not candidato.tarjetas:
            logger.warning(
                "[MicroLeccion] Lección %s: la cobertura descartó TODAS las tarjetas; "
                "usando las %d sin filtrar para no devolver 502.",
                leccion_id, len(tarjetas_corregidas),
            )
            candidato.tarjetas = tarjetas_corregidas
        # Nos quedamos con el mejor candidato visto hasta ahora.
        if micro is None or len(candidato.tarjetas) > len(micro.tarjetas):
            micro = candidato
        if len(candidato.tarjetas) >= MIN_TARJETAS_VALIDAS:
            break
        logger.info(
            "[MicroLeccion] Lección %s: solo %d tarjetas válidas tras cobertura; reintentando…",
            leccion_id, len(candidato.tarjetas),
        )

    if micro is None or not micro.tarjetas:
        raise HTTPException(status_code=502, detail="No se pudo generar la micro-lección.")
    _formatear_miles(micro, es_matematicas="matem" in (asignatura_nombre or "").lower())
    tema_leccion = f"{leccion.tema_clave or ''} {leccion.nombre}".strip()
    _asignar_emojis(micro, tema_leccion, asignatura_nombre)
    micro.fragment_ids = fragment_ids
    micro.nivel_actual = nivel
    micro.es_ultimo_nivel = nivel >= max(NIVEL_TOPK)
    return micro


async def iniciar_leccion(
    estudiante_id: int, leccion_id: int, db: AsyncSession
) -> LeccionEnRuta:
    """Marca una lección 'disponible' como 'en_progreso'."""
    leccion = (
        await db.execute(select(Leccion).where(Leccion.id == leccion_id))
    ).scalar_one_or_none()
    if leccion is None:
        raise HTTPException(status_code=404, detail="Lección no encontrada")

    progreso = await _get_or_create_progreso(estudiante_id, leccion, db)
    if progreso.estado != EstadoLeccion.disponible:
        raise HTTPException(
            status_code=400,
            detail=f"La lección no está disponible (estado actual: {progreso.estado.value}).",
        )

    progreso.estado = EstadoLeccion.en_progreso
    progreso.fecha_inicio = datetime.now(timezone.utc)
    await db.commit()
    return _to_leccion_en_ruta(leccion, progreso)


async def completar_actividad_leccion(
    estudiante_id: int, leccion_id: int, puntaje: int, db: AsyncSession
) -> LeccionEnRuta:
    """Registra una actividad completada en una lección y, si corresponde,
    completa la lección, desbloquea la siguiente y actualiza racha + puntos."""
    leccion = (
        await db.execute(select(Leccion).where(Leccion.id == leccion_id))
    ).scalar_one_or_none()
    if leccion is None:
        raise HTTPException(status_code=404, detail="Lección no encontrada")

    progreso = await _get_or_create_progreso(estudiante_id, leccion, db)

    # Opción A: solo cuentan los ACIERTOS (puntaje >= 70). El campo
    # `actividades_completadas` lleva el conteo de aciertos (no de respuestas
    # totales), y `puntaje_promedio` es el promedio de esos aciertos. Una
    # respuesta < 70 NO avanza ni penaliza la lección: el estudiante reintenta.
    # Esto evita el "promedio histórico pegajoso" del criterio anterior.
    if puntaje >= PUNTAJE_MINIMO_COMPLETAR:
        prev = progreso.actividades_completadas
        progreso.puntaje_promedio = (progreso.puntaje_promedio * prev + puntaje) / (prev + 1)
        progreso.actividades_completadas = prev + 1

    ya_completada = progreso.estado == EstadoLeccion.completada
    if (
        not ya_completada
        and progreso.actividades_completadas >= progreso.actividades_requeridas
    ):
        progreso.estado = EstadoLeccion.completada
        progreso.fecha_completada = datetime.now(timezone.utc)

        # Desbloquear la siguiente lección (orden + 1).
        siguiente = (
            await db.execute(
                select(Leccion).where(
                    Leccion.libro_id == leccion.libro_id,
                    Leccion.orden == leccion.orden + 1,
                )
            )
        ).scalar_one_or_none()
        if siguiente is not None:
            prog_sig = await _get_or_create_progreso(estudiante_id, siguiente, db)
            if prog_sig.estado == EstadoLeccion.bloqueada:
                prog_sig.estado = EstadoLeccion.disponible

        # Gamificación: la racha y los puntos solo avanzan al COMPLETAR.
        await actualizar_racha(estudiante_id, db)
        usuario = (
            await db.execute(select(Usuario).where(Usuario.id == estudiante_id))
        ).scalar_one()
        usuario.puntos_totales += puntaje

    await db.commit()
    return _to_leccion_en_ruta(leccion, progreso)


async def _posicion_en_ranking(
    estudiante_id: int, grado_id: int | None, db: AsyncSession
) -> int:
    """Posición 1-based del estudiante en el ranking de su grado, con el MISMO
    orden que `obtener_ranking` (puntos_totales, luego lecciones completadas).
    Devuelve 0 si el estudiante no tiene grado. Se llama antes y después de
    otorgar puntos para calcular el cambio de posición."""
    if grado_id is None:
        return 0
    estudiantes = (
        await db.execute(
            select(Usuario.id, Usuario.puntos_totales).where(
                Usuario.grado_id == grado_id,
                Usuario.rol == RolUsuario.estudiante,
            )
        )
    ).all()
    comp_rows = (
        await db.execute(
            select(ProgresoLeccion.estudiante_id, func.count())
            .where(ProgresoLeccion.estado == EstadoLeccion.completada)
            .group_by(ProgresoLeccion.estudiante_id)
        )
    ).all()
    completadas = {est_id: total for est_id, total in comp_rows}
    ordenados = sorted(
        estudiantes,
        key=lambda r: (r.puntos_totales, completadas.get(r.id, 0)),
        reverse=True,
    )
    for pos, r in enumerate(ordenados, start=1):
        if r.id == estudiante_id:
            return pos
    return 0


async def completar_nivel(
    estudiante_id: int,
    leccion_id: int,
    nivel: int,
    actividades_aprobadas: int,
    puntaje: int,
    db: AsyncSession,
    total_actividades: int | None = None,
) -> CompletarNivelResponse:
    """Evalúa el resultado de practicar un NIVEL y avanza/repite según el umbral.

    - Aprueba el nivel si `actividades_aprobadas >= _aprobadas_requeridas(...)`.
    - Cada nivel superado por PRIMERA vez otorga puntos (30/30/40) de forma
      inmediata (idempotente vía `nivel_completado`: rehacerlo no re-suma).
    - Niveles 1/2 aprobados: sube `nivel_actual`, la lección sigue en_progreso.
    - Nivel 3 aprobado: lección `completada` (corona 👑), desbloquea la siguiente
      y otorga racha.
    - No aprobado: `intentos_nivel += 1`, sin avanzar de nivel ni sumar puntos.
    """
    leccion = (
        await db.execute(select(Leccion).where(Leccion.id == leccion_id))
    ).scalar_one_or_none()
    if leccion is None:
        raise HTTPException(status_code=404, detail="Lección no encontrada")

    nivel = nivel if nivel in NIVEL_APROBADAS_REQUERIDAS else 1
    progreso = await _get_or_create_progreso(estudiante_id, leccion, db)

    requeridas = _aprobadas_requeridas(nivel, total_actividades)
    tema = leccion.tema_clave or leccion.nombre

    if actividades_aprobadas < requeridas:
        progreso.intentos_nivel += 1
        await db.commit()
        return CompletarNivelResponse(
            nivel_completado=progreso.nivel_completado,
            nivel_actual=progreso.nivel_actual,
            aprobado=False,
            mensaje_feedback=(
                f"¡Casi! Necesitas {requeridas} correctas para avanzar. "
                "¡Inténtalo de nuevo! 💪"
            ),
        )

    usuario = (
        await db.execute(select(Usuario).where(Usuario.id == estudiante_id))
    ).scalar_one()
    posicion_antes = await _posicion_en_ranking(estudiante_id, usuario.grado_id, db)

    # Aprobado: registrar el nivel superado (sin regresar si ya iba más adelante).
    # Solo se otorgan puntos si es un nivel NUEVO (no rehacer uno ya aprobado).
    es_nivel_nuevo = nivel > progreso.nivel_completado
    progreso.nivel_completado = max(progreso.nivel_completado, nivel)
    progreso.intentos_nivel = 0
    puntos_ganados = PUNTOS_POR_NIVEL.get(nivel, 0) if es_nivel_nuevo else 0
    if puntos_ganados:
        usuario.puntos_totales += puntos_ganados

    if nivel >= max(NIVEL_APROBADAS_REQUERIDAS):  # nivel 3 → dominada
        progreso.nivel_actual = nivel
        if progreso.estado != EstadoLeccion.completada:
            progreso.estado = EstadoLeccion.completada
            progreso.fecha_completada = datetime.now(timezone.utc)
            progreso.puntaje_promedio = 100.0

            siguiente = (
                await db.execute(
                    select(Leccion).where(
                        Leccion.libro_id == leccion.libro_id,
                        Leccion.orden == leccion.orden + 1,
                    )
                )
            ).scalar_one_or_none()
            if siguiente is not None:
                prog_sig = await _get_or_create_progreso(estudiante_id, siguiente, db)
                if prog_sig.estado == EstadoLeccion.bloqueada:
                    prog_sig.estado = EstadoLeccion.disponible

            await actualizar_racha(estudiante_id, db)
        mensaje = f"¡Lección dominada! Eres un experto en {tema} 👑"
    else:
        progreso.nivel_actual = max(progreso.nivel_actual, nivel + 1)
        if progreso.estado in (EstadoLeccion.disponible, EstadoLeccion.bloqueada):
            progreso.estado = EstadoLeccion.en_progreso
        mensaje = f"¡Nivel {nivel} completado! Ahora profundizaremos más 🚀"

    await db.commit()

    posicion_despues = await _posicion_en_ranking(estudiante_id, usuario.grado_id, db)
    # cambio positivo = subió puestos (la posición numérica bajó).
    cambio = (posicion_antes - posicion_despues) if (posicion_antes and posicion_despues) else 0
    return CompletarNivelResponse(
        nivel_completado=progreso.nivel_completado,
        nivel_actual=progreso.nivel_actual,
        aprobado=True,
        mensaje_feedback=mensaje,
        puntos_ganados=puntos_ganados,
        puntos_totales=usuario.puntos_totales,
        posicion_ranking=posicion_despues,
        cambio_posicion=cambio,
    )


ZONA_GUATEMALA = ZoneInfo("America/Guatemala")


def hoy_guatemala() -> date:
    """Fecha "de hoy" en hora de Guatemala (UTC-6), no la del servidor.

    El servidor (Railway/Docker) corre en UTC. Si la racha se calculara con
    `date.today()` del servidor, un estudiante que practica de noche en
    Guatemala (después de las 6pm, que ya es el día siguiente en UTC) vería
    su "día" cambiar antes de tiempo con respecto a su reloj real.
    """
    return datetime.now(ZONA_GUATEMALA).date()


async def actualizar_racha(estudiante_id: int, db: AsyncSession) -> None:
    """Actualiza la racha del estudiante según su última actividad.

    Suma puntos NO es responsabilidad de esta función (lo hace el caller).
    No hace commit: lo hace la función que la invoca.
    """
    usuario = (
        await db.execute(select(Usuario).where(Usuario.id == estudiante_id))
    ).scalar_one()

    hoy = hoy_guatemala()
    ultima = usuario.ultima_actividad

    if ultima == hoy:
        return  # ya contó hoy

    if ultima is not None and (hoy - ultima).days == 1:
        usuario.racha_actual += 1  # ayer → continúa la racha
    else:
        usuario.racha_actual = 1  # primera vez o racha rota

    if usuario.racha_actual > usuario.mejor_racha:
        usuario.mejor_racha = usuario.racha_actual

    usuario.ultima_actividad = hoy


async def obtener_racha(estudiante_id: int, db: AsyncSession) -> RachaResponse:
    usuario = (
        await db.execute(select(Usuario).where(Usuario.id == estudiante_id))
    ).scalar_one()
    return RachaResponse(
        racha_actual=usuario.racha_actual,
        mejor_racha=usuario.mejor_racha,
        activo_hoy=(usuario.ultima_actividad == hoy_guatemala()),
    )


async def obtener_ranking(
    grado_id: int | None, estudiante_id: int, db: AsyncSession
) -> RankingResponse:
    """Ranking de los estudiantes del grado, por puntos y lecciones completadas."""
    estudiantes = list(
        (
            await db.execute(
                select(Usuario).where(
                    Usuario.grado_id == grado_id,
                    Usuario.rol == RolUsuario.estudiante,
                )
            )
        ).scalars().all()
    )

    # Lecciones completadas por estudiante (agregado en una sola query).
    comp_rows = (
        await db.execute(
            select(ProgresoLeccion.estudiante_id, func.count())
            .where(ProgresoLeccion.estado == EstadoLeccion.completada)
            .group_by(ProgresoLeccion.estudiante_id)
        )
    ).all()
    completadas_por = {est_id: total for est_id, total in comp_rows}

    estudiantes.sort(
        key=lambda u: (u.puntos_totales, completadas_por.get(u.id, 0)),
        reverse=True,
    )

    ranking: list[RankingEstudiante] = []
    mi_posicion = 0
    for posicion, u in enumerate(estudiantes, start=1):
        ranking.append(
            RankingEstudiante(
                posicion=posicion,
                nombre=u.nombre,
                apellido=u.apellido,
                lecciones_completadas=completadas_por.get(u.id, 0),
                puntos_totales=u.puntos_totales,
                racha_actual=u.racha_actual,
            )
        )
        if u.id == estudiante_id:
            mi_posicion = posicion

    return RankingResponse(ranking=ranking, mi_posicion=mi_posicion)


async def obtener_mi_grado(current_user: Usuario, db: AsyncSession) -> MiGradoResponse:
    """Grado del estudiante autenticado (para el sidebar). None si no tiene grado."""
    if current_user.grado_id is None:
        return MiGradoResponse(id=None, nombre=None)
    nombre = (
        await db.execute(
            select(Grado.nombre).where(Grado.id == current_user.grado_id)
        )
    ).scalar_one_or_none()
    return MiGradoResponse(id=current_user.grado_id, nombre=nombre)
