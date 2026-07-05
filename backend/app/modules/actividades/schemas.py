"""Esquemas para el módulo de actividades."""
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.actividad import TipoActividad


class GenerarActividadRequest(BaseModel):
    asignatura_id: int
    tipo: TipoActividad
    tema: str | None = Field(None, description="Tema específico (opcional, si no se da, se elige del contexto)")
    leccion_id: int | None = Field(
        None,
        description="Lección que se acaba de estudiar (opcional). Si se da, la actividad "
        "se enfoca en el tema y las páginas de esa lección.",
    )
    fragment_ids: list[int] = Field(
        default_factory=list,
        description="IDs de los fragmentos que usó la micro-lección (opcional). Si se dan, "
        "la actividad se genera con EXACTAMENTE esos fragmentos (la teoría que el "
        "tutor explicó), en vez de una nueva búsqueda semántica.",
    )
    evitar_preguntas: list[str] = Field(
        default_factory=list,
        description="Textos de las preguntas YA generadas en esta sesión de práctica "
        "(opcional). Se pasan al LLM para que no repita la misma pregunta ni el "
        "mismo enfoque dentro de una sesión de 5 actividades.",
    )


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
