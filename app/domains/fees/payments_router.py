from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response

from app.api.deps import get_current_user, require_roles
from app.db.ids import oid
from app.db.mongo import get_db
from app.domains.audit.service import log_audit
from app.domains.fees.payments_schemas import (
    PaymentCreate,
    PaymentOut,
    PaymentRejectIn,
    PaymentSelfRegisterIn,
    PaymentValidateIn,
)
from app.domains.fees.payments_service import (
    create_payment,
    create_self_register_payment,
    list_payments,
    reject_payment,
    validate_payment,
)
from app.storage.gridfs import RECEIPT_CONTENT_TYPES, get_receipt_file, upload_receipt

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("", response_model=list[PaymentOut], dependencies=[Depends(require_roles("admin", "tesorero"))])
async def payments_list(
    status: str | None = None,
    series_id: str | None = None,
    tournament_id: str | None = None,
    limit: int = 100,
) -> list[PaymentOut]:
    docs = await list_payments(
        status_filter=status,
        series_id=series_id,
        tournament_id=tournament_id,
        limit=min(max(limit, 1), 500),
    )
    return [PaymentOut(**d) for d in docs]


@router.post("/self-register", response_model=PaymentOut, dependencies=[Depends(get_current_user)])
async def payments_self_register(payload: PaymentSelfRegisterIn, actor=Depends(get_current_user)) -> PaymentOut:
    """Registro de pago por jugador: identificación por RUT, queda pendiente de validación."""
    from fastapi import HTTPException, status

    try:
        created = await create_self_register_payment(actor=actor, payload=payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await log_audit(
        actor=actor,
        action="payment_self_registered",
        entity_type="payment",
        entity_id=created["id"],
        after=created,
    )
    return PaymentOut(**created)


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


@router.post(
    "/{payment_id}/receipt",
    response_model=PaymentOut,
    dependencies=[Depends(get_current_user)],
)
async def payments_upload_receipt(
    payment_id: str,
    file: UploadFile = File(...),
    actor=Depends(get_current_user),
) -> PaymentOut:
    """Adjunta comprobante de pago (imagen o PDF). Solo el creador o admin/tesorero."""
    from fastapi import HTTPException, status

    from app.db.mongo import now_utc

    db = get_db()
    pay = await db.payments.find_one({"_id": oid(payment_id)})
    if not pay:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    # Solo el creador o admin/tesorero
    created_by = str(pay.get("created_by_user_id", ""))
    if created_by != actor["id"] and actor.get("role") not in ("admin", "tesorero"):
        raise HTTPException(status_code=403, detail="Sin permiso para subir comprobante a este pago")
    if pay.get("status") not in ("pending_validation",):
        raise HTTPException(status_code=400, detail="Solo se puede adjuntar comprobante a pagos pendientes")

    ct = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if ct not in RECEIPT_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Formato no soportado. Use imagen (jpeg, png, webp, gif) o PDF.",
        )
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Archivo demasiado grande (máx 8 MB)")
    file_id = await upload_receipt(raw, ct, filename=file.filename or "comprobante")
    now = now_utc()
    await db.payments.update_one(
        {"_id": oid(payment_id)},
        {"$set": {"receipt_file_id": oid(file_id), "updated_at": now}},
    )
    from app.domains.fees.payments_service import _allocations_for_payment, _payment_to_out
    from app.domains.players.repo import get_player
    from app.domains.tournaments.repo import get_tournament

    saved = await db.payments.find_one({"_id": oid(payment_id)})
    player = await get_player(str(saved["player_id"]))
    name = f"{player['first_name']} {player['last_name']}" if player else None
    tid = saved.get("tournament_id")
    t = await get_tournament(str(tid)) if tid else None
    tname = t.get("name") if t else None
    out = _payment_to_out(saved, player_name=name, tournament_name=tname)
    out["allocations"] = await _allocations_for_payment(db, payment_id)
    return PaymentOut(**out)


@router.get(
    "/{payment_id}/receipt",
    dependencies=[Depends(require_roles("admin", "tesorero"))],
)
async def payments_get_receipt(payment_id: str) -> Response:
    """Descarga el comprobante del pago. Solo tesorero/admin."""
    from fastapi import HTTPException, status

    db = get_db()
    pay = await db.payments.find_one({"_id": oid(payment_id)})
    if not pay:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    fid = pay.get("receipt_file_id")
    if not fid:
        raise HTTPException(status_code=404, detail="Este pago no tiene comprobante adjunto")
    result = await get_receipt_file(str(fid))
    if not result:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")
    data, content_type = result
    return Response(content=data, media_type=content_type)

