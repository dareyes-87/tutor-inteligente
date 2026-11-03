"""Endpoints del módulo de actividades."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.leccion import Leccion
from app.models.libro import LibroTexto
from app.models.usuario import RolUsuario
from app.modules.auth.dependencies import get_current_user
from app.modules.actividades.schemas import (
    GenerarActividadRequest, ResponderActividadRequest,
    ActividadResponse, ResultadoResponse, PerfilResponse,
)
from app.modules.actividades.service import (
    crear_actividad, responder_actividad, obtener_perfil_estudiante,
)

router = APIRouter(prefix="/actividades", tags=["Actividades"])


@router.post("/generar", response_model=ActividadResponse)
async def generar(
    body: GenerarActividadRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Genera una actividad nueva basada en el contenido de los libros.
    El tipo puede ser: opcion_multiple, verdadero_falso, completar, ordenar, respuesta_corta.

    Con `leccion_id` sirve también para la práctica libre / repaso de CUALQUIER lección
    del libro (incluso bloqueada en la ruta): la actividad cuenta para el perfil y el
    mapa de calor, pero no toca el progreso de la ruta (eso solo lo hace completar-actividad).
    """
    if body.leccion_id is not None and current_user.rol == RolUsuario.estudiante:
        libro = (await db.execute(
            select(LibroTexto).join(Leccion, Leccion.libro_id == LibroTexto.id)
            .where(Leccion.id == body.leccion_id)
        )).scalar_one_or_none()
        if libro is None or libro.grado_id != current_user.grado_id or libro.asignatura_id != body.asignatura_id:
            raise HTTPException(status_code=404, detail="Lección no encontrada para tu grado y asignatura")
    actividad = await crear_actividad(
        db=db,
        asignatura_id=body.asignatura_id,
        tipo=body.tipo,
        estudiante=current_user,
        tema=body.tema,
        leccion_id=body.leccion_id,
        fragment_ids=body.fragment_ids,
        evitar_preguntas=body.evitar_preguntas,
        conceptos_estudiados=body.conceptos_estudiados,
    )
    if actividad is None:
        raise HTTPException(
            status_code=500,
            detail="No se pudo generar la actividad. Intenta de nuevo o con otro tema.",
        )
    return actividad


@router.post("/responder", response_model=ResultadoResponse)
async def responder(
    body: ResponderActividadRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    El estudiante envía su respuesta a una actividad.
    El sistema la evalúa y devuelve puntaje + retroalimentación.
    """
    resultado = await responder_actividad(
        db=db,
        actividad_id=body.actividad_id,
        respuesta_estudiante=body.respuesta,
        estudiante_id=current_user.id,
    )
    if resultado is None:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")
    return resultado


@router.get("/perfil", response_model=list[PerfilResponse])
async def mi_perfil(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Muestra el perfil de comprensión del estudiante:
    puntaje promedio por tema y nivel (domina/en_proceso/refuerzo).
    """
    return await obtener_perfil_estudiante(db, current_user.id)
