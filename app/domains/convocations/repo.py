from __future__ import annotations

import secrets

from app.core.enums import AttendanceStatus
from app.db.ids import oid
from app.db.mongo import get_db, now_utc


def _link_id() -> str:
    # link corto para WhatsApp (~8 chars), suficiente entropía para convocatorias
    return secrets.token_urlsafe(6)


def _to_out(d: dict) -> dict:
    d = {**d}
    d["id"] = str(d.pop("_id"))
    d["match_id"] = str(d["match_id"])
    d["series_id"] = str(d["series_id"])
    d["invited_player_ids"] = [str(x) for x in d.get("invited_player_ids", [])]
    d["created_by_user_id"] = str(d["created_by_user_id"])
    return d


async def upsert_convocation(*, match_id: str, series_id: str, invited_player_ids: list[str], created_by_user_id: str) -> dict:
    db = get_db()
    now = now_utc()
    match_oid = oid(match_id)
    series_oid = oid(series_id)
    invited_oids = [oid(x) for x in invited_player_ids]

    existing = await db.convocations.find_one({"match_id": match_oid, "series_id": series_oid})
    if not existing:
        doc = {
            "match_id": match_oid,
            "series_id": series_oid,
            "invited_player_ids": invited_oids,
            "public_link_id": _link_id(),
            "created_by_user_id": oid(created_by_user_id),
            "created_at": now,
            "updated_at": now,
        }
        res = await db.convocations.insert_one(doc)
        created = await db.convocations.find_one({"_id": res.inserted_id})
        return _to_out(created)

    await db.convocations.update_one(
        {"_id": existing["_id"]},
        {
            "$set": {
                "invited_player_ids": invited_oids,
                "updated_at": now,
            }
        },
    )
    updated = await db.convocations.find_one({"_id": existing["_id"]})
    return _to_out(updated)


async def get_convocation(convocation_id: str) -> dict | None:
    db = get_db()
    d = await db.convocations.find_one({"_id": oid(convocation_id)})
    return _to_out(d) if d else None


async def get_convocation_by_match(*, match_id: str, series_id: str) -> dict | None:
    db = get_db()
    d = await db.convocations.find_one({"match_id": oid(match_id), "series_id": oid(series_id)})
    return _to_out(d) if d else None


async def get_convocation_by_public_link(public_link_id: str) -> dict | None:
    db = get_db()
    d = await db.convocations.find_one({"public_link_id": public_link_id})
    return _to_out(d) if d else None


async def set_attendance(
    *,
    convocation_id: str,
    match_id: str,
    series_id: str,
    player_id: str,
    status: AttendanceStatus,
    comment: str | None,
    origin: str,
    actor_user_id: str | None,
    meta: dict | None = None,
) -> dict:
    db = get_db()
    now = now_utc()
    conv_oid = oid(convocation_id)
    player_oid = oid(player_id)

    # current
    await db.attendance_current.update_one(
        {"convocation_id": conv_oid, "player_id": player_oid},
        {
            "$set": {
                "match_id": oid(match_id),
                "series_id": oid(series_id),
                "status": status.value,
                "comment": comment,
                "origin": origin,
                "actor_user_id": oid(actor_user_id) if actor_user_id else None,
                "updated_at": now,
                "created_at": now,
            }
        },
        upsert=True,
    )

    # event (append-only)
    await db.attendance_events.insert_one(
        {
            "match_id": oid(match_id),
            "series_id": oid(series_id),
            "convocation_id": conv_oid,
            "player_id": player_oid,
            "status": status.value,
            "comment": comment,
            "origin": origin,
            "actor_user_id": oid(actor_user_id) if actor_user_id else None,
            "meta": meta,
            "created_at": now,
            "updated_at": now,
        }
    )

    return {"ok": True}


async def get_attendance_status(*, convocation_id: str, invited_player_ids: list[str]) -> list[dict]:
    db = get_db()
    conv_oid = oid(convocation_id)
    invited_oids = [oid(x) for x in invited_player_ids]
    cur = db.attendance_current.find(
        {"convocation_id": conv_oid, "player_id": {"$in": invited_oids}},
        projection={"_id": 0},
    )
    out: list[dict] = []
    async for d in cur:
        d["player_id"] = str(d["player_id"])
        d["status"] = d.get("status", AttendanceStatus.pending.value)
        out.append(d)
    return out

