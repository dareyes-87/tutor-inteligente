"""Modelo: Lección de la ruta de aprendizaje (generada desde un libro)."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Leccion(Base):
    __tablename__ = "leccion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    libro_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("libro_texto.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Orden en la ruta (1, 2, 3...): determina la secuencia pedagógica.
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    # Keyword para filtrar/buscar el contenido de la lección en ChromaDB.
    tema_clave: Mapped[str] = mapped_column(String(200), nullable=False)
    # Rango de páginas del libro, ej: "10-15".
    paginas: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relaciones
    libro: Mapped["LibroTexto"] = relationship(back_populates="lecciones")
    progresos: Mapped[list["ProgresoLeccion"]] = relationship(
        back_populates="leccion", cascade="all, delete-orphan"
    )
