"""Endpoints del panel de administrador. Todos requieren rol administrador."""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.usuario import RolUsuario
from app.modules.admin import service
from app.modules.admin.schemas import (
    ActualizarAsignaturaRequest,
    ActualizarDocenteRequest,
    ActualizarEstudianteRequest,
    ActualizarGradoRequest,
    AsignaturaResumen,
    CrearAsignaturaRequest,
    CrearDocenteRequest,
    CrearEstudianteRequest,
    CrearGradoRequest,
    DashboardAdmin,
    DocenteResumen,
    EstudianteAdminResumen,
    EstudianteCreado,
    GradoResumen,
    PromoverGradoRequest,
    PromoverGradoResponse,
    ResetPasswordRequest,
)
from app.modules.auth.dependencies import require_role
from app.modules.auth.schemas import UsuarioResponse

router = APIRouter(prefix="/admin", tags=["Panel administrador"])

_admin = require_role(RolUsuario.administrador)


# ----------------------- Docentes -----------------------

@router.post("/docentes", response_model=UsuarioResponse, status_code=201)
async def crear_docente(body: CrearDocenteRequest, db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    return await service.crear_docente(
        db, body.nombre, body.apellido, body.username, body.password, body.grado_id
    )


@router.get("/docentes", response_model=list[DocenteResumen])
async def listar_docentes(db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    return await service.listar_docentes(db)


@router.put("/docentes/{docente_id}", response_model=UsuarioResponse)
async def actualizar_docente(
    docente_id: int, body: ActualizarDocenteRequest,
    db: AsyncSession = Depends(get_db), _=Depends(_admin),
):
    return await service.actualizar_docente(db, docente_id, body.model_dump(exclude_unset=True))


@router.post("/docentes/{docente_id}/reset-password", status_code=204)
async def reset_password_docente(
    docente_id: int, body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db), _=Depends(_admin),
):
    await service.reset_password(db, docente_id, body.nueva_password, RolUsuario.docente)


# ----------------------- Estudiantes -----------------------

@router.post("/estudiantes", response_model=EstudianteCreado, status_code=201)
async def crear_estudiante(body: CrearEstudianteRequest, db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    return await service.crear_estudiante(
        db, body.nombre, body.apellido, body.grado_id, body.username, body.password
    )


@router.get("/estudiantes", response_model=list[EstudianteAdminResumen])
async def listar_estudiantes(
    grado_id: int | None = None, activo: bool | None = None,
    db: AsyncSession = Depends(get_db), _=Depends(_admin),
):
    return await service.listar_estudiantes(db, grado_id, activo)


@router.put("/estudiantes/{estudiante_id}", response_model=UsuarioResponse)
async def actualizar_estudiante(
    estudiante_id: int, body: ActualizarEstudianteRequest,
    db: AsyncSession = Depends(get_db), _=Depends(_admin),
):
    return await service.actualizar_estudiante(db, estudiante_id, body.model_dump(exclude_unset=True))


@router.post("/estudiantes/{estudiante_id}/reset-password", status_code=204)
async def reset_password_estudiante(
    estudiante_id: int, body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db), _=Depends(_admin),
):
    await service.reset_password(db, estudiante_id, body.nueva_password, RolUsuario.estudiante)


@router.post("/estudiantes/importar", response_model=list[EstudianteCreado])
async def importar_estudiantes(
    archivo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), _=Depends(_admin),
):
    contenido = await archivo.read()
    return await service.importar_estudiantes_csv(db, contenido)


# ----------------------- Grados -----------------------

@router.post("/grados", response_model=GradoResumen, status_code=201)
async def crear_grado(body: CrearGradoRequest, db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    g = await service.crear_grado(db, body.nombre, body.nivel)
    return GradoResumen(id=g.id, nombre=g.nombre, nivel=g.nivel,
                        cantidad_estudiantes=0, cantidad_docentes=0)


@router.get("/grados", response_model=list[GradoResumen])
async def listar_grados(db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    return await service.listar_grados(db)


@router.put("/grados/{grado_id}", response_model=GradoResumen)
async def actualizar_grado(
    grado_id: int, body: ActualizarGradoRequest,
    db: AsyncSession = Depends(get_db), _=Depends(_admin),
):
    g = await service.actualizar_grado(db, grado_id, body.nombre)
    return GradoResumen(id=g.id, nombre=g.nombre, nivel=g.nivel,
                        cantidad_estudiantes=0, cantidad_docentes=0)


@router.delete("/grados/{grado_id}", status_code=204)
async def eliminar_grado(grado_id: int, db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    await service.eliminar_grado(db, grado_id)


# ----------------------- Asignaturas -----------------------

@router.post("/asignaturas", response_model=AsignaturaResumen, status_code=201)
async def crear_asignatura(body: CrearAsignaturaRequest, db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    a = await service.crear_asignatura(db, body.nombre)
    return AsignaturaResumen(id=a.id, nombre=a.nombre, cantidad_libros=0)


@router.get("/asignaturas", response_model=list[AsignaturaResumen])
async def listar_asignaturas(db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    return await service.listar_asignaturas(db)


@router.put("/asignaturas/{asignatura_id}", response_model=AsignaturaResumen)
async def actualizar_asignatura(
    asignatura_id: int, body: ActualizarAsignaturaRequest,
    db: AsyncSession = Depends(get_db), _=Depends(_admin),
):
    a = await service.actualizar_asignatura(db, asignatura_id, body.nombre)
    return AsignaturaResumen(id=a.id, nombre=a.nombre, cantidad_libros=0)


@router.delete("/asignaturas/{asignatura_id}", status_code=204)
async def eliminar_asignatura(asignatura_id: int, db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    await service.eliminar_asignatura(db, asignatura_id)


# ----------------------- Promoción de año + Dashboard -----------------------

@router.post("/promover-grado", response_model=PromoverGradoResponse)
async def promover_grado(body: PromoverGradoRequest, db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    return await service.promover_grado(db, body.grado_origen_id, body.grado_destino_id)


@router.get("/dashboard", response_model=DashboardAdmin)
async def dashboard(db: AsyncSession = Depends(get_db), _=Depends(_admin)):
    return await service.dashboard(db)
