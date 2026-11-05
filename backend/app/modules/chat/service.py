"""Lógica de negocio del chat: orquesta RAG + LLM + historial."""
import asyncio
import logging
import re
import unicodedata
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.llm.client import grado_usa_finetuned, llm_client, rol_para_asignatura
from app.models.conversacion import Conversacion
from app.models.mensaje import Mensaje, RolMensaje
from app.models.asignatura import Asignatura
from app.models.usuario import Usuario
from app.models.grado import Grado
from app.models.leccion import Leccion
from app.models.libro import LibroTexto
from app.modules.rag.search import (
    TOP_K,
    es_ejercicio_del_libro,
    is_context_relevant,
    search_fragments,
)
from app.modules.chat.prompts import build_context_prompt, build_messages
from app.modules.rag.paginas import etiqueta_paginas
from app.modules.lecciones.service import _parsear_rango_paginas, actualizar_racha

logger = logging.getLogger(__name__)

# Respuesta fija (determinística) cuando la pregunta cae fuera de los libros.
# No depende de que el LLM obedezca: se devuelve sin llamar al modelo.
RESPUESTA_FUERA_DE_CONTEXTO = (
    "No encuentro información sobre eso en tus libros de clase. "
    "¿Quieres preguntarme sobre los temas que estamos viendo?"
)

# Candidatos que se piden a la búsqueda semántica antes de filtrar ejercicios;
# al LLM llegan como mucho TOP_K (ver el filtro en procesar_pregunta).
CANDIDATOS_CHAT = 2 * TOP_K

# Respaldo cuando el LLM falla o responde vacío: el estudiante ve un mensaje
# claro en vez de un error 500.
RESPUESTA_LLM_NO_DISPONIBLE = (
    "Lo siento, en este momento no puedo responder. "
    "Intenta de nuevo en un momento, por favor."
)

# Frases que indican que la respuesta es un rechazo por grounding. Si el LLM
# rechaza aunque el contexto haya pasado el umbral de relevancia, no tiene
# sentido mostrar referencias (páginas) de fragmentos que no se usaron.
PALABRAS_RECHAZO = (
    "no encuentro",
    "no tengo información",
    "no tengo informacion",
    "fuera del tema",
    "no puedo responder",
    "no está en",
    "no esta en",
    "lo siento",
    "no aparece",
)


def _es_rechazo(respuesta: str) -> bool:
    """True si la respuesta del tutor es un rechazo por estar fuera de los libros."""
    texto = respuesta.lower()
    return any(p in texto for p in PALABRAS_RECHAZO)


# Detección de referencias a una página concreta ("explícame la página 12").
# Cubre: página / pagina / pág / pag / pág. / pag. / page / p. / p, seguido de un
# número de 1 a 3 dígitos. La búsqueda semántica no entiende estas referencias,
# así que cuando se detectan se filtra por page_num en ChromaDB.
_RE_PAGINA = re.compile(
    r"\b(?:p[aá]g(?:ina)?\.?|page|p\.?)\s*(\d{1,3})\b",
    re.IGNORECASE,
)


def _detectar_pagina(texto: str) -> int | None:
    """Devuelve el número de página (1-999) mencionado en el texto, o None.

    Reconoce 'página X', 'la página X', 'pág X', 'pág. X', 'pag X', 'page X',
    'p. X' y 'p X'.
    """
    m = _RE_PAGINA.search(texto or "")
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 999 else None


# Rango o par de páginas: "páginas 40 a 45", "pág. 40 a la 45", "págs 40-45", "páginas 40 y 41",
# "página 40 hasta la página 45", y sin la palabra "página": "de la 40 a la 45".
# Un "40-45" suelto (sin "página") NO cuenta: en Matemáticas es una resta.
_RE_RANGO_PAGINAS = re.compile(
    r"\b(?:p[aá]g(?:inas?|s)?\.?|pages?|pp?\.?)\s*(\d{1,3})\s*(-|–|\bal?\b|\bhasta\b|\by\b)\s*"
    r"(?:la\s+)?(?:p[aá]g(?:ina)?\.?\s*)?(\d{1,3})\b"
    r"|\bde(?:sde)?\s+la\s+(\d{1,3})\s+(?:a|hasta)\s+la\s+(\d{1,3})\b",
    re.IGNORECASE,
)

