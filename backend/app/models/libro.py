"""Modelo: Libro de texto (PDF subido por un docente)."""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime, Enum, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EstadoIndexacion(str, enum.Enum):
    pendiente = "pendiente"
    procesando = "procesando"
    completado = "completado"
    error = "error"


class LibroTexto(Base):
    __tablename__ = "libro_texto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    asignatura_id: Mapped[int] = mapped_column(Integer, ForeignKey("asignatura.id"), nullable=False)
    grado_id: Mapped[int] = mapped_column(Integer, ForeignKey("grado.id"), nullable=False)
    archivo_pdf_path: Mapped[str] = mapped_column(String(500), nullable=False)
    estado_indexacion: Mapped[EstadoIndexacion] = mapped_column(
        Enum(EstadoIndexacion, name="estado_indexacion"),
        default=EstadoIndexacion.pendiente,
    )
    confianza_ocr_promedio: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_paginas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paginas_procesadas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    subido_por: Mapped[int] = mapped_column(Integer, ForeignKey("usuario.id"), nullable=False)
    fecha_subida: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relaciones
    asignatura: Mapped["Asignatura"] = relationship(back_populates="libros")
    grado: Mapped["Grado"] = relationship(back_populates="libros")
    subido_por_usuario: Mapped["Usuario"] = relationship(back_populates="libros_subidos")
    fragmentos: Mapped[list["Fragmento"]] = relationship(
        back_populates="libro", cascade="all, delete-orphan"
    )
    lecciones: Mapped[list["Leccion"]] = relationship(
        back_populates="libro",
        cascade="all, delete-orphan",
        order_by="Leccion.orden",
    )
