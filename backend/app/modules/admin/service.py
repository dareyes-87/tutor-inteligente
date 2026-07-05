"""
Lógica del panel de administrador: gestiona la ESTRUCTURA del colegio
(usuarios, grados, asignaturas) y la salud global del sistema.

Reusa `create_user`/`hash_password` de auth. El login ya rechaza usuarios con
`activo == False` (soft delete), así que desactivar basta para bloquear acceso.
"""
import csv
import io
import re
import unicodedata

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asignatura import Asignatura
from app.models.fragmento import Fragmento
from app.models.grado import Grado
from app.models.leccion import Leccion
from app.models.libro import LibroTexto
from app.models.progreso_leccion import ProgresoLeccion
from app.models.usuario import RolUsuario, Usuario
from app.modules.lecciones.service import hoy_guatemala
from app.modules.admin.schemas import (
    AsignaturaResumen,
    DashboardAdmin,
    DocenteResumen,
    EstudianteAdminResumen,
    EstudianteCreado,
    GradoResumen,
    LibroReciente,
    PromoverGradoResponse,
)
from app.modules.auth.service import create_user
from app.security import hash_password


# ----------------------- Helpers -----------------------

def _slug(texto: str) -> str:
    """Minúsculas, sin tildes ni caracteres no alfanuméricos."""
    norm = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", norm.lower())


def _nivel_de_grado(nombre: str) -> str:
    n = nombre.lower()
    if "basico" in n or "básico" in n:
        return "basico"
    if "diversificado" in n:
        return "diversificado"
    return "primaria"


async def _username_unico(db: AsyncSession, base: str) -> str:
    base = base or "usuario"
    candidato = base
    i = 1
    while (
        await db.execute(select(Usuario.id).where(Usuario.username == candidato))
    ).scalar_one_or_none() is not None:
        i += 1
        candidato = f"{base}{i}"
    return candidato


async def _total_lecciones_por_grado(db: AsyncSession) -> dict[int, int]:
    rows = (
        await db.execute(
            select(LibroTexto.grado_id, func.count(Leccion.id))
            .join(Leccion, Leccion.libro_id == LibroTexto.id)
            .group_by(LibroTexto.grado_id)
        )
    ).all()
    return {gid: total for gid, total in rows}


async def _niveles_por_estudiante(db: AsyncSession) -> dict[int, int]:
    rows = (
        await db.execute(
            select(
                ProgresoLeccion.estudiante_id,
                func.coalesce(func.sum(ProgresoLeccion.nivel_completado), 0),
            ).group_by(ProgresoLeccion.estudiante_id)
        )
    ).all()
    return {eid: int(total) for eid, total in rows}


def _progreso_pct(suma_niveles: int, total_lecciones_grado: int) -> float:
    denom = total_lecciones_grado * 3
    if denom <= 0:
        return 0.0
    return round(min(100.0, suma_niveles / denom * 100), 1)


# ----------------------- Docentes -----------------------

async def crear_docente(
    db: AsyncSession, nombre: str, apellido: str, username: str,
    password: str, grado_id: int | None,
) -> Usuario:
    if (await db.execute(select(Usuario.id).where(Usuario.username == username))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="El username ya está en uso")
    return await create_user(
        db, nombre=nombre, apellido=apellido, username=username,
        password=password, rol=RolUsuario.docente, grado_id=grado_id,
    )


async def listar_docentes(db: AsyncSession) -> list[DocenteResumen]:
    libros_count = (
        select(func.count(LibroTexto.id))
        .where(LibroTexto.subido_por == Usuario.id)
        .correlate(Usuario)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(Usuario, Grado.nombre, libros_count)
            .outerjoin(Grado, Usuario.grado_id == Grado.id)
            .where(Usuario.rol == RolUsuario.docente)
            .order_by(Usuario.nombre)
        )
    ).all()
    return [
        DocenteResumen(
            id=u.id, nombre=u.nombre, apellido=u.apellido, username=u.username,
            activo=u.activo, grado_id=u.grado_id, grado=grado, libros_subidos=libros or 0,
        )
        for u, grado, libros in rows
    ]


async def actualizar_docente(
    db: AsyncSession, docente_id: int, datos: dict,
) -> Usuario:
    u = (
        await db.execute(
            select(Usuario).where(
                Usuario.id == docente_id, Usuario.rol == RolUsuario.docente
            )
        )
    ).scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=404, detail="Docente no encontrado")
    for campo in ("nombre", "apellido", "grado_id", "activo"):
        if datos.get(campo) is not None:
            setattr(u, campo, datos[campo])
    await db.commit()
    await db.refresh(u)
    return u


