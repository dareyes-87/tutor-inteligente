"""Esquemas Pydantic para el módulo de chat."""
from datetime import datetime
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Lo que el estudiante envía para hacer una pregunta."""
    pregunta: str = Field(min_length=1, max_length=2000)
    conversacion_id: int | None = None  # None = crear conversación nueva
    asignatura_id: int = Field(description="ID de la asignatura sobre la que pregunta")


class ReferenciaFragment(BaseModel):
    page_num: int | None
    libro_id: int | None
    distance: float | None


class ChatResponse(BaseModel):
    """La respuesta del tutor."""
    conversacion_id: int
    respuesta: str
    referencias: list[ReferenciaFragment]


class ConversacionResponse(BaseModel):
    id: int
    titulo: str
    asignatura_id: int
    fecha_creacion: datetime
    fecha_ultimo_mensaje: datetime

    model_config = {"from_attributes": True}


class MensajeResponse(BaseModel):
    id: int
    rol: str
    contenido: str
    referencias: dict | None
    fecha_creacion: datetime

    model_config = {"from_attributes": True}
