"""Schemas Pydantic para lecciones, ruta de aprendizaje y gamificación."""
from pydantic import BaseModel, Field


# ----------------------- Generación (LLM) -----------------------

class LeccionGenerada(BaseModel):
    """Una lección tal como la propone el LLM."""
    nombre: str
    descripcion: str | None = None
    tema_clave: str
    paginas: str | None = None


class LeccionesGeneradas(BaseModel):
    """Estructura completa esperada del LLM: una lista de lecciones."""
    lecciones: list[LeccionGenerada]


# ----------------------- Ruta de aprendizaje -----------------------

class LeccionEnRuta(BaseModel):
    id: int
    nombre: str
    descripcion: str | None
    orden: int
    tema_clave: str
    paginas: str | None
    estado: str  # bloqueada/disponible/en_progreso/completada
    puntaje_promedio: float
    actividades_completadas: int
    actividades_requeridas: int


class RutaAprendizaje(BaseModel):
    libro_id: int
    asignatura: str
    total_lecciones: int
    lecciones_completadas: int
    progreso_porcentaje: float  # 0-100
    lecciones: list[LeccionEnRuta]


# ----------------------- Libro del estudiante -----------------------

class MiLibroResponse(BaseModel):
    """Libro activo del estudiante (resuelto por su grado)."""
    libro_id: int
    titulo: str
    total_lecciones: int


# ----------------------- Micro-lección guiada -----------------------

class PreguntaRapida(BaseModel):
    texto: str
    tipo: str  # verdadero_falso | opcion_multiple
    opciones: list[str]
    respuesta_correcta: str
    explicacion: str


class TarjetaEducativa(BaseModel):
    tipo: str  # introduccion | concepto | resumen
    contenido: str
    emoji: str = "📚"
    titulo_concepto: str | None = None
    dato_curioso: str | None = None
    pregunta: PreguntaRapida | None = None


class MicroLeccionResponse(BaseModel):
    titulo: str
    tarjetas: list[TarjetaEducativa]


# ----------------------- Acciones del estudiante -----------------------

class CompletarActividadRequest(BaseModel):
    puntaje: int = Field(ge=0, le=100, description="Puntaje obtenido en la actividad (0-100)")


# ----------------------- Gamificación -----------------------

class RachaResponse(BaseModel):
    racha_actual: int
    mejor_racha: int
    activo_hoy: bool  # si ya hizo actividad hoy


class RankingEstudiante(BaseModel):
    posicion: int
    nombre: str
    apellido: str
    lecciones_completadas: int
    puntos_totales: int
    racha_actual: int


class RankingResponse(BaseModel):
    ranking: list[RankingEstudiante]
    mi_posicion: int