# ----------------------- Estudiantes -----------------------

async def crear_estudiante(
    db: AsyncSession, nombre: str, apellido: str, grado_id: int,
    username: str | None, password: str | None,
) -> EstudianteCreado:
    """Crea un estudiante; auto-genera username/password si no se dan."""
    if username:
        if (await db.execute(select(Usuario.id).where(Usuario.username == username))).scalar_one_or_none():
            raise HTTPException(status_code=409, detail="El username ya está en uso")
        final_username = username
    else:
        base = (_slug(nombre)[:1] + _slug(apellido)) or "estudiante"
        final_username = await _username_unico(db, base)
    final_password = password or (_slug(apellido) + "123")

    u = await create_user(
        db, nombre=nombre, apellido=apellido, username=final_username,
        password=final_password, rol=RolUsuario.estudiante, grado_id=grado_id,
    )
    return EstudianteCreado(
        id=u.id, nombre=u.nombre, apellido=u.apellido,
        username=u.username, password_generado=final_password,
    )


async def listar_estudiantes(
    db: AsyncSession, grado_id: int | None = None, activo: bool | None = None,
) -> list[EstudianteAdminResumen]:
    cond = [Usuario.rol == RolUsuario.estudiante]
    if grado_id is not None:
        cond.append(Usuario.grado_id == grado_id)
    if activo is not None:
        cond.append(Usuario.activo == activo)
    rows = (
        await db.execute(
            select(Usuario, Grado.nombre)
            .outerjoin(Grado, Usuario.grado_id == Grado.id)
            .where(*cond)
            .order_by(Usuario.apellido, Usuario.nombre)
        )
    ).all()

    total_por_grado = await _total_lecciones_por_grado(db)
    niveles = await _niveles_por_estudiante(db)
    return [
        EstudianteAdminResumen(
            id=u.id, nombre=u.nombre, apellido=u.apellido, username=u.username,
            grado_id=u.grado_id, grado=grado, activo=u.activo,
            progreso=_progreso_pct(niveles.get(u.id, 0), total_por_grado.get(u.grado_id, 0)),
            ultima_actividad=u.ultima_actividad,
        )
        for u, grado in rows
    ]


async def actualizar_estudiante(
    db: AsyncSession, estudiante_id: int, datos: dict,
) -> Usuario:
    u = (
        await db.execute(
            select(Usuario).where(
                Usuario.id == estudiante_id, Usuario.rol == RolUsuario.estudiante
            )
        )
    ).scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    for campo in ("nombre", "apellido", "grado_id", "activo"):
        if datos.get(campo) is not None:
            setattr(u, campo, datos[campo])
    await db.commit()
    await db.refresh(u)
    return u


async def importar_estudiantes_csv(
    db: AsyncSession, contenido: bytes,
) -> list[EstudianteCreado]:
    """Importa estudiantes desde un CSV con columnas: nombre,apellido,grado_id."""
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = contenido.decode("latin-1")
    reader = csv.DictReader(io.StringIO(texto))
    if not reader.fieldnames or not {"nombre", "apellido", "grado_id"} <= {
        (f or "").strip().lower() for f in reader.fieldnames
    }:
        raise HTTPException(
            status_code=400,
            detail="El CSV debe tener las columnas: nombre, apellido, grado_id",
        )

    # Normaliza encabezados a minúsculas para tolerar variaciones.
    creados: list[EstudianteCreado] = []
    for fila in reader:
        fila = {(k or "").strip().lower(): (v or "").strip() for k, v in fila.items()}
        nombre, apellido, grado_raw = fila.get("nombre"), fila.get("apellido"), fila.get("grado_id")
        if not nombre or not apellido or not grado_raw:
            continue
        try:
            grado_id = int(grado_raw)
        except ValueError:
            continue
        base = (_slug(nombre)[:1] + _slug(apellido)) or "estudiante"
        final_username = await _username_unico(db, base)
        final_password = _slug(apellido) + "123"
        u = Usuario(
            nombre=nombre, apellido=apellido, username=final_username,
            password_hash=hash_password(final_password),
            rol=RolUsuario.estudiante, grado_id=grado_id,
        )
        db.add(u)
        await db.flush()  # para que _username_unico vea los recién creados
        creados.append(EstudianteCreado(
            id=u.id, nombre=nombre, apellido=apellido,
            username=final_username, password_generado=final_password,
        ))
    await db.commit()
    return creados


