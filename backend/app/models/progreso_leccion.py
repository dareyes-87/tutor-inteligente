"""Modelo: Progreso de un estudiante en una lección de la ruta de aprendizaje."""
import enum
from datetime import datetime

from sqlalchemy import (
    DateTime, Enum, Float, ForeignKey, Integer, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EstadoLeccion(str, enum.Enum):
    bloqueada = "bloqueada"
    disponible = "disponible"
    en_progreso = "en_progreso"
    completada = "completada"


class ProgresoLeccion(Base):
    __tablename__ = "progreso_leccion"
    __table_args__ = (
        UniqueConstraint(
            "estudiante_id", "leccion_id", name="uq_progreso_estudiante_leccion"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuario.id"), nullable=False, index=True
    )
    leccion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leccion.id", ondelete="CASCADE"), nullable=False
    )
    estado: Mapped[EstadoLeccion] = mapped_column(
        Enum(EstadoLeccion, name="estado_leccion"),
        nullable=False,
        default=EstadoLeccion.bloqueada,
    )
    puntaje_promedio: Mapped[float] = mapped_column(Float, default=0.0)
    actividades_completadas: Mapped[int] = mapped_column(Integer, default=0)
    # Mínimo de actividades para considerar la lección completada.
    actividades_requeridas: Mapped[int] = mapped_column(Integer, default=3)
    fecha_inicio: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fecha_completada: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relaciones
    estudiante: Mapped["Usuario"] = relationship(back_populates="progresos_lecciones")
    leccion: Mapped["Leccion"] = relationship(back_populates="progresos")
