from __future__ import annotations

from app.db.ids import oid
from app.db.mongo import get_db, now_utc


async def _resolve_display_name(db, user_id: str | None, player_id: str | None) -> str | None:
    """Resuelve delegado/tesorero a nombre para mostrar (usuario o jugador)."""
    if user_id:
        try:
            u = await db.users.find_one({"_id": oid(user_id)}, projection={"username": 1, "role": 1})
            if u:
                return f"{u.get('username', '')} (usuario · {u.get('role', '')})"
        except (ValueError, TypeError):
            pass
    if player_id:
        try:
            p = await db.players.find_one({"_id": oid(player_id)}, projection={"first_name": 1, "last_name": 1})
            if p:
                return f"{p.get('first_name', '')} {p.get('last_name', '')} (jugador)"
        except (ValueError, TypeError):
            pass
    return None


def _enrich_series_display_names_sync(d: dict, delegate_name: str | None, treasurer_name: str | None) -> None:
    d["delegate_display_name"] = delegate_name
    d["treasurer_display_name"] = treasurer_name


async def create_series(doc: dict) -> dict:
    db = get_db()
    now = now_utc()
    doc = {
        **doc,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.series.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


async def list_series(*, active: bool | None = None) -> list[dict]:
    db = get_db()
    q: dict = {}
    if active is not None:
        q["active"] = active
    cur = db.series.find(q).sort("name", 1)
    out: list[dict] = []
    async for d in cur:
        d["id"] = str(d.pop("_id"))
        for k in ("delegate_user_id", "treasurer_user_id", "delegate_player_id", "treasurer_player_id"):
            if d.get(k) is not None:
                d[k] = str(d[k])
        delegate_name = await _resolve_display_name(
            db, d.get("delegate_user_id"), d.get("delegate_player_id")
        )
        treasurer_name = await _resolve_display_name(
            db, d.get("treasurer_user_id"), d.get("treasurer_player_id")
        )
        _enrich_series_display_names_sync(d, delegate_name, treasurer_name)
        out.append(d)
    return out


async def get_series(series_id: str) -> dict | None:
    db = get_db()
    try:
        d = await db.series.find_one({"_id": oid(series_id)})
    except (ValueError, TypeError):
        return None
    if not d:
        return None
    d["id"] = str(d.pop("_id"))
    for k in ("delegate_user_id", "treasurer_user_id", "delegate_player_id", "treasurer_player_id"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    delegate_name = await _resolve_display_name(
        db, d.get("delegate_user_id"), d.get("delegate_player_id")
    )
    treasurer_name = await _resolve_display_name(
        db, d.get("treasurer_user_id"), d.get("treasurer_player_id")
    )
    _enrich_series_display_names_sync(d, delegate_name, treasurer_name)
    return d


async def get_series_by_name(name: str) -> dict | None:
    """Busca una serie por nombre (insensible a mayúsculas)."""
    if not (name or "").strip():
        return None
    db = get_db()
    d = await db.series.find_one({"name": {"$regex": f"^{name.strip()}$", "$options": "i"}})
    if not d:
        return None
    d["id"] = str(d.pop("_id"))
    for k in ("delegate_user_id", "treasurer_user_id", "delegate_player_id", "treasurer_player_id"):
        if d.get(k) is not None:
            d[k] = str(d[k])
    delegate_name = await _resolve_display_name(
        db, d.get("delegate_user_id"), d.get("delegate_player_id")
    )
    treasurer_name = await _resolve_display_name(
        db, d.get("treasurer_user_id"), d.get("treasurer_player_id")
    )
    _enrich_series_display_names_sync(d, delegate_name, treasurer_name)
    return d


async def update_series(series_id: str, patch: dict) -> dict | None:
    db = get_db()
    if not patch:
        return await get_series(series_id)

    # ids opcionales
    for k in ("delegate_user_id", "treasurer_user_id", "delegate_player_id", "treasurer_player_id"):
        if k in patch and patch[k] is not None:
            patch[k] = oid(patch[k])

    patch["updated_at"] = now_utc()
    await db.series.update_one({"_id": oid(series_id)}, {"$set": patch})
    return await get_series(series_id)

