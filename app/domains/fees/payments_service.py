from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.dates import date_to_utc_datetime, next_year_month, parse_year_month
from app.core.enums import PaymentStatus
from app.db.ids import oid
from app.db.mongo import get_db, now_utc
from app.core.validators import normalize_rut
from app.domains.players.repo import get_player, get_player_by_rut
from app.domains.fees.service import ensure_charges_up_to_current, generate_monthly_charges


def _payment_doc_create(payload: dict, actor: dict, now) -> dict:
    """Construye el documento Payment para insert (alineado al modelo Club Treasury)."""
    amount_total = int(payload.get("amount_total") or payload.get("amount", 0))
    payment_date = payload.get("payment_date")
    if hasattr(payment_date, "isoformat"):
        payment_date = date_to_utc_datetime(payment_date)
    elif isinstance(payment_date, str):
        from datetime import datetime
        payment_date = datetime.fromisoformat(payment_date.replace("Z", "+00:00")) if payment_date else now
    else:
        payment_date = now

    doc = {
        "player_id": oid(payload["player_id"]),
        "payment_date": payment_date,
        "amount_total": amount_total,
        "payment_method": (payload.get("payment_method") or "transfer")[:30],
        "reference_number": (payload.get("reference_number") or payload.get("transfer_ref") or "")[:100],
        "notes": (payload.get("notes") or payload.get("notes_player") or "")[:500],
        "status": PaymentStatus.pending_validation.value,
        "created_by_user_id": oid(actor["id"]),
        "treasurer_user_id": None,
        "notes_treasurer": None,
        "target_month": payload.get("target_month"),
        "allocations_requested": None,
        "created_at": now,
        "updated_at": now,
    }
    if payload.get("allocations"):
        doc["allocations_requested"] = [
            {"fee_charge_id": str(a.get("fee_charge_id")), "amount": int(a.get("amount", 0))}
            for a in payload["allocations"]
        ]
    return doc


async def create_payment(*, actor: dict, payload: dict) -> dict:
    db = get_db()
    now = now_utc()
    amount_total = int(payload.get("amount_total") or payload.get("amount", 0))
    allocations = payload.get("allocations") or []

    if allocations:
        total_alloc = sum(int(a.get("amount", 0)) for a in allocations)
        if total_alloc > amount_total:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La suma de allocations no puede superar amount_total",
            )
        if total_alloc < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe haber al menos una allocation con amount > 0",
            )

    doc = _payment_doc_create(payload, actor, now)
    res = await db.payments.insert_one(doc)
    saved = await db.payments.find_one({"_id": res.inserted_id})
    player = await get_player(str(saved["player_id"]))
    name = f"{player['first_name']} {player['last_name']}" if player else None
    out = _payment_to_out(saved, player_name=name)
    out["allocations"] = []
    return out


async def create_self_register_payment(*, actor: dict, payload: dict) -> dict:
    """Registro de pago por jugador: busca por RUT y crea pago pendiente de validación."""
    rut = normalize_rut(payload.get("rut", ""))
    player = await get_player_by_rut(rut)
    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe un jugador activo con ese RUT",
        )
    payload_with_player = {**payload, "player_id": player["id"]}
    return await create_payment(actor=actor, payload=payload_with_player)


async def _allocations_for_payment(db, payment_id: str) -> list[dict]:
    """Devuelve las allocations de un pago (colección payment_allocations o legacy applied_to)."""
    pay = await db.payments.find_one({"_id": oid(payment_id)}, projection={"applied_to": 1, "_id": 0})
    if not pay:
        return []
    # Legacy: applied_to en el propio payment
    applied_to = pay.get("applied_to") or []
    if applied_to:
        return [
            {
                "id": "",
                "payment_id": payment_id,
                "fee_charge_id": a.get("charge_id"),
                "amount_applied": int(a.get("amount", 0)),
                "created_at": None,
            }
            for a in applied_to
        ]
    cur = db.payment_allocations.find({"payment_id": oid(payment_id)}).sort("created_at", 1)
    out = []
    async for a in cur:
        out.append({
            "id": str(a["_id"]),
            "payment_id": str(a["payment_id"]),
            "fee_charge_id": str(a["fee_charge_id"]),
            "amount_applied": int(a.get("amount_applied", 0)),
            "created_at": a["created_at"].isoformat() if a.get("created_at") and hasattr(a["created_at"], "isoformat") else None,
        })
    return out


