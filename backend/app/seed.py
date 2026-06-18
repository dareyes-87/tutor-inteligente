"""
Seed: crea el usuario administrador al arrancar la aplicación,
si no existe todavía. Así siempre puedes loguearte sin insertar a mano.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.usuario import Usuario, RolUsuario
from app.security import hash_password


async def seed_admin(db: AsyncSession) -> None:
    result = await db.execute(
        select(Usuario).where(Usuario.username == settings.ADMIN_USERNAME)
    )
    if result.scalar_one_or_none() is not None:
        return  # ya existe, no hacer nada

    admin = Usuario(
        nombre="Administrador",
        apellido="Sistema",
        username=settings.ADMIN_USERNAME,
        password_hash=hash_password(settings.ADMIN_PASSWORD),
        rol=RolUsuario.administrador,
    )
    db.add(admin)
    await db.commit()
    print(f"[SEED] Admin creado: username='{settings.ADMIN_USERNAME}'")
