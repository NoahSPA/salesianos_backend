from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, Response, status

from app.core.security import REFRESH_COOKIE_NAME, access_expires, create_jwt, refresh_expires, verify_password
from app.core.settings import settings
from app.db.ids import oid
from app.db.mongo import get_db, now_utc


def _cookie_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "path": "/api/auth",
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    return kwargs


def _new_jti() -> str:
    return secrets.token_urlsafe(24)


async def bootstrap_first_admin(*, token: str, username: str, password_hash: str) -> dict:
    if not settings.bootstrap_token or token != settings.bootstrap_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permiso")

    db = get_db()
    existing = await db.users.estimated_document_count()
    if existing and existing > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bootstrap no disponible")

    now = now_utc()
    doc = {
        "username": username,
        "password_hash": password_hash,
        "role": "admin",
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.users.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


async def authenticate_user(*, username: str, password: str) -> dict:
    db = get_db()
    user = await db.users.find_one({"username": username, "active": True})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    if not verify_password(password, user.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    return user


async def issue_tokens(*, response: Response, user: dict) -> dict:
    user_id = str(user["_id"])
    role = user["role"]

    access_token = create_jwt(
        subject=user_id,
        role=role,
        token_type="access",
        expires_in=access_expires(),
    )

    jti = _new_jti()
    refresh_token = create_jwt(
        subject=user_id,
        role=role,
        token_type="refresh",
        expires_in=refresh_expires(),
        extra={"jti": jti},
    )

    now = now_utc()
    expires_at = now + refresh_expires()
    db = get_db()
    await db.refresh_tokens.insert_one(
        {
            "user_id": oid(user_id),
            "jti": jti,
            "created_at": now,
            "expires_at": expires_at,
            "revoked_at": None,
        }
    )

    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=int(refresh_expires().total_seconds()),
        **_cookie_kwargs(),
    )

    return {
        "access_token": access_token,
        "expires_in_seconds": int(access_expires().total_seconds()),
    }


async def rotate_refresh(*, response: Response, refresh_token: str, payload: dict) -> dict:
    if payload.get("typ") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    user_id = payload.get("sub")
    jti = payload.get("jti")
    if not isinstance(user_id, str) or not isinstance(jti, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    db = get_db()
    token_doc = await db.refresh_tokens.find_one({"user_id": oid(user_id), "jti": jti, "revoked_at": None})
    if not token_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    # Revoca el refresh actual (rotación)
    now = now_utc()
    await db.refresh_tokens.update_one({"_id": token_doc["_id"]}, {"$set": {"revoked_at": now}})

    user = await db.users.find_one({"_id": oid(user_id), "active": True})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")

    return await issue_tokens(response=response, user=user)


async def logout(*, response: Response, refresh_token: str | None, payload: dict | None) -> None:
    if refresh_token and payload and payload.get("typ") == "refresh":
        user_id = payload.get("sub")
        jti = payload.get("jti")
        if isinstance(user_id, str) and isinstance(jti, str):
            db = get_db()
            await db.refresh_tokens.update_one(
                {"user_id": oid(user_id), "jti": jti, "revoked_at": None},
                {"$set": {"revoked_at": now_utc()}},
            )

    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/api/auth")