def _payment_to_out(d: dict, player_name: str | None = None) -> dict:
    d = {**d}
    d["id"] = str(d.pop("_id"))
    d["player_id"] = str(d["player_id"])
    d["amount_total"] = int(d.get("amount_total") or d.get("amount", 0))
    d["amount"] = d["amount_total"]
    d["payment_date"] = d.get("payment_date")
    if d.get("payment_date") and hasattr(d["payment_date"], "isoformat"):
        d["payment_date"] = d["payment_date"].isoformat()
    d["payment_method"] = d.get("payment_method") or "transfer"
    d["reference_number"] = d.get("reference_number") or d.get("transfer_ref")
    d["notes"] = d.get("notes") or d.get("notes_player")
    d["treasurer_user_id"] = str(d["treasurer_user_id"]) if d.get("treasurer_user_id") else None
    if "created_by_user_id" in d and d["created_by_user_id"]:
        d["created_by_user_id"] = str(d["created_by_user_id"])
    if "created_at" in d and d["created_at"] and hasattr(d["created_at"], "isoformat"):
        d["created_at"] = d["created_at"].isoformat()
    if "updated_at" in d and d["updated_at"] and hasattr(d["updated_at"], "isoformat"):
        d["updated_at"] = d["updated_at"].isoformat()
    if player_name is not None:
        d["player_name"] = player_name
    d["receipt_file_id"] = str(d["receipt_file_id"]) if d.get("receipt_file_id") else None
    # allocations se rellenan después con _allocations_for_payment
    d["allocations"] = []
    # Quitar campos internos que PaymentOut no define (extra="forbid")
    d.pop("allocations_requested", None)
    d.pop("applied_to", None)
    d.pop("validated_by_user_id", None)
    d.pop("transfer_ref", None)
    d.pop("notes_player", None)
    return d


async def list_payments(*, status_filter: str | None = None, limit: int = 100) -> list[dict]:
    db = get_db()
    q: dict[str, Any] = {}
    if status_filter:
        q["status"] = status_filter
    cur = db.payments.find(q).sort("created_at", -1).limit(limit)
    out: list[dict] = []
    async for d in cur:
        player = await get_player(str(d["player_id"]))
        name = f"{player['first_name']} {player['last_name']}" if player else None
        row = _payment_to_out(d, player_name=name)
        row["allocations"] = await _allocations_for_payment(db, row["id"])
        out.append(row)
    return out


async def _apply_allocations_and_create_records(
    db,
    payment_id: str,
    player_id: str,
    allocations: list[dict],
    now,
) -> None:
    """
    Aplica montos a monthly_charges y crea documentos en payment_allocations.
    allocations = [{"fee_charge_id": str, "amount": int}]
    Regla: amount_applied no puede superar el saldo pendiente del cargo.
    """
    for item in allocations:
        charge_id = item.get("fee_charge_id")
        amount = int(item.get("amount", 0))
        if amount <= 0:
            continue
        ch = await db.monthly_charges.find_one({"_id": oid(charge_id), "player_id": oid(player_id)})
        if not ch:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cargo no encontrado o no pertenece al jugador: {charge_id}",
            )
        paid = int(ch.get("paid", 0))
        amt = int(ch.get("amount", 0))
        rem = amt - paid
        if rem <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El cargo {charge_id} ya está cubierto",
            )
        if amount > rem:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El monto asignado al cargo {charge_id} no puede superar el saldo pendiente ({rem})",
            )
        await db.monthly_charges.update_one(
            {"_id": ch["_id"]},
            {"$set": {"paid": paid + amount, "updated_at": now}},
        )
        await db.payment_allocations.insert_one({
            "payment_id": oid(payment_id),
            "fee_charge_id": oid(charge_id),
            "amount_applied": amount,
            "created_at": now,
        })


