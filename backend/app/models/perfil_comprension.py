"""Modelo: Perfil de comprensión por estudiante, asignatura y tema."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PerfilComprension(Base):
    __tablename__ = "perfil_comprension"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    estudiante_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("usuario.id"), nullable=False, index=True
    )
    asignatura_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("asignatura.id"), nullable=False
    )
    tema: Mapped[str] = mapped_column(String(300), nullable=False)
    puntaje_promedio: Mapped[float] = mapped_column(Float, default=0.0)
    total_actividades: Mapped[int] = mapped_column(Integer, default=0)
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    @property
    def nivel(self) -> str:
        """domina >=80%, en_proceso 50-79%, refuerzo <50%"""
        if self.puntaje_promedio >= 80:
            return "domina"
        elif self.puntaje_promedio >= 50:
            return "en_proceso"
        return "refuerzo"
