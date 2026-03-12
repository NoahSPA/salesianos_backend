"""Repositorio de configuración (branding)."""

from __future__ import annotations

from bson import ObjectId

from app.db.mongo import get_db

BRANDING_ID = "branding"
DEFAULT_PRIMARY = "#006600"
DEFAULT_APP_NAME = "Salesianos FC"


async def get_branding() -> dict:
    """Obtiene la configuración de marca. Si no existe, devuelve valores por defecto."""
    db = get_db()
    doc = await db.settings.find_one({"_id": BRANDING_ID})
    if not doc:
        return {"logo_file_id": None, "logo_url": None, "primary_color": DEFAULT_PRIMARY, "app_name": DEFAULT_APP_NAME}
    out = {
        "logo_file_id": str(doc["logo_file_id"]) if doc.get("logo_file_id") else None,
        "logo_url": (doc.get("logo_url") or "").strip() or None,
        "primary_color": doc.get("primary_color") or DEFAULT_PRIMARY,
        "app_name": (doc.get("app_name") or "").strip() or DEFAULT_APP_NAME,
    }
    return out


async def update_branding(updates: dict) -> dict:
    """Actualiza branding. updates puede contener logo_url, primary_color, logo_file_id, app_name."""
    db = get_db()
    set_fields = {}
    if "logo_url" in updates:
        set_fields["logo_url"] = (updates["logo_url"] or "").strip() or None
    if "primary_color" in updates and updates["primary_color"]:
        set_fields["primary_color"] = updates["primary_color"]
    if "logo_file_id" in updates:
        set_fields["logo_file_id"] = ObjectId(updates["logo_file_id"]) if updates["logo_file_id"] else None
    if "app_name" in updates and updates["app_name"] is not None:
        set_fields["app_name"] = (updates["app_name"] or "").strip() or DEFAULT_APP_NAME
    if not set_fields:
        return await get_branding()
    await db.settings.update_one(
        {"_id": BRANDING_ID},
        {"$set": set_fields},
        upsert=True,
    )
    return await get_branding()
