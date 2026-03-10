from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DocOut(APIModel):
    id: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime

