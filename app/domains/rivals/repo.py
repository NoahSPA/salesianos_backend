from __future__ import annotations

from app.db.ids import oid
from app.db.mongo import get_db, now_utc


def _to_out(d: dict) -> dict:
    d = {**d}
    d["id"] = str(d.pop("_id"))
    d["series_ids"] = [str(x) for x in d.get("series_ids", [])]
    return d


async def create_rival(doc: dict) -> dict:
    db = get_db()
    now = now_utc()
    doc = {**doc, "created_at": now, "updated_at": now}
    if doc.get("series_ids"):
        doc["series_ids"] = [oid(x) for x in doc["series_ids"]]
    else:
        doc["series_ids"] = []
    res = await db.rivals.insert_one(doc)
    created = await db.rivals.find_one({"_id": res.inserted_id})
    return _to_out(created)


async def list_rivals(*, series_id: str | None = None, active: bool | None = None) -> list[dict]:
    db = get_db()
    q: dict = {}
    if active is not None:
        q["active"] = active
    if series_id:
        q["series_ids"] = oid(series_id)
    cur = db.rivals.find(q).sort("name", 1)
    out: list[dict] = []
    async for d in cur:
        out.append(_to_out(d))
    return out


async def get_rival(rival_id: str) -> dict | None:
    db = get_db()
    d = await db.rivals.find_one({"_id": oid(rival_id)})
    return _to_out(d) if d else None


async def update_rival(rival_id: str, patch: dict) -> dict | None:
    db = get_db()
    if not patch:
        return await get_rival(rival_id)
    if "series_ids" in patch and patch["series_ids"] is not None:
        patch["series_ids"] = [oid(x) for x in patch["series_ids"]]
    patch["updated_at"] = now_utc()
    await db.rivals.update_one({"_id": oid(rival_id)}, {"$set": patch})
    return await get_rival(rival_id)