async def validate_payment(*, actor: dict, payment_id: str, notes_treasurer: str | None) -> dict:
    """Confirma el pago: aplica allocations (explícitas o automáticas) y crea registros en payment_allocations."""
    await ensure_charges_up_to_current()
    db = get_db()
    now = now_utc()
    pay = await db.payments.find_one({"_id": oid(payment_id)})
    if not pay:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    if pay.get("status") not in (PaymentStatus.pending_validation.value, "pending_validation"):
        raise HTTPException(status_code=409, detail="Pago no está pendiente de validación")

    player_id = str(pay["player_id"])
    amount_total = int(pay.get("amount_total") or pay.get("amount", 0))
    requested = pay.get("allocations_requested")

    if requested and len(requested) > 0:
        total_req = sum(int(a.get("amount", 0)) for a in requested)
        if total_req > amount_total:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La suma de allocations solicitadas supera el monto del pago",
            )
        await _apply_allocations_and_create_records(db, payment_id, player_id, requested, now)
        remaining_to_apply = amount_total - total_req
    else:
        # Asignación automática: target_month, luego pasados, luego futuros
        remaining_to_apply = amount_total
        target_month = pay.get("target_month")
        applied: list[dict] = []

        if target_month and remaining_to_apply > 0:
            target_ch = await db.monthly_charges.find_one({"player_id": oid(player_id), "year_month": target_month})
            if not target_ch:
                await generate_monthly_charges(year_month=target_month)
                target_ch = await db.monthly_charges.find_one({"player_id": oid(player_id), "year_month": target_month})
            if target_ch:
                paid = int(target_ch.get("paid", 0))
                amt = int(target_ch.get("amount", 0))
                rem = amt - paid
                if rem > 0:
                    use = min(rem, remaining_to_apply)
                    remaining_to_apply -= use
                    await db.monthly_charges.update_one(
                        {"_id": target_ch["_id"]},
                        {"$set": {"paid": paid + use, "updated_at": now}},
                    )
                    await db.payment_allocations.insert_one({
                        "payment_id": oid(payment_id),
                        "fee_charge_id": target_ch["_id"],
                        "amount_applied": use,
                        "created_at": now,
                    })
                    applied.append({"charge_id": str(target_ch["_id"]), "amount": use})

        charges_cur = db.monthly_charges.find({"player_id": oid(player_id)}).sort([("due_date", 1), ("year_month", 1)])
        async for ch in charges_cur:
            if remaining_to_apply <= 0:
                break
            if target_month and ch.get("year_month") == target_month:
                continue
            paid = int(ch.get("paid", 0))
            amt = int(ch.get("amount", 0))
            rem = amt - paid
            if rem <= 0:
                continue
            use = min(rem, remaining_to_apply)
            remaining_to_apply -= use
            await db.monthly_charges.update_one({"_id": ch["_id"]}, {"$set": {"paid": paid + use, "updated_at": now}})
            await db.payment_allocations.insert_one({
                "payment_id": oid(payment_id),
                "fee_charge_id": ch["_id"],
                "amount_applied": use,
                "created_at": now,
            })

        max_future_months = 24
        future_count = 0
        while remaining_to_apply > 0 and future_count < max_future_months:
            last_doc = await db.monthly_charges.find_one(
                {"player_id": oid(player_id)},
                sort=[("year_month", -1)],
                projection={"year_month": 1},
            )
            if not last_doc:
                break
            next_ym = next_year_month(parse_year_month(last_doc["year_month"]))
            next_ym_str = next_ym.key
            await generate_monthly_charges(year_month=next_ym_str)
            target_ch = await db.monthly_charges.find_one({"player_id": oid(player_id), "year_month": next_ym_str})
            if not target_ch:
                break
            paid = int(target_ch.get("paid", 0))
            amt = int(target_ch.get("amount", 0))
            rem = amt - paid
            if rem <= 0:
                future_count += 1
                continue
            use = min(rem, remaining_to_apply)
            remaining_to_apply -= use
            await db.monthly_charges.update_one(
                {"_id": target_ch["_id"]},
                {"$set": {"paid": paid + use, "updated_at": now}},
            )
            await db.payment_allocations.insert_one({
                "payment_id": oid(payment_id),
                "fee_charge_id": target_ch["_id"],
                "amount_applied": use,
                "created_at": now,
            })
            future_count += 1

        if remaining_to_apply > 0:
            await db.players.update_one(
                {"_id": oid(player_id)},
                {"$inc": {"credit_balance": remaining_to_apply}},
            )

    await db.payments.update_one(
        {"_id": oid(payment_id)},
        {
            "$set": {
                "status": PaymentStatus.confirmed.value,
                "notes_treasurer": notes_treasurer,
                "treasurer_user_id": oid(actor["id"]),
                "updated_at": now,
            }
        },
    )
    saved = await db.payments.find_one({"_id": oid(payment_id)})
    player = await get_player(str(saved["player_id"]))
    name = f"{player['first_name']} {player['last_name']}" if player else None
    out = _payment_to_out(saved, player_name=name)
    out["allocations"] = await _allocations_for_payment(db, payment_id)
    return out


async def reject_payment(*, actor: dict, payment_id: str, notes_treasurer: str | None) -> dict:
    db = get_db()
    pay = await db.payments.find_one({"_id": oid(payment_id)})
    if not pay:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    if pay.get("status") not in (PaymentStatus.pending_validation.value, "pending_validation"):
        raise HTTPException(status_code=409, detail="Pago no está pendiente")

    now = now_utc()
    await db.payments.update_one(
        {"_id": oid(payment_id)},
        {
            "$set": {
                "status": PaymentStatus.rejected.value,
                "notes_treasurer": notes_treasurer,
                "treasurer_user_id": oid(actor["id"]),
                "updated_at": now,
            }
        },
    )
    saved = await db.payments.find_one({"_id": oid(payment_id)})
    player = await get_player(str(saved["player_id"]))
    name = f"{player['first_name']} {player['last_name']}" if player else None
    out = _payment_to_out(saved, player_name=name)
    out["allocations"] = await _allocations_for_payment(db, payment_id)
    return out
