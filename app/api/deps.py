from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_jwt
from app.db.ids import oid
from app.db.mongo import get_db

security = HTTPBearer(auto_error=False)

Role = Literal["admin", "delegado", "tesorero", "jugador"]


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")

    try:
        payload = decode_jwt(creds.credentials)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    if payload.get("typ") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    db = get_db()
    user = await db.users.find_one({"_id": oid(user_id), "active": True}, projection={"password_hash": 0})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")

    user["id"] = str(user.pop("_id"))
    return user


def require_roles(*roles: Role) -> Callable:
    async def _guard(user: Annotated[dict, Depends(get_current_user)], request: Request) -> dict:
        role = user.get("role")
        if role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permiso")
        return user

    return _guard

