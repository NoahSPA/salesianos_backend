from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongo import get_db

# Únicos estados válidos. Borrador/publicado son dato sucio y se eliminan al arranque.
DEFAULT_MATCH_STATUSES: list[dict] = [
    {"code": "programado", "label": "Programado", "color_hex": "#64748b"},
    {"code": "jugado", "label": "Jugado", "color_hex": "#16a34a"},
    {"code": "suspendido", "label": "Suspendido", "color_hex": "#dc2626"},
    {"code": "reprogramado", "label": "Reprogramado", "color_hex": "#f59e0b"},
]

CODES_TO_REMOVE = ("borrador", "publicado")


async def ensure_match_statuses_seed(db: AsyncIOMotorDatabase) -> None:
    """Seed de los 4 estados válidos y limpieza de dato sucio (borrador, publicado)."""
    for doc in DEFAULT_MATCH_STATUSES:
        await db.match_statuses.update_one(
            {"code": doc["code"]},
            {"$set": {**doc}},
            upsert=True,
        )
    await db.match_statuses.delete_many({"code": {"$in": list(CODES_TO_REMOVE)}})
    await db.matches.update_many(
        {"status": {"$in": list(CODES_TO_REMOVE)}},
        {"$set": {"status": "programado"}},
    )


async def status_code_exists(code: str) -> bool:
    """True si existe un estado en BD con ese code (fuente de verdad)."""
    db = get_db()
    return await db.match_statuses.count_documents({"code": code}, limit=1) > 0


async def get_status_by_code(code: str) -> dict | None:
    """Devuelve el documento de status (code, label, color_hex) por código, o None."""
    db = get_db()
    doc = await db.match_statuses.find_one({"code": code}, projection={"_id": 0})
    return doc


async def get_status_map_by_codes() -> dict[str, dict]:
    """Devuelve un mapa code -> { code, label, color_hex } para todos los status. Útil para enriquecer listas de partidos."""
    db = get_db()
    cur = db.match_statuses.find({}, projection={"_id": 0})
    return {d["code"]: d async for d in cur}


async def list_match_statuses() -> list[dict]:
    """Lista todos los estados de partido (code, label, color_hex) ordenados por code."""
    db = get_db()
    cur = db.match_statuses.find({}, projection={"_id": 0}).sort("code", 1)
    return [doc async for doc in cur]
