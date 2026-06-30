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
    MiGradoResponse,
    PerfilTemaDocente,
    PreguntaFrecuente,
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


async def listar_estudiantes(
    db: AsyncSession, grado_id: int | None = None
) -> list[EstudianteResumen]:
    """Lista estudiantes. Si `grado_id` viene (docente), se acota a ese grado;
    si es None (administrador), devuelve todos."""
    completadas = await _completadas_por_estudiante(db)
    stmt = (
        select(Usuario, Grado.nombre)
        .outerjoin(Grado, Usuario.grado_id == Grado.id)
        .where(Usuario.rol == RolUsuario.estudiante)
    )
    if grado_id is not None:
        stmt = stmt.where(Usuario.grado_id == grado_id)
    rows = (await db.execute(stmt)).all()
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


async def mi_grado(db: AsyncSession, grado_id: int | None) -> MiGradoResponse:
    """Grado del docente autenticado (para el sidebar). None si no tiene grado."""
    if grado_id is None:
        return MiGradoResponse(id=None, nombre=None)
    nombre = (
        await db.execute(select(Grado.nombre).where(Grado.id == grado_id))
    ).scalar_one_or_none()
    return MiGradoResponse(id=grado_id, nombre=nombre)


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


async def estadisticas(
    db: AsyncSession, grado_id: int | None = None
) -> EstadisticasDocente:
    """Estadísticas del panel. Si `grado_id` viene (docente), todo se acota a ese
    grado; si es None (administrador), son globales."""
    total_estudiantes_stmt = (
        select(func.count()).select_from(Usuario).where(Usuario.rol == RolUsuario.estudiante)
    )
    total_libros_stmt = select(func.count()).select_from(LibroTexto)
    total_lecciones_stmt = select(func.count()).select_from(Leccion)
    if grado_id is not None:
        total_estudiantes_stmt = total_estudiantes_stmt.where(Usuario.grado_id == grado_id)
        total_libros_stmt = total_libros_stmt.where(LibroTexto.grado_id == grado_id)
        total_lecciones_stmt = total_lecciones_stmt.join(
            LibroTexto, Leccion.libro_id == LibroTexto.id
        ).where(LibroTexto.grado_id == grado_id)

    total_estudiantes = (await db.execute(total_estudiantes_stmt)).scalar_one()
    total_libros = (await db.execute(total_libros_stmt)).scalar_one()
    total_lecciones = (await db.execute(total_lecciones_stmt)).scalar_one()

    # Promedio de progreso: considera los 3 niveles de cada lección.
    # SUM(nivel_completado de todas las lecciones de todos los estudiantes)
    #   / (total_lecciones * 3 * total_estudiantes) * 100.
    suma_niveles_stmt = select(
        func.coalesce(func.sum(ProgresoLeccion.nivel_completado), 0)
    )
    if grado_id is not None:
        suma_niveles_stmt = suma_niveles_stmt.join(
            Usuario, ProgresoLeccion.estudiante_id == Usuario.id
        ).where(Usuario.grado_id == grado_id)
    suma_niveles = (await db.execute(suma_niveles_stmt)).scalar_one()
    denom = total_lecciones * 3 * total_estudiantes
    promedio_progreso = round(min(100.0, suma_niveles / denom * 100), 1) if denom > 0 else 0.0

    # Temas más preguntados: asignaturas por nº de mensajes de usuario, con una
    # pregunta reciente de ejemplo por asignatura.
    temas_stmt = (
        select(Asignatura.id, Asignatura.nombre, func.count(Mensaje.id))
        .join(Conversacion, Mensaje.conversacion_id == Conversacion.id)
        .join(Asignatura, Conversacion.asignatura_id == Asignatura.id)
        .where(Mensaje.rol == RolMensaje.usuario)
        .group_by(Asignatura.id, Asignatura.nombre)
        .order_by(func.count(Mensaje.id).desc())
        .limit(5)
    )
    if grado_id is not None:
        temas_stmt = temas_stmt.join(
            Usuario, Conversacion.estudiante_id == Usuario.id
        ).where(Usuario.grado_id == grado_id)
    temas_rows = (await db.execute(temas_stmt)).all()
    temas = []
    for asig_id, nombre, total in temas_rows:
        ejemplo_stmt = (
            select(Mensaje.contenido)
            .join(Conversacion, Mensaje.conversacion_id == Conversacion.id)
            .where(
                Conversacion.asignatura_id == asig_id,
                Mensaje.rol == RolMensaje.usuario,
            )
            .order_by(Mensaje.id.desc())
            .limit(1)
        )
        if grado_id is not None:
            ejemplo_stmt = ejemplo_stmt.join(
                Usuario, Conversacion.estudiante_id == Usuario.id
            ).where(Usuario.grado_id == grado_id)
        ejemplo = (await db.execute(ejemplo_stmt)).scalar_one_or_none()
        temas.append(TemaPreguntado(tema=nombre, total=total, ejemplo=ejemplo))

    # Desglose por pregunta concreta: agrupa los mensajes de usuario por su texto
    # normalizado (sin distinguir mayúsculas/espacios) y cuenta repeticiones. Así el
    # docente ve QUÉ se pregunta, no solo "Ciencias Naturales: 82".
    texto_norm = func.lower(func.trim(Mensaje.contenido))
    preguntas_stmt = (
        select(
            func.max(Mensaje.contenido),
            func.count(Mensaje.id),
            Asignatura.nombre,
        )
        .join(Conversacion, Mensaje.conversacion_id == Conversacion.id)
        .join(Asignatura, Conversacion.asignatura_id == Asignatura.id)
        .where(Mensaje.rol == RolMensaje.usuario)
        .group_by(texto_norm, Asignatura.nombre)
        .order_by(func.count(Mensaje.id).desc(), func.max(Mensaje.id).desc())
        .limit(10)
    )
    if grado_id is not None:
        preguntas_stmt = preguntas_stmt.join(
            Usuario, Conversacion.estudiante_id == Usuario.id
        ).where(Usuario.grado_id == grado_id)
    preguntas_rows = (await db.execute(preguntas_stmt)).all()
    preguntas_frecuentes = [
        PreguntaFrecuente(pregunta=pregunta, total=total, asignatura=asig)
        for pregunta, total, asig in preguntas_rows
    ]

    return EstadisticasDocente(
        total_estudiantes=total_estudiantes,
        total_libros=total_libros,
        total_lecciones=total_lecciones,
        promedio_progreso=promedio_progreso,
        temas_mas_preguntados=temas,
        preguntas_frecuentes=preguntas_frecuentes,
    )
