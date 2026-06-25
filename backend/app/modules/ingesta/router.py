"""Endpoints de ingesta de libros."""
import asyncio
import magic
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.usuario import RolUsuario
from app.modules.auth.dependencies import require_role
from app.modules.ingesta.schemas import LibroSubidoResponse, LibroEstadoResponse
from app.modules.ingesta.service import guardar_libro, obtener_estado_libro, listar_libros
from app.workers.ingesta_worker import procesar_libro

router = APIRouter(prefix="/ingesta", tags=["Ingesta de libros"])

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


@router.post(
    "/libros",
    response_model=LibroSubidoResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def subir_libro(
    titulo: str = Form(...),
    asignatura_id: int = Form(...),
    grado_id: int = Form(...),
    archivo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(RolUsuario.docente, RolUsuario.administrador)),
):
    """
    Sube un libro PDF para indexación.
    Solo docentes y administradores pueden subir libros.
    El procesamiento (OCR + embeddings + indexado) corre en segundo plano.
    Responde de inmediato con HTTP 202 (Accepted).
    """
    # Validar que es un PDF (por contenido real, no solo extensión)
    content = await archivo.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El archivo excede el tamaño máximo de 500 MB",
        )

    mime = magic.from_buffer(content[:2048], mime=True)
    if mime != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Solo se aceptan archivos PDF. El archivo subido es: {mime}",
        )

    # Guardar en disco y BD
    libro = await guardar_libro(
        db=db,
        titulo=titulo,
        asignatura_id=asignatura_id,
        grado_id=grado_id,
        pdf_content=content,
        filename=archivo.filename or "libro.pdf",
        subido_por=current_user.id,
    )

    # Lanzar procesamiento en background (NO bloquea la respuesta)
    asyncio.create_task(procesar_libro(libro.id))

    return LibroSubidoResponse(
        id=libro.id,
        titulo=libro.titulo,
        asignatura_id=libro.asignatura_id,
        grado_id=libro.grado_id,
        estado_indexacion=libro.estado_indexacion,
    )


@router.get("/libros/{libro_id}/estado", response_model=LibroEstadoResponse)
async def estado_libro(
    libro_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(
        RolUsuario.docente, RolUsuario.administrador
    )),
):
    """Consulta el estado de procesamiento de un libro."""
    estado = await obtener_estado_libro(db, libro_id)
    if estado is None:
        raise HTTPException(status_code=404, detail="Libro no encontrado")
    return estado


@router.get("/libros")
async def listar_todos_libros(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(
        RolUsuario.docente, RolUsuario.administrador
    )),
):
    """Lista todos los libros subidos."""
    libros = await listar_libros(db)
    return [
        {
            "id": l.id,
            "titulo": l.titulo,
            "estado_indexacion": l.estado_indexacion.value,
            "confianza_ocr_promedio": l.confianza_ocr_promedio,
            "fecha_subida": l.fecha_subida.isoformat(),
        }
        for l in libros
    ]
