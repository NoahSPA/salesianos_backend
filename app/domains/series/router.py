from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_roles
from app.db.ids import oid
from app.domains.audit.service import log_audit
from app.domains.series.repo import create_series, get_series, list_series, update_series
from app.domains.series.schemas import SeriesCreate, SeriesOut, SeriesUpdate

router = APIRouter(prefix="/series", tags=["series"])


@router.get("", response_model=list[SeriesOut], dependencies=[Depends(get_current_user)])
async def series_list(active: bool | None = None) -> list[SeriesOut]:
    docs = await list_series(active=active)
    return [SeriesOut(**d) for d in docs]


@router.post("", response_model=SeriesOut, dependencies=[Depends(require_roles("admin"))])
async def series_create(payload: SeriesCreate, actor=Depends(get_current_user)) -> SeriesOut:
    doc = payload.model_dump()

    # Validación: delegado/tesorero puede ser user o player (no ambos)
    if doc.get("delegate_user_id") and doc.get("delegate_player_id"):
        raise HTTPException(status_code=400, detail="Delegado: elige usuario o jugador (no ambos)")
    if doc.get("treasurer_user_id") and doc.get("treasurer_player_id"):
        raise HTTPException(status_code=400, detail="Tesorero: elige usuario o jugador (no ambos)")

    for k in ("delegate_user_id", "treasurer_user_id", "delegate_player_id", "treasurer_player_id"):
        if doc.get(k) is not None:
            doc[k] = oid(doc[k])
    created = await create_series(doc)
    out = await get_series(str(created["_id"]))
    await log_audit(
        actor=actor,
        action="series_created",
        entity_type="series",
        entity_id=str(created["_id"]),
        before=None,
        after=out,
    )
    return SeriesOut(**out)


@router.get("/{series_id}", response_model=SeriesOut, dependencies=[Depends(get_current_user)])
async def series_get(series_id: str) -> SeriesOut:
    doc = await get_series(series_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    return SeriesOut(**doc)


@router.patch("/{series_id}", response_model=SeriesOut, dependencies=[Depends(require_roles("admin"))])
async def series_patch(series_id: str, payload: SeriesUpdate, actor=Depends(get_current_user)) -> SeriesOut:
    before = await get_series(series_id)
    if not before:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    # exclude_unset permite diferenciar "no enviado" vs "enviado null" (para limpiar campos opcionales)
    patch = payload.model_dump(exclude_unset=True)

    # Normalización segura: si se setea user_id, limpia player_id y viceversa
    if "delegate_user_id" in patch and patch.get("delegate_user_id") is not None:
        patch["delegate_player_id"] = None
    if "delegate_player_id" in patch and patch.get("delegate_player_id") is not None:
        patch["delegate_user_id"] = None
    if "treasurer_user_id" in patch and patch.get("treasurer_user_id") is not None:
        patch["treasurer_player_id"] = None
    if "treasurer_player_id" in patch and patch.get("treasurer_player_id") is not None:
        patch["treasurer_user_id"] = None

    # Validación final (no ambos con valor)
    if patch.get("delegate_user_id") and patch.get("delegate_player_id"):
        raise HTTPException(status_code=400, detail="Delegado: elige usuario o jugador (no ambos)")
    if patch.get("treasurer_user_id") and patch.get("treasurer_player_id"):
        raise HTTPException(status_code=400, detail="Tesorero: elige usuario o jugador (no ambos)")

    after = await update_series(series_id, patch)
    if not after:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    await log_audit(
        actor=actor,
        action="series_updated",
        entity_type="series",
        entity_id=series_id,
        before=before,
        after=after,
    )
    return SeriesOut(**after)

