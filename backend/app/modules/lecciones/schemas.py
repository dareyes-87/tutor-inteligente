"""Schemas Pydantic para la salida del LLM al generar lecciones."""
from pydantic import BaseModel


class LeccionGenerada(BaseModel):
    """Una lección tal como la propone el LLM."""
    nombre: str
    descripcion: str | None = None
    tema_clave: str
    paginas: str | None = None


class LeccionesGeneradas(BaseModel):
    """Estructura completa esperada del LLM: una lista de lecciones."""
    lecciones: list[LeccionGenerada]