# Páginas que se resumen como máximo en una consulta por rango (contexto y costo acotados).
MAX_PAGINAS_RANGO = 6


def _detectar_paginas(texto: str) -> list[int]:
    """Páginas pedidas, en orden y SIN recortar: [] si no menciona página, [n] si es una sola
    (como _detectar_pagina), varias si es un rango ("40 a 45" -> 40..45) o un par ("40 y 41")."""
    m = _RE_RANGO_PAGINAS.search(texto or "")
    if not m:
        n = _detectar_pagina(texto)
        return [] if n is None else [n]
    if m.group(4):
        a, b, sep = int(m.group(4)), int(m.group(5)), "a"
    else:
        a, b, sep = int(m.group(1)), int(m.group(3)), m.group(2).lower()
    paginas = {a, b} if sep == "y" else set(range(min(a, b), max(a, b) + 1))
    return sorted(p for p in paginas if 1 <= p <= 999)


# Resumen por rango: UNA llamada por página con solo sus fragmentos. Con las 6 páginas juntas el
# LLM reasignaba contenido entre páginas (prod, Ciencias 9no p. 40-45: lo de la 42 bajo la 41).
INSTRUCCION_RESUMEN_PAGINA = (
    "Resume en 2 a 4 oraciones lo que dice esta página del libro, usando SOLO el contenido "
    "anterior. No agregues nada que no esté ahí y no menciones números de página. Si la página "
    "es un ejercicio (verdadero o falso, completar, preguntas para responder), di que es un "
    "ejercicio y sobre qué tema, sin presentar sus enunciados como hechos: pueden ser falsos a "
    "propósito. No resuelvas el ejercicio: no escribas sus respuestas ni nombres conceptos que no "
    "estén escritos en la página. Responde directamente con el resumen, sin título."
)
TEMPERATURA_RESUMEN_PAGINA = 0.1
SIN_CONTENIDO = "sin contenido en tu libro."
NO_SE_PUDO_RESUMIR = "no se pudo resumir esta página en este momento; intenta de nuevo."
_RE_TITULO_PAGINA = re.compile(r"^\W*p[aá]gina\s+\d+\W*", re.IGNORECASE)


async def _resumir_pagina(fragments: list[dict], grado: str | None, asignatura: str | None) -> str:
    """Resumen de una página (sus fragmentos); sin fragmentos no llama al LLM; si falla, lo dice."""
    if not fragments:
        return SIN_CONTENIDO
    messages = build_messages(build_context_prompt(fragments), [], INSTRUCCION_RESUMEN_PAGINA,
                              grado, asignatura)
    try:
        respuesta = await asyncio.to_thread(
            llm_client.chat, messages, max_tokens=400,
            temperature=TEMPERATURA_RESUMEN_PAGINA, rol=rol_para_asignatura(asignatura),
        )
    except Exception as e:  # noqa: BLE001 — una página caída no tumba el resto del rango
        logger.error(f"[Chat] Fallo al resumir la página {fragments[0].get('page_num')}: {e}")
        respuesta = None
    return _RE_TITULO_PAGINA.sub("", (respuesta or "").strip()) or NO_SE_PUDO_RESUMIR


async def _resumir_rango(paginas: list[int], fragments: list[dict],
                         grado: str | None, asignatura: str | None, n_pedidas: int) -> str:
    """'Página N: <resumen>' por página, en orden, con las llamadas al LLM en paralelo. Si pidió más
    páginas de las que se resumen, una línea inicial lo dice."""
    resumenes = await asyncio.gather(*(
        _resumir_pagina([f for f in fragments if f.get("page_num") == p], grado, asignatura)
        for p in paginas
    ))
    texto = "\n\n".join(f"Página {p}: {r}" for p, r in zip(paginas, resumenes))
    if n_pedidas > len(paginas):
        # Sin "página N" en el texto: no es una cita (no la toca la validación de citas).
        texto = (f"Pediste {n_pedidas} páginas; resumo solo las primeras {len(paginas)} "
                 f"(de la {paginas[0]} a la {paginas[-1]}).\n\n{texto}")
    return texto


