"""Esquemas Pydantic para el módulo de ingesta."""
from datetime import datetime

from pydantic import BaseModel

from app.models.libro import EstadoIndexacion


class LibroSubidoResponse(BaseModel):
    id: int
    titulo: str
    asignatura_id: int
    grado_id: int
    estado_indexacion: EstadoIndexacion
    mensaje: str = "Libro recibido. El procesamiento ha iniciado en segundo plano."

    model_config = {"from_attributes": True}


class LibroEstadoResponse(BaseModel):
    id: int
    titulo: str
    estado_indexacion: EstadoIndexacion
    total_paginas: int | None
    paginas_procesadas: int | None
    confianza_ocr_promedio: float | None
    error_detalle: str | None
    total_fragmentos: int
    fecha_subida: datetime

    model_config = {"from_attributes": True}
