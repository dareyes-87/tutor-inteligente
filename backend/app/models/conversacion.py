"""Modelo: Conversación entre un estudiante y el tutor."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Conversacion(Base):
    __tablename__ = "conversacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuario.id"), nullable=False, index=True
    )
    asignatura_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("asignatura.id"), nullable=False
    )
    titulo: Mapped[str] = mapped_column(String(300), default="Nueva conversación")
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    fecha_ultimo_mensaje: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relaciones
    estudiante: Mapped["Usuario"] = relationship()
    asignatura: Mapped["Asignatura"] = relationship()
    mensajes: Mapped[list["Mensaje"]] = relationship(
        back_populates="conversacion", cascade="all, delete-orphan",
        order_by="Mensaje.fecha_creacion",
    )
