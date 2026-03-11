"""Almacenamiento de archivos en MongoDB GridFS."""

from __future__ import annotations

import io
from bson import ObjectId

from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from app.db.mongo import get_db
from app.storage.images import (
    AVATAR_MAX_BYTES,
    ALLOWED_CONTENT_TYPES,
    compress_image_to_limit,
)

AVATAR_BUCKET = "avatars"


def _get_bucket() -> AsyncIOMotorGridFSBucket:
    """Obtiene el bucket GridFS de avatares."""
    db = get_db()
    return AsyncIOMotorGridFSBucket(db, bucket_name=AVATAR_BUCKET)


async def upload_avatar(
    data: bytes,
    content_type: str,
    filename: str = "avatar",
) -> str:
    """
    Sube una imagen como avatar. Si supera el límite, la comprime.
    Devuelve el file_id (ObjectId) como string.
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f"Tipo no soportado: {content_type}. Use: jpeg, png, webp")
    if len(data) > AVATAR_MAX_BYTES:
        data, content_type = compress_image_to_limit(data, content_type)
    bucket = _get_bucket()
    file_id = await bucket.upload_from_stream(
        filename,
        io.BytesIO(data),
        metadata={"contentType": content_type},
    )
    return str(file_id)


async def get_avatar_file(file_id: str) -> tuple[bytes, str] | None:
    """Obtiene el archivo de avatar por ID. Devuelve (bytes, content_type) o None."""
    bucket = _get_bucket()
    try:
        stream = await bucket.open_download_stream(ObjectId(file_id))
        data = await stream.read()
        meta = stream.metadata or {}
        content_type = meta.get("contentType") or getattr(stream, "content_type", None) or "image/jpeg"
        return data, str(content_type) if content_type else "image/jpeg"
    except Exception:
        return None


async def delete_avatar_file(file_id: str) -> bool:
    """Elimina un archivo de avatar por ID. Devuelve True si se eliminó."""
    bucket = _get_bucket()
    try:
        await bucket.delete(ObjectId(file_id))
        return True
    except Exception:
        return False
