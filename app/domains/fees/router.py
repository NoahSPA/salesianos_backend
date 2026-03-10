from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_current_user, require_roles
from app.core.dates import date_to_utc_datetime, last_day_of_month, parse_year_month
from app.core.enums import FeeStatus
from app.db.ids import oid
from app.domains.audit.service import log_audit
from app.domains.fees.repo import _charge_to_out, create_fee_rule, delete_fee_rule, get_fee_rule, get_collection_breakdown, get_fees_summary_by_period, get_fees_totals, get_player_period_matrix, get_players_contribution, list_charges_for_player, list_charges_for_players_up_to, list_fee_rules, update_fee_rule, get_unpaid_periods_for_tournament
from app.domains.fees.schemas import FeeRuleCreate, FeeRuleOut, FeeRuleUpdate, GenerateMonthResult, MonthlyChargeOut, PlayerFeeStatusOut
from app.domains.fees.service import compute_fee_status_for_player, ensure_charges_for_tournament_periods, ensure_charges_up_to_current, generate_monthly_charges, resolve_fee_amount_for_player
from app.domains.players.repo import get_player, list_players

router = APIRouter(prefix="/fees", tags=["fees"])


@router.get("/rules", response_model=list[FeeRuleOut], dependencies=[Depends(require_roles("admin", "tesorero"))])
async def fee_rules_list(scope: str | None = None, scope_id: str | None = None, active: bool | None = None) -> list[FeeRuleOut]:
    docs = await list_fee_rules(scope=scope, scope_id=scope_id, active=active)
    return [FeeRuleOut(**d) for d in docs]


@router.post("/rules", response_model=FeeRuleOut, dependencies=[Depends(require_roles("admin", "tesorero"))])
async def fee_rules_create(payload: FeeRuleCreate, actor=Depends(get_current_user)) -> FeeRuleOut:
    data = payload.model_dump()
    # Mongo: fechas como datetime UTC
    data["effective_from"] = date_to_utc_datetime(data["effective_from"])
    if data.get("effective_to") is not None:
        data["effective_to"] = date_to_utc_datetime(data["effective_to"])
    if data["scope"] == "general":
        data["scope_id"] = None
    else:
        if not data.get("scope_id"):
            raise HTTPException(status_code=400, detail="scope_id requerido")
        data["scope_id"] = oid(data["scope_id"])
    created = await create_fee_rule(data)
    await log_audit(actor=actor, action="fee_rule_created", entity_type="fee_rule", entity_id=created["id"], after=created)
    return FeeRuleOut(**created)


@router.patch("/rules/{rule_id}", response_model=FeeRuleOut, dependencies=[Depends(require_roles("admin", "tesorero"))])
async def fee_rules_patch(rule_id: str, payload: FeeRuleUpdate, actor=Depends(get_current_user)) -> FeeRuleOut:
    before = await get_fee_rule(rule_id)
    if not before:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    patch = payload.model_dump()
    if patch.get("effective_from") is not None:
        patch["effective_from"] = date_to_utc_datetime(patch["effective_from"])
    if patch.get("effective_to") is not None:
        patch["effective_to"] = date_to_utc_datetime(patch["effective_to"])
    after = await update_fee_rule(rule_id, patch)
    await log_audit(actor=actor, action="fee_rule_updated", entity_type="fee_rule", entity_id=rule_id, before=before, after=after)
    return FeeRuleOut(**after)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles("admin", "tesorero"))])
async def fee_rules_delete(rule_id: str, actor=Depends(get_current_user)) -> Response:
    before = await get_fee_rule(rule_id)
    if not before:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    deleted = await delete_fee_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    await log_audit(actor=actor, action="fee_rule_deleted", entity_type="fee_rule", entity_id=rule_id, before=before)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/generate-month", response_model=GenerateMonthResult, dependencies=[Depends(require_roles("admin", "tesorero"))])
async def fees_generate_month(yearMonth: str, actor=Depends(get_current_user)) -> GenerateMonthResult:
    result = await generate_monthly_charges(year_month=yearMonth)
    await log_audit(actor=actor, action="fees_generated_month", entity_type="fees", entity_id=yearMonth, after=result)
    return GenerateMonthResult(**result)


@router.get("/player-period-matrix", dependencies=[Depends(require_roles("admin", "tesorero", "delegado"))])
async def fees_player_period_matrix(series_id: str | None = None) -> dict:
    """Matriz jugador vs períodos con estado de cuota (pagado/pendiente) por mes. Incluye cuotas adelantadas."""
    await ensure_charges_up_to_current()
    return await get_player_period_matrix(series_id=series_id)


