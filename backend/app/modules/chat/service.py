"""Lógica de negocio del chat: orquesta RAG + LLM + historial."""
import asyncio
import logging
import re
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
from app.modules.rag.search import (
    TOP_K,
    es_ejercicio_del_libro,
    is_context_relevant,
    search_fragments,
)
from app.modules.chat.prompts import build_context_prompt, build_messages
from app.modules.rag.paginas import etiqueta_paginas
from app.modules.lecciones.service import actualizar_racha

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
) -> tuple[list[dict], bool, int | None]:
    """Paso 2 del chat (sin LLM): fragmentos para la pregunta. Devuelve
    (fragments, consulta_por_pagina, pagina_solicitada). Determinístico para un
    mismo índice; lo reusa scripts/corregir_citas_chat.py."""
    pagina_solicitada = _detectar_pagina(pregunta)
    consulta_por_pagina = False
    if pagina_solicitada is not None:
        fragments = await asyncio.to_thread(
            search_fragments,
            query=pregunta,
            asignatura=asignatura_nombre,
            grado=grado_nombre,
            page_num=pagina_solicitada,
        )
        if fragments:
            consulta_por_pagina = True
            logger.info(
                f"[Chat] Consulta por página {pagina_solicitada}: "
                f"{len(fragments)} fragmentos por filtro de page_num"
            )
        else:
            logger.info(
                f"[Chat] Página {pagina_solicitada} sin fragmentos; "
                "fallback a búsqueda semántica normal"
            )
            pagina_solicitada = None
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
    if pagina_solicitada is None:
        filtrados = [f for f in fragments if not es_ejercicio_del_libro(f["text"])]
        fragments = (filtrados or fragments)[:TOP_K]
    return fragments, consulta_por_pagina, pagina_solicitada


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
    fragments, consulta_por_pagina, pagina_solicitada = await recuperar_contexto(
        pregunta, asignatura_nombre, grado_nombre
    )

    # Historial (lo usa el prompt del LLM y el título del primer mensaje).
    history = await obtener_historial(db, conv.id)

    # 3-4. Grounding determinístico: si el contexto NO es relevante, no se
    # llama al LLM y se devuelve un mensaje fijo de rechazo. Así la garantía
    # no depende de que el modelo obedezca el prompt.
    # Una consulta por página se considera relevante aunque no haya solape
    # semántico: el estudiante pidió explícitamente esa página y ya tenemos su
    # contenido filtrado por page_num (el grounding se mantiene: el contexto
    # sigue siendo SOLO el del libro).
    if consulta_por_pagina or is_context_relevant(fragments):
        context = build_context_prompt(fragments)
        # Para consultas por página, se refuerza el prompt del LLM sin modificar
        # build_messages: se guarda la pregunta ORIGINAL en la BD, pero al LLM se
        # le envía una versión con la instrucción de explicar esa página.
        pregunta_llm = pregunta
        if consulta_por_pagina:
            pregunta_llm = (
                f"{pregunta}\n\n[El estudiante pregunta sobre el contenido de la "
                f"página {pagina_solicitada}. Explícale el contenido de esa página "
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
    if _es_rechazo(respuesta):
        fragments_referencia = []
    if not _citas_validas(respuesta, fragments):
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
            respuesta, {f.get("page_num") for f in fragments if f.get("page_num") is not None}
        )

    # Referencia de página SIEMPRE visible (determinística, no depende del LLM):
    # se arma a partir de page_num de los fragmentos que sobrevivieron al
    # grounding de arriba, no de lo que el LLM haya citado en el texto. Si el
    # pre-grounding rechazó la pregunta (fragments_referencia vacío), no hay
    # nada que anexar.
    if fragments_referencia:
        respuesta = respuesta + _referencia_paginas(fragments_referencia, asignatura_nombre)

    # 5. Guardar mensajes
    referencias_json = [
        {"page_num": f.get("page_num"), "libro_id": f.get("libro_id"), "distance": f.get("distance")}
        for f in fragments_referencia
    ]

    msg_usuario = Mensaje(
        conversacion_id=conv.id,
        rol=RolMensaje.usuario,
        contenido=pregunta,
    )
    msg_asistente = Mensaje(
        conversacion_id=conv.id,
        rol=RolMensaje.asistente,
        contenido=respuesta,
        referencias={"fragmentos": referencias_json},
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