# ----------------------- Reset de contraseña -----------------------

async def reset_password(
    db: AsyncSession, usuario_id: int, nueva_password: str, rol: RolUsuario,
) -> None:
    u = (
        await db.execute(
            select(Usuario).where(Usuario.id == usuario_id, Usuario.rol == rol)
        )
    ).scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=404, detail=f"{rol.value.capitalize()} no encontrado")
    u.password_hash = hash_password(nueva_password)
    await db.commit()


# ----------------------- Grados -----------------------

async def crear_grado(db: AsyncSession, nombre: str, nivel: str | None) -> Grado:
    if (await db.execute(select(Grado.id).where(Grado.nombre == nombre))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe un grado con ese nombre")
    grado = Grado(nombre=nombre, nivel=nivel or _nivel_de_grado(nombre))
    db.add(grado)
    await db.commit()
    await db.refresh(grado)
    return grado


async def listar_grados(db: AsyncSession) -> list[GradoResumen]:
    est_count = (
        select(func.count(Usuario.id))
        .where(Usuario.grado_id == Grado.id, Usuario.rol == RolUsuario.estudiante)
        .correlate(Grado).scalar_subquery()
    )
    doc_count = (
        select(func.count(Usuario.id))
        .where(Usuario.grado_id == Grado.id, Usuario.rol == RolUsuario.docente)
        .correlate(Grado).scalar_subquery()
    )
    rows = (
        await db.execute(
            select(Grado, est_count, doc_count).order_by(Grado.nombre)
        )
    ).all()
    return [
        GradoResumen(
            id=g.id, nombre=g.nombre, nivel=g.nivel,
            cantidad_estudiantes=est or 0, cantidad_docentes=doc or 0,
        )
        for g, est, doc in rows
    ]


async def actualizar_grado(db: AsyncSession, grado_id: int, nombre: str) -> Grado:
    g = (await db.execute(select(Grado).where(Grado.id == grado_id))).scalar_one_or_none()
    if g is None:
        raise HTTPException(status_code=404, detail="Grado no encontrado")
    g.nombre = nombre
    g.nivel = _nivel_de_grado(nombre)
    await db.commit()
    await db.refresh(g)
    return g


async def eliminar_grado(db: AsyncSession, grado_id: int) -> None:
    g = (await db.execute(select(Grado).where(Grado.id == grado_id))).scalar_one_or_none()
    if g is None:
        raise HTTPException(status_code=404, detail="Grado no encontrado")
    n_est = (
        await db.execute(
            select(func.count(Usuario.id)).where(Usuario.grado_id == grado_id)
        )
    ).scalar_one()
    n_lib = (
        await db.execute(
            select(func.count(LibroTexto.id)).where(LibroTexto.grado_id == grado_id)
        )
    ).scalar_one()
    if n_est > 0 or n_lib > 0:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede eliminar: el grado tiene {n_est} usuario(s) y {n_lib} libro(s) asociados.",
        )
    await db.delete(g)
    await db.commit()


# ----------------------- Asignaturas -----------------------

async def crear_asignatura(db: AsyncSession, nombre: str) -> Asignatura:
    if (await db.execute(select(Asignatura.id).where(Asignatura.nombre == nombre))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe una asignatura con ese nombre")
    a = Asignatura(nombre=nombre)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


async def listar_asignaturas(db: AsyncSession) -> list[AsignaturaResumen]:
    lib_count = (
        select(func.count(LibroTexto.id))
        .where(LibroTexto.asignatura_id == Asignatura.id)
        .correlate(Asignatura).scalar_subquery()
    )
    rows = (
        await db.execute(select(Asignatura, lib_count).order_by(Asignatura.nombre))
    ).all()
    return [
        AsignaturaResumen(id=a.id, nombre=a.nombre, cantidad_libros=libros or 0)
        for a, libros in rows
    ]


async def actualizar_asignatura(db: AsyncSession, asignatura_id: int, nombre: str) -> Asignatura:
    a = (await db.execute(select(Asignatura).where(Asignatura.id == asignatura_id))).scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="Asignatura no encontrada")
    a.nombre = nombre
    await db.commit()
    await db.refresh(a)
    return a


