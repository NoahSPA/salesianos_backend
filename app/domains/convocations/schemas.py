from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.core.enums import AttendanceStatus
from app.core.schemas import APIModel, DocOut


class ConvocationUpsert(APIModel):
    invited_player_ids: list[str] = Field(default_factory=list)


class ConvocationOut(DocOut):
    match_id: str
    series_id: str
    invited_player_ids: list[str]
    public_link_id: str
    created_by_user_id: str


class AttendanceRespondPublic(APIModel):
    rut: str = Field(min_length=7, max_length=15)
    birth_date: str = Field(min_length=10, max_length=10)  # YYYY-MM-DD
    status: AttendanceStatus
    comment: str | None = Field(default=None, max_length=300)


class AttendanceOverride(APIModel):
    player_id: str
    status: AttendanceStatus
    comment: str | None = Field(default=None, max_length=300)
    reason: str | None = Field(default=None, max_length=300)


class AttendanceLine(APIModel):
    player_id: str
    player_name: str
    status: AttendanceStatus
    comment: str | None = None
    updated_at: datetime


class ConvocationStatusOut(APIModel):
    convocation_id: str
    match_id: str
    series_id: str
    public_link_id: str
    invited_count: int
    confirmed_count: int
    declined_count: int
    pending_count: int
    lines: list[AttendanceLine]


class PublicConvocationInfo(APIModel):
    public_link_id: str
    series_name: str
    opponent: str
    match_date: str
    call_time: str
    venue: str
    field_number: str | None = None

