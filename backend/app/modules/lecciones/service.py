"""
Lógica de negocio de la ruta de aprendizaje y la gamificación.

Expone: ruta del estudiante (con progreso por lección), iniciar/completar
lecciones, y la capa de gamificación (rachas + ranking) integrada con las
lecciones. Las funciones son async y son dueñas del commit.
"""
import logging
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asignatura import Asignatura
from app.models.leccion import Leccion
from app.models.libro import LibroTexto
from app.models.progreso_leccion import EstadoLeccion, ProgresoLeccion
from app.models.usuario import RolUsuario, Usuario
from app.modules.lecciones.schemas import (
    LeccionEnRuta,
    RachaResponse,
    RankingEstudiante,
    RankingResponse,
    RutaAprendizaje,
)

logger = logging.getLogger(__name__)

# Puntaje mínimo (promedio) para dar una lección por completada.
PUNTAJE_MINIMO_COMPLETAR = 70


async def _get_or_create_progreso(
    estudiante_id: int, leccion: Leccion, db: AsyncSession
) -> ProgresoLeccion:
    """Obtiene el progreso del estudiante en una lección; lo crea si no existe.

    La primera lección (orden=1) nace 'disponible'; las demás 'bloqueada'.
    Usa flush (no commit) — el commit lo hace la función que orquesta.
    """
    result = await db.execute(
        select(ProgresoLeccion).where(
            ProgresoLeccion.estudiante_id == estudiante_id,
            ProgresoLeccion.leccion_id == leccion.id,
        )
    )
    progreso = result.scalar_one_or_none()
    if progreso is None:
        progreso = ProgresoLeccion(
            estudiante_id=estudiante_id,
            leccion_id=leccion.id,
            estado=(
                EstadoLeccion.disponible if leccion.orden == 1 else EstadoLeccion.bloqueada
            ),
        )
        db.add(progreso)
        await db.flush()
    return progreso


def _to_leccion_en_ruta(leccion: Leccion, progreso: ProgresoLeccion) -> LeccionEnRuta:
    return LeccionEnRuta(
        id=leccion.id,
        nombre=leccion.nombre,
        descripcion=leccion.descripcion,
        orden=leccion.orden,
        tema_clave=leccion.tema_clave,
        paginas=leccion.paginas,
        estado=progreso.estado.value,
        puntaje_promedio=round(progreso.puntaje_promedio, 1),
        actividades_completadas=progreso.actividades_completadas,
        actividades_requeridas=progreso.actividades_requeridas,
    )


async def obtener_ruta(
    estudiante_id: int, libro_id: int, db: AsyncSession
) -> RutaAprendizaje:
    """Ruta completa del libro con el progreso del estudiante (inicializa lo que falte)."""
    fila = (
        await db.execute(
            select(LibroTexto, Asignatura.nombre)
            .join(Asignatura, LibroTexto.asignatura_id == Asignatura.id)
            .where(LibroTexto.id == libro_id)
        )
    ).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Libro no encontrado")
    _libro, asignatura_nombre = fila

    lecciones = list(
        (
            await db.execute(
                select(Leccion).where(Leccion.libro_id == libro_id).order_by(Leccion.orden)
            )
        ).scalars().all()
    )

    items: list[LeccionEnRuta] = []
    completadas = 0
    for leccion in lecciones:
        progreso = await _get_or_create_progreso(estudiante_id, leccion, db)
        if progreso.estado == EstadoLeccion.completada:
            completadas += 1
        items.append(_to_leccion_en_ruta(leccion, progreso))

    await db.commit()

    total = len(lecciones)
    pct = round((completadas / total) * 100, 1) if total else 0.0
    return RutaAprendizaje(
        libro_id=libro_id,
        asignatura=asignatura_nombre,
        total_lecciones=total,
        lecciones_completadas=completadas,
        progreso_porcentaje=pct,
        lecciones=items,
    )


async def iniciar_leccion(
    estudiante_id: int, leccion_id: int, db: AsyncSession
) -> LeccionEnRuta:
    """Marca una lección 'disponible' como 'en_progreso'."""
    leccion = (
        await db.execute(select(Leccion).where(Leccion.id == leccion_id))
    ).scalar_one_or_none()
    if leccion is None:
        raise HTTPException(status_code=404, detail="Lección no encontrada")

    progreso = await _get_or_create_progreso(estudiante_id, leccion, db)
    if progreso.estado != EstadoLeccion.disponible:
        raise HTTPException(
            status_code=400,
            detail=f"La lección no está disponible (estado actual: {progreso.estado.value}).",
        )

    progreso.estado = EstadoLeccion.en_progreso
    progreso.fecha_inicio = datetime.now(timezone.utc)
    await db.commit()
    return _to_leccion_en_ruta(leccion, progreso)


