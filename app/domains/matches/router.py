from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_roles
from app.db.ids import oid
from app.domains.audit.service import log_audit
from app.domains.matches.repo import create_match, get_match, list_matches, update_match
from app.domains.matches.schemas import MatchCreate, MatchOut, MatchUpdate

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("", response_model=list[MatchOut], dependencies=[Depends(get_current_user)])
async def matches_list(series_id: str | None = None, tournament_id: str | None = None, from_date: date | None = None) -> list[MatchOut]:
    docs = await list_matches(series_id=series_id, tournament_id=tournament_id, from_date=from_date)
    return [MatchOut(**d) for d in docs]


@router.post("", response_model=MatchOut, dependencies=[Depends(require_roles("admin", "delegado"))])
async def matches_create(payload: MatchCreate, actor=Depends(get_current_user)) -> MatchOut:
    doc = payload.model_dump()
    doc["tournament_id"] = oid(doc["tournament_id"])
    doc["series_id"] = oid(doc["series_id"])
    created = await create_match(doc)
    await log_audit(actor=actor, action="match_created", entity_type="match", entity_id=created["id"], after=created)
    return MatchOut(**created)


@router.get("/{match_id}", response_model=MatchOut, dependencies=[Depends(get_current_user)])
async def matches_get(match_id: str) -> MatchOut:
    doc = await get_match(match_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    return MatchOut(**doc)


@router.patch("/{match_id}", response_model=MatchOut, dependencies=[Depends(require_roles("admin", "delegado"))])
async def matches_patch(match_id: str, payload: MatchUpdate, actor=Depends(get_current_user)) -> MatchOut:
    before = await get_match(match_id)
    if not before:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    after = await update_match(match_id, payload.model_dump())
    await log_audit(actor=actor, action="match_updated", entity_type="match", entity_id=match_id, before=before, after=after)
    return MatchOut(**after)

