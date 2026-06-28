"""Schemas del panel de administrador (gestión de la estructura del colegio)."""
from datetime import date, datetime

from pydantic import BaseModel, Field


# ----------------------- Docentes -----------------------

class CrearDocenteRequest(BaseModel):
    nombre: str
    apellido: str
    username: str
    password: str
    grado_id: int | None = None


class ActualizarDocenteRequest(BaseModel):
    nombre: str | None = None
    apellido: str | None = None
    grado_id: int | None = None
    activo: bool | None = None


class DocenteResumen(BaseModel):
    id: int
    nombre: str
    apellido: str
    username: str
    activo: bool
    grado_id: int | None
    grado: str | None
    libros_subidos: int


# ----------------------- Estudiantes -----------------------

class CrearEstudianteRequest(BaseModel):
    nombre: str
    apellido: str
    grado_id: int
    # Opcionales: si no se dan, se auto-generan (username = inicial+apellido,
    # password = apellido + "123").
    username: str | None = None
    password: str | None = None


class ActualizarEstudianteRequest(BaseModel):
    nombre: str | None = None
    apellido: str | None = None
    grado_id: int | None = None
    activo: bool | None = None


class EstudianteAdminResumen(BaseModel):
    id: int
    nombre: str
    apellido: str
    username: str
    grado_id: int | None
    grado: str | None
    activo: bool
    progreso: float  # % 0-100
    ultima_actividad: date | None


class EstudianteCreado(BaseModel):
    """Credenciales generadas (se muestran UNA sola vez)."""
    id: int | None = None
    nombre: str
    apellido: str
    username: str
    password_generado: str


# ----------------------- Reset de contraseña -----------------------

class ResetPasswordRequest(BaseModel):
    nueva_password: str = Field(min_length=3)


# ----------------------- Grados -----------------------

class CrearGradoRequest(BaseModel):
    nombre: str
    # Si no se da, se deriva del nombre (primaria/basico/diversificado).
    nivel: str | None = None


class ActualizarGradoRequest(BaseModel):
    nombre: str


class GradoResumen(BaseModel):
    id: int
    nombre: str
    nivel: str
    cantidad_estudiantes: int
    cantidad_docentes: int


# ----------------------- Asignaturas -----------------------

class CrearAsignaturaRequest(BaseModel):
    nombre: str


class ActualizarAsignaturaRequest(BaseModel):
    nombre: str


class AsignaturaResumen(BaseModel):
    id: int
    nombre: str
    cantidad_libros: int


# ----------------------- Promoción de año -----------------------

class PromoverGradoRequest(BaseModel):
    grado_origen_id: int
    grado_destino_id: int


class PromoverGradoResponse(BaseModel):
    estudiantes_promovidos: int


# ----------------------- Dashboard -----------------------

class LibroReciente(BaseModel):
    titulo: str
    fecha_subida: datetime
    estado: str


class DashboardAdmin(BaseModel):
    total_estudiantes: int
    total_docentes: int
    total_grados: int
    total_asignaturas: int
    total_libros: int
    total_lecciones: int
    total_fragmentos: int
    progreso_general: float
    estudiantes_activos_hoy: int
    libro_mas_reciente: LibroReciente | None
