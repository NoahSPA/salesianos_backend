from __future__ import annotations

from datetime import date, datetime

from app.core.dates import date_to_utc_datetime, dt_to_date
from app.domains.players.schemas import (
    _normalize_level_stars_from_legacy,
    _normalize_positions_from_legacy,
    normalize_positions_for_output,
)
from app.db.ids import oid
from app.db.mongo import get_db, now_utc


def _to_out(d: dict) -> dict:
    d = {**d}
    d["id"] = str(d.pop("_id"))
    d["primary_series_id"] = str(d["primary_series_id"])
    d["series_ids"] = [str(x) for x in d.get("series_ids", [])]
    if isinstance(d.get("birth_date"), datetime):
        d["birth_date"] = dt_to_date(d["birth_date"])

    # Compat: posiciones/nivel nuevo, con fallback desde campos antiguos
    if "positions" not in d or not d.get("positions"):
        pos = _normalize_positions_from_legacy(d.get("position_primary"), d.get("position_secondary"))
        d["positions"] = [p.value for p in pos]
    else:
        d["positions"] = normalize_positions_for_output(d.get("positions", []))

    if "level_stars" not in d or d.get("level_stars") is None:
        d["level_stars"] = _normalize_level_stars_from_legacy(d.get("level"))
    else:
        try:
            d["level_stars"] = int(d["level_stars"])
        except Exception:
            d["level_stars"] = _normalize_level_stars_from_legacy(d.get("level"))

    # Legacy derivados (para compat/UI)
    if d.get("position_primary") is None and d.get("positions"):
        d["position_primary"] = d["positions"][0]
    if d.get("position_secondary") is None and d.get("positions") and len(d["positions"]) > 1:
        d["position_secondary"] = d["positions"][1]
    if d.get("level") is None and d.get("level_stars") is not None:
        d["level"] = str(d["level_stars"])
    if d.get("avatar_file_id") is not None:
        d["avatar_file_id"] = str(d["avatar_file_id"])
    # Campos opcionales (nómina): asegurar que existan para la API
    if "second_first_name" not in d:
        d["second_first_name"] = None
    if "second_last_name" not in d:
        d["second_last_name"] = None
    if "email" not in d:
        d["email"] = None
    return d


async def create_player(doc: dict) -> dict:
    db = get_db()
    now = now_utc()
    if isinstance(doc.get("birth_date"), date) and not isinstance(doc.get("birth_date"), datetime):
        doc["birth_date"] = date_to_utc_datetime(doc["birth_date"])
    doc = {**doc, "created_at": now, "updated_at": now}
    res = await db.players.insert_one(doc)
    created = await db.players.find_one({"_id": res.inserted_id})
    return _to_out(created)


async def list_players(*, active: bool | None = None, series_id: str | None = None, q: str | None = None) -> list[dict]:
    db = get_db()
    flt: dict = {}
    if active is not None:
        flt["active"] = active
    if series_id is not None:
        flt["series_ids"] = oid(series_id)
    if q:
        qn = q.strip().lower()
        if qn:
            flt["$or"] = [
                {"first_name": {"$regex": qn, "$options": "i"}},
                {"last_name": {"$regex": qn, "$options": "i"}},
                {"rut": {"$regex": qn, "$options": "i"}},
            ]
    cur = db.players.find(flt).sort([("active", -1), ("last_name", 1), ("first_name", 1)])
    out: list[dict] = []
    async for d in cur:
        out.append(_to_out(d))
    return out


async def get_player(player_id: str) -> dict | None:
    db = get_db()
    d = await db.players.find_one({"_id": oid(player_id)})
    return _to_out(d) if d else None


async def update_player(player_id: str, patch: dict) -> dict | None:
    db = get_db()
    patch = {k: v for k, v in patch.items() if v is not None}
    if not patch:
        return await get_player(player_id)

    if "primary_series_id" in patch:
        patch["primary_series_id"] = oid(patch["primary_series_id"])
    if "series_ids" in patch and patch["series_ids"] is not None:
        patch["series_ids"] = [oid(x) for x in patch["series_ids"]]
    if "birth_date" in patch and isinstance(patch["birth_date"], date) and not isinstance(patch["birth_date"], datetime):
        patch["birth_date"] = date_to_utc_datetime(patch["birth_date"])

    patch["updated_at"] = now_utc()
    await db.players.update_one({"_id": oid(player_id)}, {"$set": patch})
    return await get_player(player_id)


async def upsert_by_rut(*, rut: str, doc: dict) -> tuple[str, dict]:
    """
    Retorna (mode, player_out) donde mode ∈ {'inserted','updated'}.
    """
    db = get_db()
    existing = await db.players.find_one({"rut": rut})
    if not existing:
        out = await create_player(doc)
        return ("inserted", out)

    patch = {**doc}
    if isinstance(patch.get("birth_date"), date) and not isinstance(patch.get("birth_date"), datetime):
        patch["birth_date"] = date_to_utc_datetime(patch["birth_date"])
    patch.pop("created_at", None)
    patch["updated_at"] = now_utc()
    await db.players.update_one({"_id": existing["_id"]}, {"$set": patch})
    updated = await db.players.find_one({"_id": existing["_id"]})
    return ("updated", _to_out(updated))

