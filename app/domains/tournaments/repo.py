from __future__ import annotations

from datetime import date, datetime

from app.core.dates import date_to_utc_datetime, dt_to_date
from app.db.ids import oid
from app.db.mongo import get_db, now_utc


async def create_tournament(doc: dict) -> dict:
    db = get_db()
    now = now_utc()
    for k in ("start_date", "end_date"):
        if isinstance(doc.get(k), date) and not isinstance(doc.get(k), datetime):
            doc[k] = date_to_utc_datetime(doc[k])
    doc = {**doc, "created_at": now, "updated_at": now}
    res = await db.tournaments.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


async def list_tournaments(*, active: bool | None = None, season_year: int | None = None) -> list[dict]:
    db = get_db()
    q: dict = {}
    if active is not None:
        q["active"] = active
    if season_year is not None:
        q["season_year"] = season_year
    cur = db.tournaments.find(q).sort([("season_year", -1), ("name", 1)])
    out: list[dict] = []
    async for d in cur:
        d["id"] = str(d.pop("_id"))
        d["series_ids"] = [str(x) for x in d.get("series_ids", [])]
        if isinstance(d.get("start_date"), datetime):
            d["start_date"] = dt_to_date(d["start_date"])
        if isinstance(d.get("end_date"), datetime):
            d["end_date"] = dt_to_date(d["end_date"])
        out.append(d)
    return out


async def get_tournament(tournament_id: str) -> dict | None:
    db = get_db()
    d = await db.tournaments.find_one({"_id": oid(tournament_id)})
    if not d:
        return None
    d["id"] = str(d.pop("_id"))
    d["series_ids"] = [str(x) for x in d.get("series_ids", [])]
    if isinstance(d.get("start_date"), datetime):
        d["start_date"] = dt_to_date(d["start_date"])
    if isinstance(d.get("end_date"), datetime):
        d["end_date"] = dt_to_date(d["end_date"])
    return d


async def update_tournament(tournament_id: str, patch: dict) -> dict | None:
    db = get_db()
    if not patch:
        return await get_tournament(tournament_id)
    if "series_ids" in patch and patch["series_ids"] is not None:
        patch["series_ids"] = [oid(x) for x in patch["series_ids"]]
    for k in ("start_date", "end_date"):
        if isinstance(patch.get(k), date) and not isinstance(patch.get(k), datetime):
            patch[k] = date_to_utc_datetime(patch[k])
    patch["updated_at"] = now_utc()
    await db.tournaments.update_one({"_id": oid(tournament_id)}, {"$set": patch})
    return await get_tournament(tournament_id)

