from __future__ import annotations

from pydantic import Field

from app.core.schemas import APIModel, DocOut


class RivalCreate(APIModel):
    name: str = Field(min_length=2, max_length=80)
    code: str | None = Field(default=None, max_length=20)
    series_ids: list[str] = Field(default_factory=list, description="Series en las que puede aparecer este rival")
    active: bool = True
    notes: str | None = Field(default=None, max_length=500)


class RivalUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    code: str | None = Field(default=None, max_length=20)
    series_ids: list[str] | None = None
    active: bool | None = None
    notes: str | None = Field(default=None, max_length=500)


class RivalOut(DocOut):
    name: str
    code: str | None = None
    series_ids: list[str]
    active: bool
    notes: str | None = None
