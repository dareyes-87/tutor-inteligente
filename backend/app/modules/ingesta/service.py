"""Lógica de negocio de ingesta: subida de libros y consulta de estado."""
import os
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.libro import LibroTexto
from app.models.fragmento import Fragmento


async def guardar_libro(
    db: AsyncSession,
    titulo: str,
    asignatura_id: int,
    grado_id: int,
    pdf_content: bytes,
    filename: str,
    subido_por: int,
) -> LibroTexto:
    """Guarda el PDF en disco y crea el registro en la BD."""
    # Nombre seguro con UUID (evita colisiones y caracteres raros)
    ext = os.path.splitext(filename)[1] or ".pdf"
    safe_name = f"{uuid.uuid4().hex}{ext}"
    pdf_path = os.path.join(settings.BOOKS_DIR, safe_name)

    # Guardar archivo
    os.makedirs(settings.BOOKS_DIR, exist_ok=True)
    with open(pdf_path, "wb") as f:
        f.write(pdf_content)

    # Crear registro
    libro = LibroTexto(
        titulo=titulo,
        asignatura_id=asignatura_id,
        grado_id=grado_id,
        archivo_pdf_path=pdf_path,
        subido_por=subido_por,
    )
    db.add(libro)
    await db.commit()
    await db.refresh(libro)
    return libro


async def obtener_estado_libro(db: AsyncSession, libro_id: int) -> dict | None:
    """Obtiene el estado de un libro con el conteo de fragmentos."""
    result = await db.execute(
        select(LibroTexto).where(LibroTexto.id == libro_id)
    )
    libro = result.scalar_one_or_none()
    if libro is None:
        return None

    # Contar fragmentos
    count_result = await db.execute(
        select(func.count(Fragmento.id)).where(Fragmento.libro_id == libro_id)
    )
    total_fragmentos = count_result.scalar() or 0

    return {
        "id": libro.id,
        "titulo": libro.titulo,
        "estado_indexacion": libro.estado_indexacion,
        "total_paginas": libro.total_paginas,
        "paginas_procesadas": libro.paginas_procesadas,
        "confianza_ocr_promedio": libro.confianza_ocr_promedio,
        "error_detalle": libro.error_detalle,
        "total_fragmentos": total_fragmentos,
        "fecha_subida": libro.fecha_subida,
    }


async def listar_libros(db: AsyncSession) -> list[LibroTexto]:
    result = await db.execute(select(LibroTexto).order_by(LibroTexto.fecha_subida.desc()))
    return list(result.scalars().all())
