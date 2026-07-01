"""Lógica de negocio del chat: orquesta RAG + LLM + historial."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.llm.client import llm_client
from app.models.conversacion import Conversacion
from app.models.mensaje import Mensaje, RolMensaje
from app.models.asignatura import Asignatura
from app.models.usuario import Usuario
from app.models.grado import Grado
from app.modules.rag.search import search_fragments, is_context_relevant
from app.modules.chat.prompts import build_context_prompt, build_messages

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
    fragments = search_fragments(
        query=pregunta,
        asignatura=asignatura_nombre,
        grado=grado_nombre,
    )

    # Historial (lo usa el prompt del LLM y el título del primer mensaje).
    history = await obtener_historial(db, conv.id)

    # 3-4. Grounding determinístico: si el contexto NO es relevante, no se
    # llama al LLM y se devuelve un mensaje fijo de rechazo. Así la garantía
    # no depende de que el modelo obedezca el prompt.
    if is_context_relevant(fragments):
        context = build_context_prompt(fragments)
        messages = build_messages(
            context, history, pregunta, grado_nombre, asignatura_nombre
        )
        logger.info(
            f"[Chat] System prompt adaptado a grado='{grado_nombre}', "
            f"asignatura='{asignatura_nombre}'"
        )
        logger.info(
            f"[Chat] Contexto relevante: enviando al LLM con {len(fragments)} fragmentos"
        )
        respuesta = llm_client.chat(messages)
        fragments_referencia = fragments
    else:
        logger.info(
            "[Chat] Contexto NO relevante: respuesta determinística de rechazo (sin LLM)"
        )
        respuesta = RESPUESTA_FUERA_DE_CONTEXTO
        fragments_referencia = []

    # Si el LLM rechazó la pregunta (aunque el contexto pasara el umbral), no
    # mostrar referencias: las páginas recuperadas no respaldan esa respuesta.
    if _es_rechazo(respuesta):
        fragments_referencia = []

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
