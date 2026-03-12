"""API de configuración (branding): logo y color principal."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response

from app.api.deps import get_current_user, require_roles
from app.domains.settings.repo import get_branding, update_branding
from app.domains.settings.schemas import BrandingOut, BrandingUpdate
from app.storage.gridfs import get_avatar_file, upload_avatar
from app.storage.images import generate_app_icon, resize_for_og_image, resize_to_square_png

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/branding", response_model=BrandingOut)
async def settings_get_branding() -> BrandingOut:
    """Obtiene la configuración de marca (logo y color). Público para login y layout."""
    data = await get_branding()
    return BrandingOut(**data)


@router.patch("/branding", response_model=BrandingOut, dependencies=[Depends(require_roles("admin"))])
async def settings_patch_branding(payload: BrandingUpdate) -> BrandingOut:
    """Actualiza logo_url y/o primary_color. Solo admin."""
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        data = await get_branding()
        return BrandingOut(**data)
    data = await update_branding(updates)
    return BrandingOut(**data)


@router.post("/logo", response_model=BrandingOut, dependencies=[Depends(require_roles("admin"))])
async def settings_upload_logo(file: UploadFile) -> BrandingOut:
    """Sube el logo del sistema. Reemplaza el anterior. Solo admin."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Solo imágenes (JPEG, PNG, WebP)")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo vacío")
    content_type = file.content_type.split(";")[0].strip().lower()
    if content_type not in ("image/jpeg", "image/png", "image/webp"):
        content_type = "image/jpeg"
    file_id = await upload_avatar(content, content_type, "system_logo")
    data = await update_branding({"logo_file_id": file_id, "logo_url": None})
    return BrandingOut(**data)


@router.get("/logo")
async def settings_get_logo() -> Response:
    """Sirve el logo del sistema desde GridFS. Si no hay logo personalizado, 404."""
    data = await get_branding()
    file_id = data.get("logo_file_id")
    if not file_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay logo")
    result = await get_avatar_file(file_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo no encontrado")
    body, content_type = result
    return Response(content=body, media_type=content_type)


@router.get("/favicon")
async def settings_get_favicon(
    size: int = Query(32, ge=16, le=32),
) -> Response:
    """
    Sirve el logo del sistema redimensionado como favicon (16x16 o 32x32 PNG).
    Público. Si no hay logo en BD, 404 (el navegador usará el favicon estático).
    """
    data = await get_branding()
    file_id = data.get("logo_file_id")
    if not file_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay logo")
    result = await get_avatar_file(file_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo no encontrado")
    body, content_type = result
    try:
        png_bytes = resize_to_square_png(body, content_type, size)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al procesar imagen")
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "ETag": f'"{file_id}"',
        },
    )


@router.get("/og-image")
async def settings_get_og_image() -> Response:
    """
    Sirve el logo redimensionado para Open Graph / redes (512x512 JPEG).
    Público. Útil para og:image y twitter:image al compartir enlaces.
    """
    data = await get_branding()
    file_id = data.get("logo_file_id")
    if not file_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay logo")
    result = await get_avatar_file(file_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo no encontrado")
    body, content_type = result
    try:
        jpeg_bytes, media_type = resize_for_og_image(body, content_type, 512, 512)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al procesar imagen")
    return Response(
        content=jpeg_bytes,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "ETag": f'"{file_id}"',
        },
    )


@router.get("/app-icon")
async def settings_get_app_icon(
    size: int = Query(192, ge=64, le=1024),
) -> Response:
    """
    Sirve un ícono cuadrado PNG para la app:
    - fondo = primary_color de la marca
    - logo centrado ocupando ~80% del canvas

    Útil para iconos de PWA (launcher / app maskable).
    """
    data = await get_branding()
    file_id = data.get("logo_file_id")
    primary_color = data.get("primary_color") or "#006600"
    if not file_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay logo")
    result = await get_avatar_file(file_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo no encontrado")
    body, content_type = result
    try:
        png_bytes = generate_app_icon(body, content_type, size, primary_color)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al procesar imagen")
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "ETag": f'"{file_id}-{primary_color}"',
        },
    )


@router.get("/manifest.webmanifest")
async def settings_get_manifest() -> Response:
    """
    Manifest dinámico para PWA basado en la configuración de marca.
    Se puede usar desde el frontend con un <link rel="manifest"> apuntando a este endpoint.
    """
    data = await get_branding()
    app_name = (data.get("app_name") or "Salesianos FC").strip() or "Salesianos FC"
    primary = data.get("primary_color") or "#006600"
    file_id = data.get("logo_file_id")

    icons: list[dict] = []
    if file_id:
        for size in (192, 512):
            icons.append(
                {
                    "src": f"/api/settings/app-icon?size={size}&v={file_id}",
                    "sizes": f"{size}x{size}",
                    "type": "image/png",
                    "purpose": "any maskable",
                }
            )

    manifest = {
        "name": f"{app_name} — Gestión del equipo",
        "short_name": app_name,
        "description": "Gestión del equipo de fútbol amateur. Cuotas, convocatorias, partidos, jugadores y tesorería.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "theme_color": primary,
        "background_color": "#f1f5f9",
        "icons": icons,
    }
    body = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    return Response(
        content=body,
        media_type="application/manifest+json",
        headers={
            "Cache-Control": "public, max-age=3600",
        },
    )
