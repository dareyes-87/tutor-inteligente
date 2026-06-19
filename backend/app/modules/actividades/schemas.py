"""Esquemas para el módulo de actividades."""
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.actividad import TipoActividad


class GenerarActividadRequest(BaseModel):
    asignatura_id: int
    tipo: TipoActividad
    tema: str | None = Field(None, description="Tema específico (opcional, si no se da, se elige del contexto)")


class ResponderActividadRequest(BaseModel):
    actividad_id: int
    respuesta: dict = Field(description="La respuesta del estudiante")


class ActividadResponse(BaseModel):
    id: int
    tipo: TipoActividad
    tema: str | None
    contenido: dict  # La pregunta/ejercicio para mostrar al estudiante
    fecha_creacion: datetime

    model_config = {"from_attributes": True}


class ResultadoResponse(BaseModel):
    actividad_id: int
    puntaje: float
    retroalimentacion: str
    respuesta_correcta: dict


class PerfilResponse(BaseModel):
    asignatura: str
    tema: str
    puntaje_promedio: float
    nivel: str  # "domina", "en_proceso", "refuerzo"
    total_actividades: int