async def eliminar_asignatura(db: AsyncSession, asignatura_id: int) -> None:
    a = (await db.execute(select(Asignatura).where(Asignatura.id == asignatura_id))).scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="Asignatura no encontrada")
    n_lib = (
        await db.execute(
            select(func.count(LibroTexto.id)).where(LibroTexto.asignatura_id == asignatura_id)
        )
    ).scalar_one()
    if n_lib > 0:
        raise HTTPException(
            status_code=409,
            detail=f"No se puede eliminar: la asignatura tiene {n_lib} libro(s) asociados.",
        )
    await db.delete(a)
    await db.commit()


# ----------------------- Promoción de año -----------------------

async def promover_grado(
    db: AsyncSession, grado_origen_id: int, grado_destino_id: int,
) -> PromoverGradoResponse:
    if grado_origen_id == grado_destino_id:
        raise HTTPException(status_code=400, detail="El grado origen y destino deben ser distintos")
    for gid in (grado_origen_id, grado_destino_id):
        if (await db.execute(select(Grado.id).where(Grado.id == gid))).scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail=f"Grado {gid} no encontrado")

    estudiantes = (
        await db.execute(
            select(Usuario).where(
                Usuario.grado_id == grado_origen_id,
                Usuario.rol == RolUsuario.estudiante,
                Usuario.activo == True,  # noqa: E712
            )
        )
    ).scalars().all()
    for e in estudiantes:
        e.grado_id = grado_destino_id
    await db.commit()
    return PromoverGradoResponse(estudiantes_promovidos=len(estudiantes))


# ----------------------- Dashboard -----------------------

async def dashboard(db: AsyncSession) -> DashboardAdmin:
    async def _count(stmt) -> int:
        return (await db.execute(stmt)).scalar_one()

    total_estudiantes = await _count(
        select(func.count()).select_from(Usuario).where(
            Usuario.rol == RolUsuario.estudiante, Usuario.activo == True  # noqa: E712
        )
    )
    total_docentes = await _count(
        select(func.count()).select_from(Usuario).where(
            Usuario.rol == RolUsuario.docente, Usuario.activo == True  # noqa: E712
        )
    )
    total_grados = await _count(select(func.count()).select_from(Grado))
    total_asignaturas = await _count(select(func.count()).select_from(Asignatura))
    total_libros = await _count(select(func.count()).select_from(LibroTexto))
    total_lecciones = await _count(select(func.count()).select_from(Leccion))
    total_fragmentos = await _count(select(func.count()).select_from(Fragmento))

    # Progreso general: promedio del % por estudiante activo (basado en niveles).
    total_por_grado = await _total_lecciones_por_grado(db)
    niveles = await _niveles_por_estudiante(db)
    activos = (
        await db.execute(
            select(Usuario.id, Usuario.grado_id).where(
                Usuario.rol == RolUsuario.estudiante, Usuario.activo == True  # noqa: E712
            )
        )
    ).all()
    if activos:
        pcts = [_progreso_pct(niveles.get(eid, 0), total_por_grado.get(gid, 0)) for eid, gid in activos]
        progreso_general = round(sum(pcts) / len(pcts), 1)
    else:
        progreso_general = 0.0

    estudiantes_activos_hoy = await _count(
        select(func.count()).select_from(Usuario).where(
            Usuario.rol == RolUsuario.estudiante,
            Usuario.ultima_actividad == hoy_guatemala(),
        )
    )

    libro = (
        await db.execute(
            select(LibroTexto).order_by(LibroTexto.fecha_subida.desc()).limit(1)
        )
    ).scalar_one_or_none()
    libro_reciente = (
        LibroReciente(
            titulo=libro.titulo,
            fecha_subida=libro.fecha_subida,
            estado=libro.estado_indexacion.value,
        )
        if libro else None
    )

    return DashboardAdmin(
        total_estudiantes=total_estudiantes,
        total_docentes=total_docentes,
        total_grados=total_grados,
        total_asignaturas=total_asignaturas,
        total_libros=total_libros,
        total_lecciones=total_lecciones,
        total_fragmentos=total_fragmentos,
        progreso_general=progreso_general,
        estudiantes_activos_hoy=estudiantes_activos_hoy,
        libro_mas_reciente=libro_reciente,
    )
