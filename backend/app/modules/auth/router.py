"""Endpoints de autenticación."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.usuario import RolUsuario
from app.modules.auth.dependencies import get_current_user, require_role
from app.modules.auth.schemas import (
    LoginRequest, RegistroRequest, TokenResponse, UsuarioResponse,
)
from app.modules.auth.service import (
    authenticate_user, create_token_for_user, create_user, get_user_by_username,
)

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Inicia sesión y devuelve un token JWT."""
    user = await authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )
    token = create_token_for_user(user)
    return TokenResponse(access_token=token)


@router.post(
    "/registro",
    response_model=UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
)
async def registro(
    body: RegistroRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(RolUsuario.administrador, RolUsuario.docente)),
):
    """Registra un usuario nuevo. Solo administradores y docentes pueden crear usuarios."""
    existing = await get_user_by_username(db, body.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El username ya está en uso",
        )
    user = await create_user(
        db,
        nombre=body.nombre,
        apellido=body.apellido,
        username=body.username,
        password=body.password,
        rol=body.rol,
        grado_id=body.grado_id,
    )
    return user


@router.get("/me", response_model=UsuarioResponse)
async def me(current_user=Depends(get_current_user)):
    """Devuelve los datos del usuario autenticado."""
    return current_user
