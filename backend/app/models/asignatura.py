"""Modelo: Asignatura (ej: Matemáticas, Ciencias Naturales)."""
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Asignatura(Base):
    __tablename__ = "asignatura"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relaciones
    libros: Mapped[list["LibroTexto"]] = relationship(back_populates="asignatura")
