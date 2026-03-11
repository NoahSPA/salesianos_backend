"""Compresión de imágenes para avatares. Si supera el límite, redimensiona y reduce calidad."""

from __future__ import annotations

import io

from PIL import Image

# Límite por archivo para avatares: 1.5 MB (GridFS permite 16MB, dejamos margen)
AVATAR_MAX_BYTES = 1_500_000
# Tamaño máximo de imagen en píxeles (para avatares, 512x512 es suficiente)
AVATAR_MAX_SIZE = 512
# Formatos de imagen soportados
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def compress_image_to_limit(
    data: bytes,
    content_type: str,
    max_bytes: int = AVATAR_MAX_BYTES,
    max_size: int = AVATAR_MAX_SIZE,
) -> tuple[bytes, str]:
    """
    Comprime la imagen para que no supere max_bytes.
    Redimensiona si es necesario y reduce calidad JPEG.
    Devuelve (bytes, content_type).
    """
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as e:
        raise ValueError(f"No se pudo procesar la imagen: {e}") from e
    # Redimensionar si es muy grande
    if img.width > max_size or img.height > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    quality = 85
    fmt = "JPEG"
    mime = "image/jpeg"
    while quality >= 20:
        out.seek(0)
        out.truncate()
        img.save(out, format=fmt, quality=quality, optimize=True)
        if out.tell() <= max_bytes:
            return out.getvalue(), mime
        quality -= 10
    # Último intento: redimensionar más
    if img.width > 256 or img.height > 256:
        img.thumbnail((256, 256), Image.Resampling.LANCZOS)
        out.seek(0)
        out.truncate()
        img.save(out, format=fmt, quality=70, optimize=True)
    return out.getvalue(), mime