async def completar_actividad_leccion(
    estudiante_id: int, leccion_id: int, puntaje: int, db: AsyncSession
) -> LeccionEnRuta:
    """Registra una actividad completada en una lección y, si corresponde,
    completa la lección, desbloquea la siguiente y actualiza racha + puntos."""
    leccion = (
        await db.execute(select(Leccion).where(Leccion.id == leccion_id))
    ).scalar_one_or_none()
    if leccion is None:
        raise HTTPException(status_code=404, detail="Lección no encontrada")

    progreso = await _get_or_create_progreso(estudiante_id, leccion, db)

    # Promedio acumulativo sobre las actividades completadas.
    prev = progreso.actividades_completadas
    progreso.puntaje_promedio = (progreso.puntaje_promedio * prev + puntaje) / (prev + 1)
    progreso.actividades_completadas = prev + 1

    ya_completada = progreso.estado == EstadoLeccion.completada
    if (
        not ya_completada
        and progreso.actividades_completadas >= progreso.actividades_requeridas
        and progreso.puntaje_promedio >= PUNTAJE_MINIMO_COMPLETAR
    ):
        progreso.estado = EstadoLeccion.completada
        progreso.fecha_completada = datetime.now(timezone.utc)

        # Desbloquear la siguiente lección (orden + 1).
        siguiente = (
            await db.execute(
                select(Leccion).where(
                    Leccion.libro_id == leccion.libro_id,
                    Leccion.orden == leccion.orden + 1,
                )
            )
        ).scalar_one_or_none()
        if siguiente is not None:
            prog_sig = await _get_or_create_progreso(estudiante_id, siguiente, db)
            if prog_sig.estado == EstadoLeccion.bloqueada:
                prog_sig.estado = EstadoLeccion.disponible

        # Gamificación: la racha y los puntos solo avanzan al COMPLETAR.
        await actualizar_racha(estudiante_id, db)
        usuario = (
            await db.execute(select(Usuario).where(Usuario.id == estudiante_id))
        ).scalar_one()
        usuario.puntos_totales += puntaje

    await db.commit()
    return _to_leccion_en_ruta(leccion, progreso)


async def actualizar_racha(estudiante_id: int, db: AsyncSession) -> None:
    """Actualiza la racha del estudiante según su última actividad.

    Suma puntos NO es responsabilidad de esta función (lo hace el caller).
    No hace commit: lo hace la función que la invoca.
    """
    usuario = (
        await db.execute(select(Usuario).where(Usuario.id == estudiante_id))
    ).scalar_one()

    hoy = date.today()
    ultima = usuario.ultima_actividad

    if ultima == hoy:
        return  # ya contó hoy

    if ultima is not None and (hoy - ultima).days == 1:
        usuario.racha_actual += 1  # ayer → continúa la racha
    else:
        usuario.racha_actual = 1  # primera vez o racha rota

    if usuario.racha_actual > usuario.mejor_racha:
        usuario.mejor_racha = usuario.racha_actual

    usuario.ultima_actividad = hoy


async def obtener_racha(estudiante_id: int, db: AsyncSession) -> RachaResponse:
    usuario = (
        await db.execute(select(Usuario).where(Usuario.id == estudiante_id))
    ).scalar_one()
    return RachaResponse(
        racha_actual=usuario.racha_actual,
        mejor_racha=usuario.mejor_racha,
        activo_hoy=(usuario.ultima_actividad == date.today()),
    )


async def obtener_ranking(
    grado_id: int | None, estudiante_id: int, db: AsyncSession
) -> RankingResponse:
    """Ranking de los estudiantes del grado, por puntos y lecciones completadas."""
    estudiantes = list(
        (
            await db.execute(
                select(Usuario).where(
                    Usuario.grado_id == grado_id,
                    Usuario.rol == RolUsuario.estudiante,
                )
            )
        ).scalars().all()
    )

    # Lecciones completadas por estudiante (agregado en una sola query).
    comp_rows = (
        await db.execute(
            select(ProgresoLeccion.estudiante_id, func.count())
            .where(ProgresoLeccion.estado == EstadoLeccion.completada)
            .group_by(ProgresoLeccion.estudiante_id)
        )
    ).all()
    completadas_por = {est_id: total for est_id, total in comp_rows}

    estudiantes.sort(
        key=lambda u: (u.puntos_totales, completadas_por.get(u.id, 0)),
        reverse=True,
    )

    ranking: list[RankingEstudiante] = []
    mi_posicion = 0
    for posicion, u in enumerate(estudiantes, start=1):
        ranking.append(
            RankingEstudiante(
                posicion=posicion,
                nombre=u.nombre,
                apellido=u.apellido,
                lecciones_completadas=completadas_por.get(u.id, 0),
                puntos_totales=u.puntos_totales,
                racha_actual=u.racha_actual,
            )
        )
        if u.id == estudiante_id:
            mi_posicion = posicion

    return RankingResponse(ranking=ranking, mi_posicion=mi_posicion)
