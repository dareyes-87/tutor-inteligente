"""
Conexión a PostgreSQL con SQLAlchemy asíncrono.
- engine: el motor de conexión (con pool, suficiente para ~90 usuarios).
- AsyncSessionLocal: fábrica de sesiones para hablar con la BD.
- Base: clase de la que heredarán todos los modelos (tablas) en el Sprint 1.
- get_db: dependencia de FastAPI que entrega una sesión por petición.
"""
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url_async,
    pool_size=10,
    max_overflow=10,
    pool_pre_ping=True,  # evita usar conexiones muertas
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    """Todos los modelos del Sprint 1 heredarán de aquí."""
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
