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
from app.modules.rag.search import search_fragments
from app.modules.chat.prompts import SYSTEM_PROMPT, build_context_prompt, build_messages

logger = logging.getLogger(__name__)


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

    # 3. Construir prompt
    context = build_context_prompt(fragments)
    history = await obtener_historial(db, conv.id)
    messages = build_messages(SYSTEM_PROMPT, context, history, pregunta)

    # 4. Llamar al LLM
    logger.info(f"[Chat] Enviando pregunta al LLM con {len(fragments)} fragmentos de contexto")
    respuesta = llm_client.chat(messages)

    # 5. Guardar mensajes
    referencias_json = [
        {"page_num": f.get("page_num"), "libro_id": f.get("libro_id"), "distance": f.get("distance")}
        for f in fragments
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
