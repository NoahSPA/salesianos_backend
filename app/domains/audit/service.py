from __future__ import annotations

from datetime import date, datetime
from typing import Any

from bson import ObjectId

from app.db.mongo import get_db, now_utc


def _sanitize(value: Any) -> Any:
    # Mongo/PyMongo no soporta datetime.date en documentos; además normalizamos ObjectId.
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    return value


async def log_audit(
    *,
    actor: dict | None,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict | None = None,
    after: dict | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    db = get_db()
    now = now_utc()
    doc = {
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "actor_user_id": actor.get("id") if actor else None,
        "actor_role": actor.get("role") if actor else None,
        "actor_username": actor.get("username") if actor else None,
        "before": _sanitize(before),
        "after": _sanitize(after),
        "meta": _sanitize(meta),
        "created_at": now,
        "updated_at": now,
    }
    await db.audit_logs.insert_one(doc)


async def query_audit(*, filters: dict, limit: int) -> list[dict]:
    db = get_db()
    cur = db.audit_logs.find(filters).sort("created_at", -1).limit(limit)
    out: list[dict] = []
    async for doc in cur:
        doc["id"] = str(doc.pop("_id"))
        out.append(doc)
    return out

