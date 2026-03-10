from __future__ import annotations

from datetime import date, datetime

from app.core.dates import date_to_utc_datetime, dt_to_date
from app.db.ids import oid
from app.db.mongo import get_db, now_utc


def _to_out(d: dict) -> dict:
    d = {**d}
    d["id"] = str(d.pop("_id"))
    d["tournament_id"] = str(d["tournament_id"])
    d["series_id"] = str(d["series_id"])
    if isinstance(d.get("match_date"), datetime):
        d["match_date"] = dt_to_date(d["match_date"])
    return d


async def create_match(doc: dict) -> dict:
    db = get_db()
    now = now_utc()
    if isinstance(doc.get("match_date"), date) and not isinstance(doc.get("match_date"), datetime):
        doc["match_date"] = date_to_utc_datetime(doc["match_date"])
    doc = {**doc, "created_at": now, "updated_at": now}
    res = await db.matches.insert_one(doc)
    created = await db.matches.find_one({"_id": res.inserted_id})
    return _to_out(created)


async def list_matches(*, series_id: str | None = None, tournament_id: str | None = None, from_date=None) -> list[dict]:
    """Lista todos los partidos. Sin límite. Filtros opcionales por query: series_id, tournament_id, from_date."""
    db = get_db()
    flt: dict = {}
    if series_id:
        flt["series_id"] = oid(series_id)
    if tournament_id:
        flt["tournament_id"] = oid(tournament_id)
    if from_date:
        flt["match_date"] = {"$gte": date_to_utc_datetime(from_date)}

    # Sin .limit(): se devuelven todos los partidos que cumplan el filtro
    cur = db.matches.find(flt).sort([("match_date", 1), ("call_time", 1)])
    out: list[dict] = []
    async for d in cur:
        out.append(_to_out(d))
    return out


async def get_match(match_id: str) -> dict | None:
    db = get_db()
    d = await db.matches.find_one({"_id": oid(match_id)})
    return _to_out(d) if d else None


async def update_match(match_id: str, patch: dict) -> dict | None:
    db = get_db()
    patch = {k: v for k, v in patch.items() if v is not None}
    if not patch:
        return await get_match(match_id)
    if "tournament_id" in patch:
        patch["tournament_id"] = oid(patch["tournament_id"])
    if "series_id" in patch:
        patch["series_id"] = oid(patch["series_id"])
    if "match_date" in patch and isinstance(patch["match_date"], date) and not isinstance(patch["match_date"], datetime):
        patch["match_date"] = date_to_utc_datetime(patch["match_date"])
    patch["updated_at"] = now_utc()
    await db.matches.update_one({"_id": oid(match_id)}, {"$set": patch})
    return await get_match(match_id)

