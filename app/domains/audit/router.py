from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_roles
from app.domains.audit.schemas import AuditLogOut
from app.domains.audit.service import query_audit

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogOut], dependencies=[Depends(require_roles("admin"))])
async def list_audit(
    entity_type: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    limit: int = 50,
) -> list[AuditLogOut]:
    filters: dict = {}
    if entity_type:
        filters["entity_type"] = entity_type
    if entity_id:
        filters["entity_id"] = entity_id
    if action:
        filters["action"] = action
    docs = await query_audit(filters=filters, limit=limit)
    return [AuditLogOut(**d) for d in docs]

