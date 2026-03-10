from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, require_roles
from app.domains.audit.service import log_audit
from app.domains.fees.payments_schemas import PaymentCreate, PaymentOut, PaymentRejectIn, PaymentValidateIn
from app.domains.fees.payments_service import create_payment, list_payments, reject_payment, validate_payment

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("", response_model=list[PaymentOut], dependencies=[Depends(require_roles("admin", "tesorero"))])
async def payments_list(status: str | None = None, limit: int = 100) -> list[PaymentOut]:
    docs = await list_payments(status_filter=status, limit=min(max(limit, 1), 200))
    return [PaymentOut(**d) for d in docs]


@router.post("", response_model=PaymentOut, dependencies=[Depends(require_roles("admin", "tesorero"))])
async def payments_create(payload: PaymentCreate, actor=Depends(get_current_user)) -> PaymentOut:
    created = await create_payment(actor=actor, payload=payload.model_dump())
    await log_audit(actor=actor, action="payment_created", entity_type="payment", entity_id=created["id"], after=created)
    return PaymentOut(**created)


@router.post("/{payment_id}/validate", response_model=PaymentOut, dependencies=[Depends(require_roles("admin", "tesorero"))])
async def payments_validate(payment_id: str, payload: PaymentValidateIn, actor=Depends(get_current_user)) -> PaymentOut:
    out = await validate_payment(actor=actor, payment_id=payment_id, notes_treasurer=payload.notes_treasurer)
    await log_audit(actor=actor, action="payment_validated", entity_type="payment", entity_id=payment_id, after=out)
    return PaymentOut(**out)


@router.post("/{payment_id}/reject", response_model=PaymentOut, dependencies=[Depends(require_roles("admin", "tesorero"))])
async def payments_reject(payment_id: str, payload: PaymentRejectIn, actor=Depends(get_current_user)) -> PaymentOut:
    out = await reject_payment(actor=actor, payment_id=payment_id, notes_treasurer=payload.notes_treasurer)
    await log_audit(actor=actor, action="payment_rejected", entity_type="payment", entity_id=payment_id, after=out)
    return PaymentOut(**out)

