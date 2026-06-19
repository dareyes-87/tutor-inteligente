"""Modelos: Actividad generada y resultado del estudiante."""
import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class TipoActividad(str, enum.Enum):
    opcion_multiple = "opcion_multiple"
    verdadero_falso = "verdadero_falso"
    completar = "completar"
    ordenar = "ordenar"
    respuesta_corta = "respuesta_corta"


class Actividad(Base):
    __tablename__ = "actividad"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asignatura_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("asignatura.id"), nullable=False
    )
    grado_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("grado.id"), nullable=False
    )
    tipo: Mapped[TipoActividad] = mapped_column(
        Enum(TipoActividad, name="tipo_actividad"), nullable=False
    )
    tema: Mapped[str | None] = mapped_column(Text, nullable=True)
    contenido: Mapped[dict] = mapped_column(JSONB, nullable=False)
    respuesta_correcta: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    resultados: Mapped[list["ResultadoActividad"]] = relationship(
        back_populates="actividad", cascade="all, delete-orphan"
    )


class ResultadoActividad(Base):
    __tablename__ = "resultado_actividad"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actividad_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("actividad.id", ondelete="CASCADE"), nullable=False
    )
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuario.id"), nullable=False
    )
    respuesta_estudiante: Mapped[dict] = mapped_column(JSONB, nullable=False)
    puntaje: Mapped[float] = mapped_column(Float, nullable=False)
    retroalimentacion: Mapped[str] = mapped_column(Text, nullable=False)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    actividad: Mapped["Actividad"] = relationship(back_populates="resultados")
    estudiante: Mapped["Usuario"] = relationship()
