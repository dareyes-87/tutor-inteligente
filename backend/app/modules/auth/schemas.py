"""Esquemas Pydantic para autenticación (entrada y salida de la API)."""
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.usuario import RolUsuario


# --- Entrada ---
class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=4, max_length=128)


class RegistroRequest(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    apellido: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    rol: RolUsuario = RolUsuario.estudiante
    grado_id: int | None = None


# --- Salida ---
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UsuarioResponse(BaseModel):
    id: int
    nombre: str
    apellido: str
    username: str
    rol: RolUsuario
    grado_id: int | None
    activo: bool
    fecha_creacion: datetime

    model_config = {"from_attributes": True}
