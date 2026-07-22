"""Lógica de negocio del chat: orquesta RAG + LLM + historial."""
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.llm.client import grado_usa_finetuned, llm_client, modelo_para_asignatura
from app.models.conversacion import Conversacion
from app.models.mensaje import Mensaje, RolMensaje
from app.models.asignatura import Asignatura
from app.models.fragmento import Fragmento
from app.models.usuario import Usuario
from app.models.grado import Grado
from app.modules.rag.search import (
    es_ejercicio_del_libro,
    is_context_relevant,
    search_fragments,
)
from app.modules.chat.prompts import build_context_prompt, build_messages
from app.modules.lecciones.service import actualizar_racha

logger = logging.getLogger(__name__)

# Respuesta fija (determinística) cuando la pregunta cae fuera de los libros.
# No depende de que el LLM obedezca: se devuelve sin llamar al modelo.
RESPUESTA_FUERA_DE_CONTEXTO = (
    "No encuentro información sobre eso en tus libros de clase. "
    "¿Quieres preguntarme sobre los temas que estamos viendo?"
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


def _paginas_citadas(respuesta: str) -> list[int]:
    """Extrae los números de página citados en el texto, formato '(página X)'."""
    return [int(n) for n in re.findall(r"p[aá]gina\s+(\d+)", respuesta, re.IGNORECASE)]


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
    """Obtiene los mensajes previos de una conversación."""
    result = await db.execute(
        select(Mensaje)
        .where(Mensaje.conversacion_id == conversacion_id)
        .order_by(Mensaje.fecha_creacion)
    )
    mensajes = result.scalars().all()
    return [{"rol": m.rol.value, "contenido": m.contenido} for m in mensajes]


async def procesar_pregunta(
    db: AsyncSession,
    pregunta: str,
    conversacion_id: int | None,
    asignatura_id: int,
    estudiante: Usuario,
    debug: bool = False,
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
    pagina_solicitada = _detectar_pagina(pregunta)
    consulta_por_pagina = False
    if pagina_solicitada is not None:
        fragments = search_fragments(
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
            fragments = search_fragments(
                query=pregunta,
                asignatura=asignatura_nombre,
                grado=grado_nombre,
            )
    else:
        fragments = search_fragments(
            query=pregunta,
            asignatura=asignatura_nombre,
            grado=grado_nombre,
        )

    # Filtro de ejercicios SOLO en búsqueda semántica (sin página específica):
    # en el chat conceptual no queremos que un ejercicio del libro ("Mesa lista",
    # "Ahora es tu turno"…) se cuele como si fuera teoría. Con página específica
    # NO se filtra: el estudiante pidió esa página tal cual, sea teoría o
    # ejercicio. Si el filtro dejara la lista vacía, se conservan los originales
    # para no dejar al estudiante sin respuesta.
    if pagina_solicitada is None:
        filtrados = [f for f in fragments if not es_ejercicio_del_libro(f["text"])]
        if filtrados:
            fragments = filtrados

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
        if grado_usa_finetuned(estudiante.grado_id):
            try:
                respuesta = llm_client.chat_finetuned(messages)
                logger.info(f"[Chat] Respuesta del fine-tuned (grado_id={estudiante.grado_id})")
            except Exception as e:  # noqa: BLE001 — cualquier fallo del endpoint de Modal degrada a Together
                logger.warning(f"[Chat] Fine-tuned no disponible, fallback a base: {e}")
                respuesta = llm_client.chat(messages, model=modelo_para_asignatura(asignatura_nombre))
        else:
            # Matemáticas usa el 70B (más confiable en aritmética); el resto, el Qwen 7B.
            respuesta = llm_client.chat(messages, model=modelo_para_asignatura(asignatura_nombre))
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
    # Capa 3 del grounding: si el modelo NO rechazó pero citó una página que no
    # está entre los fragmentos recuperados, es señal de alucinación de cita.
    # OPCIÓN A (actual, mínimo riesgo): limpiar referencias + log de auditoría;
    # la respuesta sí se muestra al estudiante, pero sin páginas que no la
    # respaldan. Para cambiar a la OPCIÓN B (tratar la cita inválida como
    # alucinación y reemplazar la respuesta por RESPUESTA_FUERA_DE_CONTEXTO),
    # basta con reemplazar el cuerpo del `elif` por esas dos líneas.
    if _es_rechazo(respuesta):
        fragments_referencia = []
    elif not _citas_validas(respuesta, fragments):
        logger.warning(
            "[Chat] Grounding: el modelo citó una página que NO está en los "
            "fragmentos recuperados. Pregunta=%r, respuesta=%r, "
            "paginas_citadas=%r, paginas_disponibles=%r",
            pregunta,
            respuesta,
            _paginas_citadas(respuesta),
            {f.get("page_num") for f in fragments},
        )
        fragments_referencia = []
        # OPCIÓN B (más estricta, desactivada): descartar también el contenido.
        # respuesta = RESPUESTA_FUERA_DE_CONTEXTO

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

    resultado = {
        "conversacion_id": conv.id,
        "respuesta": respuesta,
        "referencias": referencias_json,
    }
    # Modo debug (RAGAS): adjunta los fragmentos crudos que recuperó el RAG
    # (con su `text` completo), no los que sobrevivieron al grounding. No afecta
    # el flujo normal de /chat/preguntar (debug=False por defecto).
    if debug:
        resultado["contextos_recuperados"] = [
            {
                "text": f.get("text"),
                "page_num": f.get("page_num"),
                "libro_id": f.get("libro_id"),
                "chunk_id": f.get("chunk_id"),
                "distance": f.get("distance"),
            }
            for f in fragments
        ]
    return resultado


async def listar_fragmentos_libro(db: AsyncSession, libro_id: int) -> list[dict]:
    """Todos los fragmentos indexados de un libro, ordenados por página.

    Temporal: alimenta la extracción de datos para la evaluación RAGAS de la
    tesis. Solo accesible por admin/docente desde el router.
    """
    result = await db.execute(
        select(Fragmento)
        .where(Fragmento.libro_id == libro_id)
        .order_by(Fragmento.numero_pagina)
    )
    return [
        {
            "contenido_texto": f.contenido_texto,
            "numero_pagina": f.numero_pagina,
            "tema": f.tema,
        }
        for f in result.scalars().all()
    ]


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
