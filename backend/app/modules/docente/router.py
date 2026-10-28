"""Endpoints del panel docente (solo lectura, rol docente/administrador)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.usuario import RolUsuario, Usuario
from app.modules.auth.dependencies import require_role
from app.modules.docente import service
from app.modules.docente.schemas import (
    AsignaturaOpcion,
    DiagnosticoResponse,
    EstadisticasDocente,
    EstudianteDetalle,
    EstudianteResumen,
    LibroDocente,
    MiGradoResponse,
)

router = APIRouter(prefix="/docente", tags=["Panel docente"])

_docente = require_role(RolUsuario.docente, RolUsuario.administrador)


@router.get("/libros", response_model=list[LibroDocente])
async def get_libros(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_docente),
):
    return await service.listar_libros(db, current_user.grado_id)


@router.get("/asignaturas", response_model=list[AsignaturaOpcion])
async def get_asignaturas(db: AsyncSession = Depends(get_db), _=Depends(_docente)):
    """Asignaturas disponibles para el formulario de subida de libros."""
    return await service.listar_asignaturas(db)


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


@router.get("/diagnostico", response_model=DiagnosticoResponse)
async def get_diagnostico(
    asignatura_id: int | None = Query(None),
    libro_id: int | None = Query(None, description="Libro; si no viene, el más reciente de la asignatura"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_docente),
):
    """Matriz estudiantes × lecciones con el nivel de comprensión (domina ≥80 /
    en_proceso ≥50 / refuerzo / sin_datos). Docente: solo su grado; admin: todo."""
    grado_id = None if current_user.rol == RolUsuario.administrador else current_user.grado_id
    if current_user.rol == RolUsuario.docente and grado_id is None:
        # Sin grado asignado no hay alcance: no se le muestra la matriz de todos.
        raise HTTPException(status_code=404, detail="No tienes un grado asignado")
    resultado = await service.diagnostico(db, grado_id, asignatura_id, libro_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail="No hay un libro con esos filtros para tu grado")
    return resultado
