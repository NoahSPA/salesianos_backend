from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_roles
from app.domains.audit.service import log_audit
from app.domains.rivals.repo import create_rival, get_rival, list_rivals, update_rival
from app.domains.rivals.schemas import RivalCreate, RivalOut, RivalUpdate

router = APIRouter(prefix="/rivals", tags=["rivals"])


@router.get("", response_model=list[RivalOut], dependencies=[Depends(get_current_user)])
async def rivals_list(series_id: str | None = None, active: bool | None = None) -> list[RivalOut]:
    docs = await list_rivals(series_id=series_id, active=active)
    return [RivalOut(**d) for d in docs]


@router.post("", response_model=RivalOut, dependencies=[Depends(require_roles("admin"))])
async def rivals_create(payload: RivalCreate, actor=Depends(get_current_user)) -> RivalOut:
    doc = payload.model_dump()
    created = await create_rival(doc)
    await log_audit(
        actor=actor,
        action="rival_created",
        entity_type="rival",
        entity_id=created["id"],
        after=created,
    )
    return RivalOut(**created)


@router.get("/{rival_id}", response_model=RivalOut, dependencies=[Depends(get_current_user)])
async def rivals_get(rival_id: str) -> RivalOut:
    doc = await get_rival(rival_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    return RivalOut(**doc)


@router.patch("/{rival_id}", response_model=RivalOut, dependencies=[Depends(require_roles("admin"))])
async def rivals_patch(rival_id: str, payload: RivalUpdate, actor=Depends(get_current_user)) -> RivalOut:
    before = await get_rival(rival_id)
    if not before:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    patch = payload.model_dump(exclude_unset=True)
    after = await update_rival(rival_id, patch)
    await log_audit(
        actor=actor,
        action="rival_updated",
        entity_type="rival",
        entity_id=rival_id,
        before=before,
        after=after,
    )
    return RivalOut(**after)
