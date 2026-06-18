"""Modelo: Usuario del sistema (estudiante, docente, administrador)."""
import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RolUsuario(str, enum.Enum):
    estudiante = "estudiante"
    docente = "docente"
    administrador = "administrador"


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    apellido: Mapped[str] = mapped_column(String(100), nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[RolUsuario] = mapped_column(
        Enum(RolUsuario, name="rol_usuario"),
        nullable=False,
        default=RolUsuario.estudiante,
    )
    grado_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("grado.id"), nullable=True
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relaciones
    grado: Mapped["Grado | None"] = relationship(back_populates="usuarios")
    libros_subidos: Mapped[list["LibroTexto"]] = relationship(back_populates="subido_por_usuario")
