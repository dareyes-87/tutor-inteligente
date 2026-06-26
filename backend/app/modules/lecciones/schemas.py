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
    # Sistema de 3 niveles
    nivel_actual: int = 1
    nivel_completado: int = 0
    tiene_corona: bool = False


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
    # IDs de los fragmentos del libro usados para generar la lección. El frontend
    # los reenvía a /actividades/generar para que la práctica use el MISMO contenido
    # que el tutor explicó (no una búsqueda semántica distinta).
    fragment_ids: list[int] = []
    # Nivel de esta micro-lección (1, 2 o 3) y si es el último.
    nivel_actual: int = 1
    es_ultimo_nivel: bool = False


# ----------------------- Acciones del estudiante -----------------------

class CompletarActividadRequest(BaseModel):
    puntaje: int = Field(ge=0, le=100, description="Puntaje obtenido (0-100)")
    # Campos del sistema de niveles (opcionales para compatibilidad). Si vienen
    # ambos, se evalúa el nivel completo; si no, se usa el comportamiento viejo.
    nivel: int | None = Field(None, ge=1, le=3, description="Nivel practicado (1-3)")
    actividades_aprobadas: int | None = Field(
        None, ge=0, description="Cuántas de las 5 actividades superaron el umbral (>=70)"
    )


class CompletarNivelResponse(BaseModel):
    nivel_completado: int
    nivel_actual: int
    aprobado: bool
    mensaje_feedback: str


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
