"""Lógica de negocio de autenticación: verificar credenciales, crear usuarios."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usuario import Usuario, RolUsuario
from app.security import hash_password, verify_password, create_access_token


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> Usuario | None:
    """Busca al usuario y verifica su contraseña. Devuelve None si falla."""
    result = await db.execute(
        select(Usuario).where(Usuario.username == username, Usuario.activo == True)
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def create_token_for_user(user: Usuario) -> str:
    """Genera un JWT con el id, username y rol del usuario."""
    return create_access_token(
        data={"sub": str(user.id), "username": user.username, "rol": user.rol.value}
    )


async def create_user(
    db: AsyncSession,
    nombre: str,
    apellido: str,
    username: str,
    password: str,
    rol: RolUsuario = RolUsuario.estudiante,
    grado_id: int | None = None,
) -> Usuario:
    """Crea un usuario nuevo con contraseña hasheada."""
    user = Usuario(
        nombre=nombre,
        apellido=apellido,
        username=username,
        password_hash=hash_password(password),
        rol=rol,
        grado_id=grado_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_username(db: AsyncSession, username: str) -> Usuario | None:
    result = await db.execute(select(Usuario).where(Usuario.username == username))
    return result.scalar_one_or_none()
