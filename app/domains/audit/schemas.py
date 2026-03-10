from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.core.schemas import APIModel, DocOut


class AuditLogOut(DocOut):
    action: str = Field(min_length=1, max_length=100)
    entity_type: str = Field(min_length=1, max_length=50)
    entity_id: str = Field(min_length=1, max_length=100)
    actor_user_id: str | None = None
    actor_role: str | None = None
    actor_username: str | None = None
    before: dict | None = None
    after: dict | None = None
    meta: dict | None = None


class AuditQuery(APIModel):
    entity_type: str | None = None
    entity_id: str | None = None
    action: str | None = None
    limit: int = Field(default=50, ge=1, le=200)

