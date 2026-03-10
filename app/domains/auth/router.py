from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.api.deps import get_current_user, require_roles
from app.core.security import REFRESH_COOKIE_NAME, decode_jwt, hash_password, verify_password
from app.db.ids import oid
from app.db.mongo import get_db, now_utc
from app.domains.audit.service import log_audit
from app.domains.auth.schemas import AdminSetPasswordIn, BootstrapAdminIn, ChangePasswordIn, LoginIn, MeOut, TokenOut, UserCreate, UserOut
from app.domains.auth.service import authenticate_user, bootstrap_first_admin, issue_tokens, logout as logout_service, rotate_refresh

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/bootstrap-admin", response_model=MeOut)
async def bootstrap_admin(payload: BootstrapAdminIn) -> MeOut:
    doc = await bootstrap_first_admin(
        token=payload.token,
        username=payload.username,
        password_hash=hash_password(payload.password),
    )
    return MeOut(id=str(doc["_id"]), username=doc["username"], role=doc["role"], active=doc["active"])


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginIn, response: Response) -> TokenOut:
    user = await authenticate_user(username=payload.username, password=payload.password)
    out = await issue_tokens(response=response, user=user)
    return TokenOut(**out)


@router.post("/refresh", response_model=TokenOut)
async def refresh(
    response: Response,
    refresh_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> TokenOut:
    if not refresh_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    payload = decode_jwt(refresh_cookie)
    out = await rotate_refresh(response=response, refresh_token=refresh_cookie, payload=payload)
    return TokenOut(**out)


@router.post("/logout")
async def logout(
    response: Response,
    refresh_cookie: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> dict:
    payload = None
    if refresh_cookie:
        try:
            payload = decode_jwt(refresh_cookie)
        except ValueError:
            payload = None
    await logout_service(response=response, refresh_token=refresh_cookie, payload=payload)
    return {"ok": True}


@router.get("/me", response_model=MeOut)
async def me(user=Depends(get_current_user)) -> MeOut:
    return MeOut(id=user["id"], username=user["username"], role=user["role"], active=user["active"])


@router.post("/users", dependencies=[Depends(require_roles("admin"))])
async def create_user(payload: UserCreate, actor=Depends(get_current_user)) -> UserOut:
    db = get_db()
    now = now_utc()
    doc = {
        "username": payload.username,
        "password_hash": hash_password(payload.password),
        "role": payload.role.value,
        "active": payload.active,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.users.insert_one(doc)
    out = {
        "id": str(res.inserted_id),
        "username": payload.username,
        "role": payload.role.value,
        "active": payload.active,
        "created_at": now,
        "updated_at": now,
    }
    await log_audit(
        actor=actor,
        action="user_created",
        entity_type="user",
        entity_id=str(res.inserted_id),
        before=None,
        after={k: out[k] for k in out if k != "password_hash"},
    )
    return UserOut(**out)


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_roles("admin"))])
async def list_users() -> list[UserOut]:
    db = get_db()
    cur = db.users.find({}, projection={"password_hash": 0}).sort("username", 1)
    out: list[UserOut] = []
    async for d in cur:
        d["id"] = str(d.pop("_id"))
        out.append(UserOut(**d))
    return out


@router.post(
    "/users/{user_id}/set-password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Depends(require_roles("admin"))],
)
async def admin_set_password(user_id: str, payload: AdminSetPasswordIn, actor=Depends(get_current_user)) -> None:
    """Admin: establece una nueva contraseña para cualquier usuario."""
    db = get_db()
    user = await db.users.find_one({"_id": oid(user_id)})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    now = now_utc()
    await db.users.update_one(
        {"_id": oid(user_id)},
        {"$set": {"password_hash": hash_password(payload.new_password), "updated_at": now}},
    )
    await log_audit(
        actor=actor,
        action="user_password_set",
        entity_type="user",
        entity_id=user_id,
        after={"username": user.get("username")},
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def change_password(payload: ChangePasswordIn, user=Depends(get_current_user)) -> None:
    """Usuario autenticado: cambia su propia contraseña (requiere contraseña actual)."""
    db = get_db()
    doc = await db.users.find_one({"_id": oid(user["id"])}, projection={"password_hash": 1})
    if not doc or not verify_password(payload.current_password, doc.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contraseña actual incorrecta")
    now = now_utc()
    await db.users.update_one(
        {"_id": oid(user["id"])},
        {"$set": {"password_hash": hash_password(payload.new_password), "updated_at": now}},
    )
    await log_audit(
        actor=user,
        action="user_password_changed",
        entity_type="user",
        entity_id=user["id"],
    )

