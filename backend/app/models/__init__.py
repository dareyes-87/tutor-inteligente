"""Importa todos los modelos para que SQLAlchemy y Alembic los detecten."""
from app.models.grado import Grado
from app.models.asignatura import Asignatura
from app.models.usuario import Usuario, RolUsuario
from app.models.libro import LibroTexto, EstadoIndexacion
from app.models.fragmento import Fragmento
from app.models.conversacion import Conversacion
from app.models.mensaje import Mensaje, RolMensaje
from app.models.actividad import Actividad, ResultadoActividad, TipoActividad
from app.models.perfil_comprension import PerfilComprension
from app.models.leccion import Leccion
from app.models.progreso_leccion import ProgresoLeccion, EstadoLeccion

__all__ = [
    "Grado", "Asignatura", "Usuario", "RolUsuario",
    "LibroTexto", "EstadoIndexacion", "Fragmento",
    "Conversacion", "Mensaje", "RolMensaje",
    "Actividad", "ResultadoActividad", "TipoActividad",
    "PerfilComprension",
    "Leccion", "ProgresoLeccion", "EstadoLeccion",
]
