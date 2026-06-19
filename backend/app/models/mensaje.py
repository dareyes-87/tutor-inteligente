"""Modelo: Mensaje individual dentro de una conversación."""
import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class RolMensaje(str, enum.Enum):
    usuario = "usuario"
    asistente = "asistente"


class Mensaje(Base):
    __tablename__ = "mensaje"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversacion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversacion.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    rol: Mapped[RolMensaje] = mapped_column(
        Enum(RolMensaje, name="rol_mensaje"), nullable=False
    )
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    referencias: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relación
    conversacion: Mapped["Conversacion"] = relationship(back_populates="mensajes")
