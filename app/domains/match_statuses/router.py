from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.domains.match_statuses.repo import list_match_statuses
from app.domains.match_statuses.schemas import MatchStatusOut

router = APIRouter(prefix="/match-statuses", tags=["match-statuses"])


@router.get("", response_model=list[MatchStatusOut], dependencies=[Depends(get_current_user)])
async def match_statuses_list() -> list[MatchStatusOut]:
    """Lista estados de partido con código, etiqueta y color hex para badges."""
    docs = await list_match_statuses()
    return [MatchStatusOut(**d) for d in docs]
