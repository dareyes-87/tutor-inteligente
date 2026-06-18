"""
Importa todos los modelos para que SQLAlchemy y Alembic los detecten.
Cada vez que crees un modelo nuevo, agrégalo aquí.
"""
from app.models.grado import Grado
from app.models.asignatura import Asignatura
from app.models.usuario import Usuario, RolUsuario
from app.models.libro import LibroTexto, EstadoIndexacion
from app.models.fragmento import Fragmento

__all__ = [
    "Grado",
    "Asignatura",
    "Usuario",
    "RolUsuario",
    "LibroTexto",
    "EstadoIndexacion",
    "Fragmento",
]
