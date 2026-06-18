"""Modelo: Grado escolar (ej: 1ro Primaria, 2do Básico)."""
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Grado(Base):
    __tablename__ = "grado"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    nivel: Mapped[str] = mapped_column(String(50), nullable=False)  # "primaria", "basico", "diversificado"

    # Relaciones
    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="grado")
    libros: Mapped[list["LibroTexto"]] = relationship(back_populates="grado")
