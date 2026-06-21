"""
Lógica del panel docente. SOLO LECTURA: agrega datos de otros módulos sin
modificarlos. Reúsa por import `obtener_ruta` y `obtener_perfil_estudiante`.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asignatura import Asignatura
from app.models.conversacion import Conversacion
from app.models.fragmento import Fragmento
from app.models.grado import Grado
from app.models.leccion import Leccion
from app.models.libro import LibroTexto
from app.models.mensaje import Mensaje, RolMensaje
from app.models.progreso_leccion import EstadoLeccion, ProgresoLeccion
from app.models.usuario import RolUsuario, Usuario
from app.modules.actividades.service import obtener_perfil_estudiante
from app.modules.lecciones.service import obtener_ruta
from app.modules.docente.schemas import (
    EstadisticasDocente,
    EstudianteDetalle,
    EstudianteResumen,
    LibroDocente,
    PerfilTemaDocente,
    TemaPreguntado,
)


async def listar_libros(db: AsyncSession) -> list[LibroDocente]:
    frag_count = (
        select(func.count(Fragmento.id))
        .where(Fragmento.libro_id == LibroTexto.id)
        .correlate(LibroTexto)
        .scalar_subquery()
    )
    lec_count = (
        select(func.count(Leccion.id))
        .where(Leccion.libro_id == LibroTexto.id)
        .correlate(LibroTexto)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(LibroTexto, Asignatura.nombre, Grado.nombre, frag_count, lec_count)
            .join(Asignatura, LibroTexto.asignatura_id == Asignatura.id)
            .join(Grado, LibroTexto.grado_id == Grado.id)
            .order_by(LibroTexto.fecha_subida.desc())
        )
    ).all()
    return [
        LibroDocente(
            id=libro.id,
            titulo=libro.titulo,
            asignatura=asig,
            grado=grado,
            estado=libro.estado_indexacion.value,
            total_fragmentos=frags or 0,
            total_lecciones=lecs or 0,
            fecha_creacion=libro.fecha_subida,
        )
        for libro, asig, grado, frags, lecs in rows
    ]


async def _completadas_por_estudiante(db: AsyncSession) -> dict[int, int]:
    rows = (
        await db.execute(
            select(ProgresoLeccion.estudiante_id, func.count())
            .where(ProgresoLeccion.estado == EstadoLeccion.completada)
            .group_by(ProgresoLeccion.estudiante_id)
        )
    ).all()
    return {est_id: total for est_id, total in rows}


async def listar_estudiantes(db: AsyncSession) -> list[EstudianteResumen]:
    completadas = await _completadas_por_estudiante(db)
    rows = (
        await db.execute(
            select(Usuario, Grado.nombre)
            .outerjoin(Grado, Usuario.grado_id == Grado.id)
            .where(Usuario.rol == RolUsuario.estudiante)
        )
    ).all()
    estudiantes = [
        EstudianteResumen(
            id=u.id,
            nombre=u.nombre,
            apellido=u.apellido,
            grado=grado,
            racha_actual=u.racha_actual,
            puntos_totales=u.puntos_totales,
            lecciones_completadas=completadas.get(u.id, 0),
            ultima_actividad=u.ultima_actividad,
        )
        for u, grado in rows
    ]
    estudiantes.sort(key=lambda e: e.puntos_totales, reverse=True)
    return estudiantes


async def detalle_estudiante(
    db: AsyncSession, estudiante_id: int
) -> EstudianteDetalle | None:
    fila = (
        await db.execute(
            select(Usuario, Grado.nombre)
            .outerjoin(Grado, Usuario.grado_id == Grado.id)
            .where(Usuario.id == estudiante_id)
        )
    ).first()
    if fila is None:
        return None
    usuario, grado_nombre = fila

    # Ruta: libro del grado del estudiante (reusa obtener_ruta).
    libro = (
        await db.execute(
            select(LibroTexto)
            .where(LibroTexto.grado_id == usuario.grado_id)
            .order_by(LibroTexto.id)
        )
    ).scalars().first()
    ruta = await obtener_ruta(estudiante_id, libro.id, db) if libro else None

    # Perfil de comprensión (reusa la lógica de actividades).
    perfil_raw = await obtener_perfil_estudiante(db, estudiante_id)
    perfil = [PerfilTemaDocente(**p) for p in perfil_raw]

    return EstudianteDetalle(
        id=usuario.id,
        nombre=usuario.nombre,
        apellido=usuario.apellido,
        grado=grado_nombre,
        racha_actual=usuario.racha_actual,
        puntos_totales=usuario.puntos_totales,
        ruta=ruta,
        perfil=perfil,
    )


async def estadisticas(db: AsyncSession) -> EstadisticasDocente:
    total_estudiantes = (
        await db.execute(
            select(func.count()).select_from(Usuario).where(Usuario.rol == RolUsuario.estudiante)
        )
    ).scalar_one()
    total_libros = (
        await db.execute(select(func.count()).select_from(LibroTexto))
    ).scalar_one()
    total_lecciones = (
        await db.execute(select(func.count()).select_from(Leccion))
    ).scalar_one()

    # Promedio de progreso: media, por estudiante, de (completadas / total_lecciones).
    # Aproximación válida con un libro por grado (lo dominante hoy).
    completadas = await _completadas_por_estudiante(db)
    ids = (
        await db.execute(
            select(Usuario.id).where(Usuario.rol == RolUsuario.estudiante)
        )
    ).scalars().all()
    if ids and total_lecciones > 0:
        porcentajes = [
            min(100.0, completadas.get(sid, 0) / total_lecciones * 100) for sid in ids
        ]
        promedio_progreso = round(sum(porcentajes) / len(porcentajes), 1)
    else:
        promedio_progreso = 0.0

    # Temas más preguntados: asignaturas por nº de mensajes de usuario.
    temas_rows = (
        await db.execute(
            select(Asignatura.nombre, func.count(Mensaje.id))
            .join(Conversacion, Mensaje.conversacion_id == Conversacion.id)
            .join(Asignatura, Conversacion.asignatura_id == Asignatura.id)
            .where(Mensaje.rol == RolMensaje.usuario)
            .group_by(Asignatura.nombre)
            .order_by(func.count(Mensaje.id).desc())
            .limit(5)
        )
    ).all()
    temas = [TemaPreguntado(tema=nombre, total=total) for nombre, total in temas_rows]

    return EstadisticasDocente(
        total_estudiantes=total_estudiantes,
        total_libros=total_libros,
        total_lecciones=total_lecciones,
        promedio_progreso=promedio_progreso,
        temas_mas_preguntados=temas,
    )
