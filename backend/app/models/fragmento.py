"""Modelo: Fragmento de texto extraído de un libro (un chunk indexado)."""
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Fragmento(Base):
    __tablename__ = "fragmento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    libro_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("libro_texto.id", ondelete="CASCADE"), nullable=False
    )
    contenido_texto: Mapped[str] = mapped_column(Text, nullable=False)
    numero_pagina: Mapped[int] = mapped_column(Integer, nullable=False)
    tema: Mapped[str | None] = mapped_column(String(300), nullable=True)
    chunk_id_vectordb: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    confianza_ocr: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relación
    libro: Mapped["LibroTexto"] = relationship(back_populates="fragmentos")