# Cita de página en una respuesta del LLM: "página 8", "páginas 12 y 13", "págs. 4-6",
# "pág. 7", opcionalmente en negrita ("**página 25**").
_RE_CITA = re.compile(
    r"\*{0,2}p[aá]g(?:inas?|s?\.)\s*(\d{1,3}(?:\s*(?:,|y|-|–|al?)\s*\d{1,3})*)\*{0,2}",
    re.IGNORECASE,
)


def _numeros_cita(lista: str) -> list[int]:
    """'12 y 13' -> [12, 13]; '4-6' / '4 a 6' -> [4, 5, 6]."""
    paginas = []
    for parte in re.split(r"\s*(?:,|\by\b)\s*", lista):
        m = re.fullmatch(r"(\d+)\s*(?:-|–|\bal?\b)\s*(\d+)", parte)
        if m and 0 < int(m[2]) - int(m[1]) <= 20:
            paginas += range(int(m[1]), int(m[2]) + 1)
        elif m:
            paginas += [int(m[1]), int(m[2])]
        elif parte.isdigit():
            paginas.append(int(parte))
    return paginas


def _paginas_citadas(respuesta: str) -> list[int]:
    """Extrae los números de página citados en el texto (ver _RE_CITA)."""
    return [p for m in _RE_CITA.finditer(respuesta) for p in _numeros_cita(m.group(1))]


_CITA = _RE_CITA.pattern
# De más a menos específica; cada una se aplica solo a citas con alguna página no recuperada.
_QUITAR_CITA = [
    # "(página 82)", "(ver página 3)", "(en la página 7)" -> se borra
    (re.compile(rf"\s*\(\s*(?:ver\s+|en\s+(?:la\s+|las\s+)?)?{_CITA}\s*\)", re.IGNORECASE), ""),
    # "revisar la página 45 de tu libro" -> "revisar tu libro"
    (re.compile(rf"\b(?:la|las)\s+{_CITA}\s+(?=de\s+tu\s+libro)de\s+", re.IGNORECASE), ""),
    # "en la página 32" -> "" si justo antes se nombra el libro; si no, "en tu libro"
    (re.compile(rf"\s*\b(?:en|de|según)\s+(?:la|las)\s+{_CITA}", re.IGNORECASE), None),
    # "en tus páginas 36 y 37" -> "en tu libro"
    (re.compile(rf"\b(?:tus|sus|mis|las|la)\s+{_CITA}", re.IGNORECASE), "tu libro"),
    # resto: "página 8" -> "tu libro"
    (re.compile(_CITA, re.IGNORECASE), "tu libro"),
]


def _quitar_citas_invalidas(respuesta: str, paginas_disponibles: set[int]) -> str:
    """Quita (o cambia por "tu libro") las citas a páginas que no están entre los
    fragmentos recuperados; las citas válidas quedan intactas. Determinístico."""
    texto = respuesta
    for patron, reemplazo in _QUITAR_CITA:
        def sustituir(m, texto_actual):
            if set(_numeros_cita(m.group(1))) <= paginas_disponibles:
                return m.group(0)
            if reemplazo is not None:
                return reemplazo
            return "" if "libro" in texto_actual[max(0, m.start() - 40):m.start()].lower() else " en tu libro"
        texto = patron.sub(lambda m, t=texto: sustituir(m, t), texto)
    return texto


def _citas_validas(respuesta: str, fragments: list[dict]) -> bool:
    """
    True si todas las páginas citadas en la respuesta existen entre los
    fragmentos recuperados. Si la respuesta no cita ninguna página, se considera
    válida (no es una alucinación de citas).

    Capa 3 del grounding: detecta cuando el LLM inventa una cita de página que no
    está respaldada por el contexto recuperado. El campo de página en `fragments`
    es `page_num` (ver rag/search.py:93).
    """
    citadas = _paginas_citadas(respuesta)
    if not citadas:
        return True
    paginas_disponibles = {
        f.get("page_num") for f in fragments if f.get("page_num") is not None
    }
    return all(p in paginas_disponibles for p in citadas)


