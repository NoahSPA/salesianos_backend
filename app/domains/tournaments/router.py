from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_roles
from app.db.ids import oid
from app.domains.audit.service import log_audit
from app.domains.tournaments.repo import create_tournament, get_tournament, list_tournaments, update_tournament
from app.domains.tournaments.schemas import TournamentCreate, TournamentOut, TournamentUpdate

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


@router.get("", response_model=list[TournamentOut], dependencies=[Depends(get_current_user)])
async def tournaments_list(active: bool | None = None, season_year: int | None = None) -> list[TournamentOut]:
    docs = await list_tournaments(active=active, season_year=season_year)
    return [TournamentOut(**d) for d in docs]


@router.post("", response_model=TournamentOut, dependencies=[Depends(require_roles("admin"))])
async def tournaments_create(payload: TournamentCreate, actor=Depends(get_current_user)) -> TournamentOut:
    doc = payload.model_dump()
    doc["series_ids"] = [oid(x) for x in doc.get("series_ids", [])]
    doc["player_ids"] = [oid(x) for x in doc.get("player_ids", [])]
    created = await create_tournament(doc)
    out = await get_tournament(str(created["_id"]))
    await log_audit(
        actor=actor,
        action="tournament_created",
        entity_type="tournament",
        entity_id=str(created["_id"]),
        after=out,
    )
    return TournamentOut(**out)


@router.get("/{tournament_id}", response_model=TournamentOut, dependencies=[Depends(get_current_user)])
async def tournaments_get(tournament_id: str) -> TournamentOut:
    doc = await get_tournament(tournament_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    return TournamentOut(**doc)


@router.patch("/{tournament_id}", response_model=TournamentOut, dependencies=[Depends(require_roles("admin"))])
async def tournaments_patch(tournament_id: str, payload: TournamentUpdate, actor=Depends(get_current_user)) -> TournamentOut:
    before = await get_tournament(tournament_id)
    if not before:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    # exclude_unset evita limpiar campos no enviados; permite enviar null para limpiar campos opcionales
    after = await update_tournament(tournament_id, payload.model_dump(exclude_unset=True))
    await log_audit(
        actor=actor,
        action="tournament_updated",
        entity_type="tournament",
        entity_id=tournament_id,
        before=before,
        after=after,
    )
    return TournamentOut(**after)

