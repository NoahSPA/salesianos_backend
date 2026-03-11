from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.core.enums import Role
from app.core.schemas import APIModel, DocOut


class UserCreate(APIModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=200)
    role: Role
    active: bool = True
    player_id: str | None = Field(default=None, description="Opcional: vincula este usuario al jugador (ej. rol jugador)")


class UserUpdate(APIModel):
    """Actualización parcial: active y/o player_id."""
    active: bool | None = None
    player_id: str | None = None


class PlayerRefOut(APIModel):
    """Referencia mínima del jugador vinculado a un usuario."""
    id: str
    first_name: str
    last_name: str


class MePlayerOut(APIModel):
    """Jugador vinculado al usuario actual (para /me), con avatar opcional."""
    id: str
    first_name: str
    last_name: str
    avatar_url: str | None = None


class UserOut(DocOut):
    username: str
    role: Role
    active: bool
    player_id: str | None = None
    player: PlayerRefOut | None = Field(default=None, description="Jugador vinculado (populado en listado)")


class AdminSetPasswordIn(APIModel):
    """Solo admin: nueva contraseña para un usuario."""
    new_password: str = Field(min_length=8, max_length=200)


class ChangePasswordIn(APIModel):
    """Usuario autenticado: cambiar su propia contraseña."""
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class LoginIn(APIModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class TokenOut(APIModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class MeOut(APIModel):
    id: str
    username: str
    role: Role
    active: bool
    player_id: str | None = None
    player: MePlayerOut | None = None


class BootstrapAdminIn(APIModel):
    token: str = Field(min_length=1)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=12, max_length=200)


class RefreshTokenDoc(APIModel):
    user_id: str
    jti: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None = None