def _referencia_paginas(fragments: list[dict], asignatura_nombre: str | None) -> str:
    """Construye la línea de referencia determinística ("📖 Basado en tu libro
    de X, páginas Y-Z.") a partir de los fragmentos EFECTIVAMENTE usados como
    contexto (ya filtrados por rechazo/citas inválidas). No depende de que el
    LLM cite bien la página: si hay fragmentos, hay referencia; si no, no."""
    paginas = [f.get("page_num") for f in fragments if f.get("page_num") is not None]
    if not paginas:
        return ""
    materia = asignatura_nombre or "tu libro"
    return f"\n\n📖 Basado en tu libro de {materia}, {etiqueta_paginas(paginas)}."


def _palabras(texto: str) -> set[str]:
    """Palabras de 5+ letras, en minúsculas y sin tildes (para comparar vocabulario)."""
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return set(re.findall(r"[a-zñ]{5,}", t))


# Sin citas en el texto, un fragmento cuenta como usado si comparte con la respuesta al menos
# este número de palabras y este tanto del mejor (calibrado con 25 respuestas reales del piloto:
# las páginas que el LLM cita son siempre las de mayor solape).
MIN_PALABRAS_USADO = 3
FRACCION_DEL_MEJOR = 0.6


def _fragmentos_usados(respuesta: str, fragments: list[dict]) -> list[dict]:
    """Fragmentos que la respuesta usó, de más a menos solape de vocabulario (el primero es la
    página principal). Si la respuesta cita páginas (ya validadas), solo esas; si no, los que
    comparten vocabulario con ella; como mínimo, el de más solape."""
    if not fragments:
        return []
    palabras = _palabras(respuesta)
    puntaje = {id(f): len(_palabras(f.get("text", "")) & palabras) for f in fragments}
    ordenados = sorted(fragments, key=lambda f: -puntaje[id(f)])
    citadas = set(_paginas_citadas(respuesta))
    if citadas:
        usados = [f for f in ordenados if f.get("page_num") in citadas]
    else:
        mejor = puntaje[id(ordenados[0])]
        usados = [f for f in ordenados
                  if puntaje[id(f)] >= max(MIN_PALABRAS_USADO, FRACCION_DEL_MEJOR * mejor)]
    return usados or ordenados[:1]


async def _leccion_de_pagina(db: AsyncSession, libro_id: int | None, pagina: int | None) -> dict | None:
    """Lección del libro cuyo rango de páginas contiene la página (para "Pon a prueba…")."""
    if libro_id is None or pagina is None:
        return None
    for leccion in (await db.execute(select(Leccion).where(Leccion.libro_id == libro_id))).scalars():
        rango = _parsear_rango_paginas(leccion.paginas)
        if rango and rango[0] <= pagina <= rango[1]:
            return {"id": leccion.id, "nombre": leccion.nombre}
    return None


async def _titulos_libros(db: AsyncSession, libro_ids: set) -> dict[int, str]:
    ids = {i for i in libro_ids if i is not None}
    if not ids:
        return {}
    return dict((await db.execute(select(LibroTexto.id, LibroTexto.titulo).where(LibroTexto.id.in_(ids)))).all())


# Marcador fijo con el que SIEMPRE empieza el footer de _referencia_paginas.
# Nunca aparece en input de un usuario ni en teoría del libro, así que
# buscarlo como substring es seguro.
_MARCADOR_FOOTER_PAGINA = "\n\n📖 Basado en tu libro de "


