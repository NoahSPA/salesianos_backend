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


def resize_to_square_png(
    data: bytes,
    content_type: str,
    size: int,
) -> bytes:
    """
    Redimensiona la imagen a un cuadrado de `size`x`size` píxeles y la devuelve como PNG.
    Mantiene transparencia si la imagen original es RGBA.
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        content_type = "image/png"
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as e:
        raise ValueError(f"No se pudo procesar la imagen: {e}") from e
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")
    img.thumbnail((size, size), Image.Resampling.LANCZOS)
    # Centrar en canvas size x size (por si la imagen no es cuadrada)
    out_img = Image.new(img.mode, (size, size), (255, 255, 255, 0) if img.mode == "RGBA" else (255, 255, 255))
    paste_x = (size - img.width) // 2
    paste_y = (size - img.height) // 2
    out_img.paste(img, (paste_x, paste_y))
    out = io.BytesIO()
    out_img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def resize_for_og_image(
    data: bytes,
    content_type: str,
    width: int = 512,
    height: int = 512,
) -> tuple[bytes, str]:
    """
    Redimensiona la imagen para uso en Open Graph / redes (cuadrado por defecto).
    Devuelve (bytes, content_type) en JPEG para menor peso.
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        content_type = "image/png"
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as e:
        raise ValueError(f"No se pudo procesar la imagen: {e}") from e
    img = img.convert("RGB")
    img.thumbnail((width, height), Image.Resampling.LANCZOS)
    out_img = Image.new("RGB", (width, height), (255, 255, 255))
    paste_x = (width - img.width) // 2
    paste_y = (height - img.height) // 2
    out_img.paste(img, (paste_x, paste_y))
    out = io.BytesIO()
    out_img.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue(), "image/jpeg"


def generate_app_icon(
    data: bytes,
    content_type: str,
    size: int,
    background_hex: str,
) -> bytes:
    """
    Genera un ícono cuadrado PNG de `size`x`size` con:
    - fondo = color de marca
    - logo centrado ocupando ~80% del lado.
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        content_type = "image/png"
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as e:
        raise ValueError(f"No se pudo procesar la imagen: {e}") from e

    img = img.convert("RGBA")

    # Escalar logo para que el lado mayor sea ~80% del canvas
    target = int(size * 0.8)
    if target <= 0:
        target = size
    scale = min(target / img.width, target / img.height, 1.0)
    new_w = max(1, int(img.width * scale))
    new_h = max(1, int(img.height * scale))
    if new_w != img.width or new_h != img.height:
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Color de fondo desde hex (#RRGGBB)
    hex_color = (background_hex or "#006600").strip()
    if hex_color.startswith("#"):
        hex_color = hex_color[1:]
    if len(hex_color) != 6:
        hex_color = "006600"
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
    except ValueError:
        r, g, b = 0, 102, 0

    bg = Image.new("RGB", (size, size), (r, g, b))
    paste_x = (size - img.width) // 2
    paste_y = (size - img.height) // 2
    bg.paste(img, (paste_x, paste_y), mask=img)

    out = io.BytesIO()
    bg.save(out, format="PNG", optimize=True)
    return out.getvalue()