@router.get("/summary-by-period", dependencies=[Depends(require_roles("admin", "tesorero", "delegado"))])
async def fees_summary_by_period(series_id: str | None = None) -> dict:
    """Resumen por período + totales + desglose de recaudación por serie/torneo/jugador. Opcional: filtrar por series_id."""
    await ensure_charges_up_to_current()
    await ensure_charges_for_tournament_periods()
    today = date.today()
    current_ym = f"{today.year:04d}-{today.month:02d}"
    periods = await get_fees_summary_by_period(current_year_month=current_ym, series_id=series_id)
    total_collected, total_pending = await get_fees_totals(current_year_month=current_ym, series_id=series_id)
    collection_breakdown = await get_collection_breakdown(series_id=series_id)
    return {
        "periods": periods,
        "total_collected": total_collected,
        "total_pending": total_pending,
        "collection_by_series": collection_breakdown["by_series"],
        "collection_by_tournament": collection_breakdown["by_tournament"],
        "collection_by_player": collection_breakdown["by_player"],
    }


@router.get("/unpaid-periods", dependencies=[Depends(require_roles("admin", "tesorero", "delegado"))])
async def fees_unpaid_periods(tournament_id: str) -> dict:
    """Periodos (meses) no pagados por jugador para un torneo con período de cuotas definido."""
    result = await get_unpaid_periods_for_tournament(tournament_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Torneo no encontrado")
    return result


@router.get("/player-fee", dependencies=[Depends(require_roles("admin", "tesorero", "delegado"))])
async def fees_player_fee(player_id: str, year_month: str) -> dict:
    """Retorna la cuota mensual de un jugador para un mes dado según las reglas activas."""
    p = await get_player(player_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jugador no encontrado")
    ym = parse_year_month(year_month)
    fee_amount, fee_source = await resolve_fee_amount_for_player(
        player={"id": p["id"], "primary_series_id": p["primary_series_id"]}, ym=ym
    )
    return {"fee_amount": fee_amount, "fee_source": fee_source}


@router.get("/players/{player_id}", response_model=list[MonthlyChargeOut], dependencies=[Depends(require_roles("admin", "tesorero"))])
async def fees_player_detail(player_id: str) -> list[MonthlyChargeOut]:
    charges = await list_charges_for_player(player_id=player_id)
    today = date.today()
    out: list[MonthlyChargeOut] = []
    for ch in charges:
        amt = int(ch.get("amount", 0))
        paid = int(ch.get("paid", 0))
        remaining = amt - paid
        due = ch["due_date"].date() if hasattr(ch["due_date"], "date") else ch["due_date"]
        st = FeeStatus.al_dia if remaining <= 0 else (FeeStatus.atrasado if due < today else FeeStatus.pendiente)
        out.append(MonthlyChargeOut(**_charge_to_out(ch, st)))
    return out


@router.get("/status", response_model=list[PlayerFeeStatusOut], dependencies=[Depends(require_roles("admin", "tesorero", "delegado"))])
async def fees_status(series_id: str | None = None, active: bool = True) -> list[PlayerFeeStatusOut]:
    await ensure_charges_up_to_current()
    players = await list_players(active=active, series_id=series_id, q=None)
    player_ids = [p["id"] for p in players]

    today = date.today()
    ym = parse_year_month(f"{today.year:04d}-{today.month:02d}")
    up_to = last_day_of_month(ym)

    charges = await list_charges_for_players_up_to(player_ids=player_ids, up_to_due_date=up_to)
    by_player: dict[str, list[dict]] = {}
    for ch in charges:
        pid = str(ch["player_id"])
        by_player.setdefault(pid, []).append(ch)

    contribution = await get_players_contribution(player_ids=player_ids)

    out: list[PlayerFeeStatusOut] = []
    for p in players:
        chs = by_player.get(p["id"], [])
        st = compute_fee_status_for_player(charges=chs, today=today)

        total_pending = 0
        pending_months = 0
        for ch in chs:
            amt = int(ch.get("amount", 0))
            paid = int(ch.get("paid", 0))
            rem = amt - paid
            if rem > 0:
                total_pending += rem
                pending_months += 1

        fee_amount, fee_source = await resolve_fee_amount_for_player(
            player={"id": p["id"], "primary_series_id": p["primary_series_id"]}, ym=ym
        )
        credit = int(p.get("credit_balance", 0) or 0)
        contrib = contribution.get(p["id"], {})
        total_contributed = contrib.get("total_contributed", 0)
        paid_months_count = contrib.get("paid_months_count", 0)

        out.append(
            PlayerFeeStatusOut(
                player_id=p["id"],
                player_name=f"{p['first_name']} {p['last_name']}",
                series_id=p["primary_series_id"],
                status=st,
                fee_amount=fee_amount,
                fee_source=fee_source,
                total_pending=total_pending,
                pending_months_count=pending_months,
                credit_balance=credit,
                total_contributed=total_contributed,
                paid_months_count=paid_months_count,
            )
        )
    return out

