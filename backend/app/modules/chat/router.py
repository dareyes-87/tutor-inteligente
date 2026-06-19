"""Endpoints del chat del tutor inteligente."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.usuario import RolUsuario
from app.modules.auth.dependencies import get_current_user, require_role
from app.modules.chat.schemas import (
    ChatRequest, ChatResponse, ConversacionResponse,
)
from app.modules.chat.service import (
    procesar_pregunta, listar_conversaciones, obtener_conversacion_completa,
)

router = APIRouter(prefix="/chat", tags=["Chat del Tutor"])


@router.post("/preguntar", response_model=ChatResponse)
async def preguntar(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    El estudiante hace una pregunta al tutor.
    El sistema busca contexto en los libros (RAG), construye un prompt
    pedagógico y genera la respuesta con el LLM.
    """
    resultado = await procesar_pregunta(
        db=db,
        pregunta=body.pregunta,
        conversacion_id=body.conversacion_id,
        asignatura_id=body.asignatura_id,
        estudiante=current_user,
    )
    return resultado


@router.get("/conversaciones", response_model=list[ConversacionResponse])
async def mis_conversaciones(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista las conversaciones del estudiante autenticado."""
    return await listar_conversaciones(db, current_user.id)


@router.get("/conversaciones/{conversacion_id}")
async def ver_conversacion(
    conversacion_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Obtiene una conversación completa con todos sus mensajes."""
    result = await obtener_conversacion_completa(db, conversacion_id, current_user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return result
