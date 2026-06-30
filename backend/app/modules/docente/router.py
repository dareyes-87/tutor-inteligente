"""Endpoints del panel docente (solo lectura, rol docente/administrador)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.usuario import RolUsuario, Usuario
from app.modules.auth.dependencies import require_role
from app.modules.docente import service
from app.modules.docente.schemas import (
    EstadisticasDocente,
    EstudianteDetalle,
    EstudianteResumen,
    LibroDocente,
    MiGradoResponse,
)

router = APIRouter(prefix="/docente", tags=["Panel docente"])

_docente = require_role(RolUsuario.docente, RolUsuario.administrador)


@router.get("/libros", response_model=list[LibroDocente])
async def get_libros(db: AsyncSession = Depends(get_db), _=Depends(_docente)):
    return await service.listar_libros(db)


@router.get("/mi-grado", response_model=MiGradoResponse)
async def get_mi_grado(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_docente),
):
    """Grado del docente autenticado (para el sidebar)."""
    return await service.mi_grado(db, current_user.grado_id)


@router.get("/estudiantes", response_model=list[EstudianteResumen])
async def get_estudiantes(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_docente),
):
    return await service.listar_estudiantes(db, current_user.grado_id)


@router.get("/estudiantes/{estudiante_id}/detalle", response_model=EstudianteDetalle)
async def get_detalle_estudiante(
    estudiante_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(_docente),
):
    detalle = await service.detalle_estudiante(db, estudiante_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    return detalle


@router.get("/estadisticas", response_model=EstadisticasDocente)
async def get_estadisticas(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_docente),
):
    return await service.estadisticas(db, current_user.grado_id)
