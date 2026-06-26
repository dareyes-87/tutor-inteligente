"""
Endpoints de la ruta de aprendizaje y la gamificación (rachas + ranking).

La gamificación vive en este mismo router porque está integrada con las
lecciones. Todos los endpoints son para estudiantes autenticados.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.usuario import RolUsuario, Usuario
from app.modules.auth.dependencies import require_role
from app.modules.lecciones import service
from app.modules.lecciones.schemas import (
    CompletarActividadRequest,
    CompletarNivelResponse,
    LeccionEnRuta,
    MicroLeccionResponse,
    MiLibroResponse,
    RachaResponse,
    RankingResponse,
    RutaAprendizaje,
)

router = APIRouter(tags=["Lecciones y Gamificación"])

# Dependencia: solo estudiantes autenticados.
_estudiante = require_role(RolUsuario.estudiante)


@router.get("/lecciones/mi-libro", response_model=MiLibroResponse)
async def get_mi_libro(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_estudiante),
):
    """Libro activo del estudiante (resuelto por su grado). 404 si no hay."""
    return await service.obtener_mi_libro(current_user, db)


@router.get("/lecciones/ruta", response_model=RutaAprendizaje)
async def get_ruta(
    libro_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_estudiante),
):
    """Ruta de aprendizaje del libro con el progreso del estudiante."""
    return await service.obtener_ruta(current_user.id, libro_id, db)


@router.get("/lecciones/{leccion_id}/micro-leccion", response_model=MicroLeccionResponse)
async def get_micro_leccion(
    leccion_id: int,
    nivel: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_estudiante),
):
    """Micro-lección guiada (tarjetas educativas) generada on-demand para un nivel (1-3)."""
    return await service.generar_micro_leccion(leccion_id, db, nivel=nivel)


@router.post("/lecciones/{leccion_id}/iniciar", response_model=LeccionEnRuta)
async def post_iniciar(
    leccion_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_estudiante),
):
    """Marca una lección disponible como en progreso."""
    return await service.iniciar_leccion(current_user.id, leccion_id, db)


@router.post(
    "/lecciones/{leccion_id}/completar-actividad",
    response_model=LeccionEnRuta | CompletarNivelResponse,
)
async def post_completar_actividad(
    leccion_id: int,
    body: CompletarActividadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_estudiante),
):
    """Registra el resultado de práctica de una lección.

    - Si vienen `nivel` y `actividades_aprobadas` → evalúa el NIVEL (sistema de
      3 niveles) y devuelve CompletarNivelResponse.
    - Si no → comportamiento anterior por actividad (devuelve LeccionEnRuta).
    """
    if body.nivel is not None and body.actividades_aprobadas is not None:
        return await service.completar_nivel(
            current_user.id,
            leccion_id,
            body.nivel,
            body.actividades_aprobadas,
            body.puntaje,
            db,
        )
    return await service.completar_actividad_leccion(
        current_user.id, leccion_id, body.puntaje, db
    )


@router.get("/gamificacion/racha", response_model=RachaResponse)
async def get_racha(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_estudiante),
):
    """Racha actual, mejor racha y si ya hizo actividad hoy."""
    return await service.obtener_racha(current_user.id, db)


@router.get("/gamificacion/ranking", response_model=RankingResponse)
async def get_ranking(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(_estudiante),
):
    """Ranking de los estudiantes del grado del estudiante actual."""
    return await service.obtener_ranking(current_user.grado_id, current_user.id, db)
