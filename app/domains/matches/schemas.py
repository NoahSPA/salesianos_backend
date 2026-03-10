from __future__ import annotations

from datetime import date

from pydantic import Field

from app.core.enums import MatchStatus
from app.core.schemas import APIModel, DocOut


class MatchCreate(APIModel):
    tournament_id: str
    series_id: str
    opponent: str = Field(min_length=1, max_length=80)
    match_date: date
    call_time: str = Field(min_length=4, max_length=10)  # HH:MM
    venue: str = Field(default="", max_length=120)
    field_number: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=500)
    status: MatchStatus = MatchStatus.programado


class MatchUpdate(APIModel):
    tournament_id: str | None = None
    series_id: str | None = None
    opponent: str | None = Field(default=None, min_length=1, max_length=80)
    match_date: date | None = None
    call_time: str | None = Field(default=None, min_length=4, max_length=10)
    venue: str | None = Field(default=None, max_length=120)
    field_number: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=500)
    status: MatchStatus | None = None

    result: str | None = Field(default=None, max_length=50)
    our_goals: int | None = Field(default=None, ge=0, le=99)
    opponent_goals: int | None = Field(default=None, ge=0, le=99)
    story: str | None = Field(default=None, max_length=5000)
    story_author: str | None = Field(default=None, max_length=80)


class MatchOut(DocOut):
    tournament_id: str
    series_id: str
    opponent: str
    match_date: date
    call_time: str
    venue: str
    field_number: str | None = None
    notes: str | None = None
    status: MatchStatus

    result: str | None = None
    our_goals: int | None = None
    opponent_goals: int | None = None
    story: str | None = None
    story_author: str | None = None

