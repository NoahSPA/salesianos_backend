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


class UserOut(DocOut):
    username: str
    role: Role
    active: bool


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

