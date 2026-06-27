"""Schemas del panel docente."""
from datetime import date, datetime

from pydantic import BaseModel

from app.modules.lecciones.schemas import RutaAprendizaje


class LibroDocente(BaseModel):
    id: int
    titulo: str
    asignatura: str
    grado: str
    estado: str  # procesando / completado / error / pendiente
    total_fragmentos: int
    total_lecciones: int
    fecha_creacion: datetime


class EstudianteResumen(BaseModel):
    id: int
    nombre: str
    apellido: str
    grado: str | None
    racha_actual: int
    puntos_totales: int
    lecciones_completadas: int
    ultima_actividad: date | None


class PerfilTemaDocente(BaseModel):
    asignatura: str
    tema: str
    puntaje_promedio: float
    nivel: str
    total_actividades: int


class EstudianteDetalle(BaseModel):
    id: int
    nombre: str
    apellido: str
    grado: str | None
    racha_actual: int
    puntos_totales: int
    ruta: RutaAprendizaje | None
    perfil: list[PerfilTemaDocente]


class TemaPreguntado(BaseModel):
    tema: str
    total: int
    ejemplo: str | None = None  # pregunta reciente de ejemplo (si existe)


class EstadisticasDocente(BaseModel):
    total_estudiantes: int
    total_libros: int
    total_lecciones: int
    promedio_progreso: float  # 0-100
    temas_mas_preguntados: list[TemaPreguntado]