def _sin_footer_pagina(contenido: str) -> str:
    """Quita el footer determinístico de página de una respuesta ya guardada,
    para NO incluirlo en el historial que se le pasa al LLM.

    Si el modelo ve su propio turno anterior terminando en "📖 Basado en tu
    libro de...", tiende a imitar esa frase literalmente en el turno
    siguiente (in-context, no es un patrón aprendido en el fine-tuning: pasa
    igual con Together AI) — produciendo una segunda línea casi idéntica con
    una página distinta a la que arma nuestro código. Cortar el footer del
    historial elimina la fuente de la imitación sin tocar el footer que sí
    se le muestra al estudiante (ese queda intacto en `Mensaje.contenido`)."""
    idx = contenido.find(_MARCADOR_FOOTER_PAGINA)
    if idx == -1:
        return contenido
    return contenido[:idx].rstrip()


async def obtener_o_crear_conversacion(
    db: AsyncSession,
    conversacion_id: int | None,
    estudiante_id: int,
    asignatura_id: int,
) -> Conversacion:
    """Obtiene una conversación existente o crea una nueva."""
    if conversacion_id:
        result = await db.execute(
            select(Conversacion).where(
                Conversacion.id == conversacion_id,
                Conversacion.estudiante_id == estudiante_id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv

    # Crear nueva
    conv = Conversacion(
        estudiante_id=estudiante_id,
        asignatura_id=asignatura_id,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def obtener_historial(db: AsyncSession, conversacion_id: int) -> list[dict]:
    """Obtiene los mensajes previos de una conversación, para usar como
    historial en el prompt del LLM. A los mensajes del asistente se les quita
    el footer determinístico de página (ver _sin_footer_pagina) — el
    estudiante lo sigue viendo en la conversación guardada, pero el LLM no lo
    ve en su propio historial."""
    result = await db.execute(
        select(Mensaje)
        .where(Mensaje.conversacion_id == conversacion_id)
        .order_by(Mensaje.fecha_creacion)
    )
    mensajes = result.scalars().all()
    return [
        {
            "rol": m.rol.value,
            "contenido": (
                _sin_footer_pagina(m.contenido)
                if m.rol == RolMensaje.asistente
                else m.contenido
            ),
        }
        for m in mensajes
    ]


async def recuperar_contexto(
    pregunta: str, asignatura_nombre: str | None, grado_nombre: str | None
) -> tuple[list[dict], bool, list[int]]:
    """Paso 2 del chat (sin LLM): fragmentos para la pregunta. Devuelve
    (fragments, consulta_por_pagina, paginas): paginas = [] en la búsqueda semántica,
    [n] si pidió una página y hasta MAX_PAGINAS_RANGO si pidió un rango. Determinístico
    para un mismo índice; lo reusa scripts/corregir_citas_chat.py."""
    paginas = _detectar_paginas(pregunta)[:MAX_PAGINAS_RANGO]
    consulta_por_pagina = False
    if paginas:
        fragments = await asyncio.to_thread(
            search_fragments,
            query=pregunta,
            asignatura=asignatura_nombre,
            grado=grado_nombre,
            page_num=paginas[0] if len(paginas) == 1 else None,
            page_nums=paginas if len(paginas) > 1 else None,
        )
        if fragments:
            consulta_por_pagina = True
            logger.info(
                f"[Chat] Consulta por {etiqueta_paginas(paginas)}: "
                f"{len(fragments)} fragmentos por filtro de page_num"
            )
        else:
            logger.info(
                f"[Chat] {etiqueta_paginas(paginas)} sin fragmentos; "
                "fallback a búsqueda semántica normal"
            )
            paginas = []
            fragments = await asyncio.to_thread(
                search_fragments,
                query=pregunta,
                asignatura=asignatura_nombre,
                grado=grado_nombre,
                top_k=CANDIDATOS_CHAT,
            )
    else:
        fragments = await asyncio.to_thread(
            search_fragments,
            query=pregunta,
            asignatura=asignatura_nombre,
            grado=grado_nombre,
            top_k=CANDIDATOS_CHAT,
        )

    # Filtro de ejercicios SOLO en búsqueda semántica (sin página específica):
    # en el chat conceptual no queremos que un ejercicio del libro ("Mesa lista",
    # "Ahora es tu turno"…) se cuele como si fuera teoría. Con página específica
    # NO se filtra: el estudiante pidió esa página tal cual, sea teoría o
    # ejercicio. Si el filtro dejara la lista vacía, se conservan los originales
    # para no dejar al estudiante sin respuesta. Se recuperan CANDIDATOS_CHAT y,
    # tras filtrar, se rellena hasta TOP_K con los siguientes por distancia: así
    # un ejercicio descartado no deja fuera la teoría que venía justo detrás
    # (caso real: la tabla de propiedades de la multiplicación, puesto 6).
    if not paginas:
        filtrados = [f for f in fragments if not es_ejercicio_del_libro(f["text"])]
        fragments = (filtrados or fragments)[:TOP_K]
    return fragments, consulta_por_pagina, paginas


async def procesar_pregunta(
    db: AsyncSession,
    pregunta: str,
    conversacion_id: int | None,
    asignatura_id: int,
    estudiante: Usuario,
) -> dict:
    """
    Pipeline completo del chat:
    1. Obtener/crear conversación
    2. Buscar contexto con RAG
    3. Construir prompt con historial
    4. Llamar al LLM
    5. Guardar mensajes
    6. Devolver respuesta con referencias
    """
    # 1. Conversación
    conv = await obtener_o_crear_conversacion(
        db, conversacion_id, estudiante.id, asignatura_id
    )

    # Obtener nombre de asignatura y grado para filtrar RAG
    asig_result = await db.execute(
        select(Asignatura).where(Asignatura.id == asignatura_id)
    )
    asignatura = asig_result.scalar_one_or_none()
    asignatura_nombre = asignatura.nombre if asignatura else None

    grado_nombre = None
    if estudiante.grado_id:
        grado_result = await db.execute(
            select(Grado).where(Grado.id == estudiante.grado_id)
        )
        grado = grado_result.scalar_one_or_none()
        grado_nombre = grado.nombre if grado else None

    # 2. Búsqueda RAG
    # Si el estudiante se refiere a una página concreta ("explícame la página
    # 12"), se busca FILTRANDO por page_num (la búsqueda semántica no entiende
    # referencias a páginas). Si esa página no existe, se cae a la búsqueda
    # semántica normal para no romper el flujo.
    # to_thread: search_fragments es síncrona (embedding con torch + query a
    # Chroma) y bloquearía el único worker mientras corre.
    fragments, consulta_por_pagina, paginas = await recuperar_contexto(
        pregunta, asignatura_nombre, grado_nombre
    )
    # Rango: páginas pedidas sin fragmentos (se dicen "sin contenido en tu libro"; citarlas es válido).
    faltantes = ([p for p in paginas if p not in {f.get("page_num") for f in fragments}]
                 if len(paginas) > 1 else [])
    frags_validacion = fragments + [{"page_num": p} for p in faltantes]

    # Historial (lo usa el prompt del LLM y el título del primer mensaje).
    history = await obtener_historial(db, conv.id)

    # 3-4. Grounding determinístico: si el contexto NO es relevante, no se
    # llama al LLM y se devuelve un mensaje fijo de rechazo. Así la garantía
    # no depende de que el modelo obedezca el prompt.
    # Una consulta por página se considera relevante aunque no haya solape
    # semántico: el estudiante pidió explícitamente esa página y ya tenemos su
    # contenido filtrado por page_num (el grounding se mantiene: el contexto
    # sigue siendo SOLO el del libro).
    es_rango = consulta_por_pagina and len(paginas) > 1
    if es_rango:
        # Lo arma el código: una llamada al LLM por página (ver _resumir_rango).
        respuesta = await _resumir_rango(paginas, fragments, grado_nombre, asignatura_nombre,
                                         len(_detectar_paginas(pregunta)))
        fragments_referencia = fragments
    elif consulta_por_pagina or is_context_relevant(fragments):
        context = build_context_prompt(fragments)
        # Para consultas por página, se refuerza el prompt del LLM sin modificar
        # build_messages: se guarda la pregunta ORIGINAL en la BD, pero al LLM se
        # le envía una versión con la instrucción de explicar esa página.
        pregunta_llm = pregunta
        if consulta_por_pagina:
            pregunta_llm = (
                f"{pregunta}\n\n[El estudiante pregunta sobre el contenido de la "
                f"página {paginas[0]}. Explícale el contenido de esa página "
                f"de forma clara y pedagógica, usando ÚNICAMENTE el contexto anterior.]"
            )
        messages = build_messages(
            context, history, pregunta_llm, grado_nombre, asignatura_nombre
        )
        logger.info(
            f"[Chat] System prompt adaptado a grado='{grado_nombre}', "
            f"asignatura='{asignatura_nombre}'"
        )
        logger.info(
            f"[Chat] Contexto relevante: enviando al LLM con {len(fragments)} fragmentos"
        )
        # Cohorte experimental (objetivo específico 3 de tesis, A/B por grado):
        # intenta el modelo fine-tuned en Modal primero; si falla o tarda más
        # del timeout configurado (cold start, contenedor caído, etc.), degrada
        # SIN error visible al modelo base de Together — el estudiante nunca ve
        # la diferencia salvo la respuesta en sí.
        respuesta = None
        if grado_usa_finetuned(estudiante.grado_id):
            try:
                # to_thread: chat_finetuned() puede bloquear hasta
                # MODAL_FINETUNED_TIMEOUT_SEGUNDOS reintentando un cold start;
                # con --workers 1, hacerlo en el hilo del event loop congelaría
                # el backend entero para todos los estudiantes mientras tanto.
                respuesta = await asyncio.to_thread(llm_client.chat_finetuned, messages)
                logger.info(f"[Chat] Respuesta del fine-tuned (grado_id={estudiante.grado_id})")
            except Exception as e:  # noqa: BLE001 — cualquier fallo del endpoint de Modal degrada a Together
                logger.warning(f"[Chat] Fine-tuned no disponible, fallback a base: {e}")
        if not respuesta:
            # Matemáticas usa su propio modelo (LLM_MODEL_MATEMATICAS); el resto, LLM_MODEL.
            # to_thread: llamada síncrona a Together que, sin esto, bloquearía el
            # único worker (--workers 1) para todos los estudiantes mientras dura.
            try:
                respuesta = await asyncio.to_thread(
                    llm_client.chat, messages, rol=rol_para_asignatura(asignatura_nombre)
                )
            except Exception as e:  # noqa: BLE001 — Together caído/timeout: respaldo, no un 500
                logger.error(f"[Chat] Fallo al llamar al LLM: {e}")
        if not respuesta:
            # Respuesta vacía (content=None) o error del API. Contiene "lo siento",
            # así que _es_rechazo() la trata como rechazo y no se anexan páginas.
            respuesta = RESPUESTA_LLM_NO_DISPONIBLE
        fragments_referencia = fragments
    else:
        logger.info(
            "[Chat] Contexto NO relevante: respuesta determinística de rechazo (sin LLM)"
        )
        respuesta = RESPUESTA_FUERA_DE_CONTEXTO
        fragments_referencia = []

    # Si el LLM rechazó la pregunta (aunque el contexto pasara el umbral), no
    # mostrar referencias: las páginas recuperadas no respaldan esa respuesta.
    #
    # Capa 3 del grounding: si el modelo citó una página que no está entre los
    # fragmentos recuperados (alucinación de cita), se quita esa cita del texto
    # (log de auditoría) y se mantiene la referencia determinística.
    # Un rango no es rechazo aunque un resumen diga "no aparece": lo arma el código.
    if not es_rango and _es_rechazo(respuesta):
        fragments_referencia = []
    if not _citas_validas(respuesta, frags_validacion):
        logger.warning(
            "[Chat] Grounding: el modelo citó una página que NO está en los "
            "fragmentos recuperados. Pregunta=%r, respuesta=%r, "
            "paginas_citadas=%r, paginas_disponibles=%r",
            pregunta,
            respuesta,
            _paginas_citadas(respuesta),
            {f.get("page_num") for f in fragments},
        )
        # Antes (opción A) se vaciaban las referencias pero la cita errónea quedaba
        # en el texto que ve el estudiante. Ahora se quita del texto y se conserva
        # la referencia determinística de las páginas recuperadas.
        respuesta = _quitar_citas_invalidas(
            respuesta, {f.get("page_num") for f in frags_validacion if f.get("page_num") is not None}
        )

    # Solo las páginas que la respuesta usó (las citadas o, sin citas, las que comparten
    # vocabulario con ella), no todas las recuperadas.
    fragments_referencia = _fragmentos_usados(respuesta, fragments_referencia)

    # Referencia de página SIEMPRE visible (determinística): toda respuesta con fragmentos
    # lleva el pie. Si el pre-grounding o el LLM rechazaron la pregunta, no hay nada que anexar.
    if fragments_referencia:
        respuesta = respuesta + _referencia_paginas(fragments_referencia, asignatura_nombre)

    # 5. Guardar mensajes
    titulos = await _titulos_libros(db, {f.get("libro_id") for f in fragments_referencia})
    referencias_json = [
        {"page_num": f.get("page_num"), "libro_id": f.get("libro_id"), "distance": f.get("distance"),
         "libro_titulo": titulos.get(f.get("libro_id"))}
        for f in fragments_referencia
    ]
    # Lección de la página principal: el botón "🎯 Pon a prueba lo que aprendiste" abre su
    # práctica libre (no toca la ruta).
    leccion = (await _leccion_de_pagina(db, fragments_referencia[0].get("libro_id"),
                                        fragments_referencia[0].get("page_num"))
               if fragments_referencia else None)

    msg_usuario = Mensaje(
        conversacion_id=conv.id,
        rol=RolMensaje.usuario,
        contenido=pregunta,
    )
    msg_asistente = Mensaje(
        conversacion_id=conv.id,
        rol=RolMensaje.asistente,
        contenido=respuesta,
        referencias={"fragmentos": referencias_json, "leccion": leccion},
    )
    db.add(msg_usuario)
    db.add(msg_asistente)

    # Actualizar título si es el primer mensaje
    if not history:
        conv.titulo = pregunta[:100]

    conv.fecha_ultimo_mensaje = datetime.now(timezone.utc)

    # Gamificación: enviar un mensaje al tutor cuenta como "usar la app hoy" para la racha.
    await actualizar_racha(estudiante.id, db)

    await db.commit()

    return {
        "conversacion_id": conv.id,
        "respuesta": respuesta,
        "referencias": referencias_json,
        "leccion": leccion,
    }


async def listar_conversaciones(db: AsyncSession, estudiante_id: int) -> list:
    result = await db.execute(
        select(Conversacion)
        .where(Conversacion.estudiante_id == estudiante_id)
        .order_by(Conversacion.fecha_ultimo_mensaje.desc())
    )
    return list(result.scalars().all())


async def obtener_conversacion_completa(
    db: AsyncSession, conversacion_id: int, estudiante_id: int
) -> dict | None:
    result = await db.execute(
        select(Conversacion)
        .options(selectinload(Conversacion.mensajes))
        .where(
            Conversacion.id == conversacion_id,
            Conversacion.estudiante_id == estudiante_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        return None
    # Mensajes guardados antes de que las referencias llevaran el título del libro.
    refs = [r for m in conv.mensajes for r in ((m.referencias or {}).get("fragmentos") or [])]
    titulos = await _titulos_libros(db, {r.get("libro_id") for r in refs if not r.get("libro_titulo")})
    for r in refs:
        r.setdefault("libro_titulo", titulos.get(r.get("libro_id")))
    return {
        "id": conv.id,
        "titulo": conv.titulo,
        "asignatura_id": conv.asignatura_id,
        "mensajes": [
            {
                "id": m.id,
                "rol": m.rol.value,
                "contenido": m.contenido,
                "referencias": m.referencias,
                "fecha_creacion": m.fecha_creacion,
            }
            for m in conv.mensajes
        ],
    }
