from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_current_user, require_roles
from app.core.dates import date_to_utc_datetime, last_day_of_month, parse_year_month
from app.core.enums import FeeStatus
from app.db.ids import oid
from app.domains.audit.service import log_audit
from app.domains.fees.repo import _charge_to_out, create_fee_rule, delete_fee_rule, get_fee_rule, get_collection_breakdown, get_fees_summary_by_period, get_fees_totals, get_player_period_matrix, get_players_contribution, list_charges_for_player, list_charges_for_players_up_to, list_fee_rules, update_fee_rule, get_unpaid_periods_for_tournament, _raw_fee_rules
from app.domains.fees.schemas import FeeRuleCreate, FeeRuleOut, FeeRuleUpdate, GenerateMonthResult, MonthlyChargeOut, PlayerFeeStatusOut
from app.domains.fees.service import compute_fee_status_for_player, ensure_charges_for_dashboard, ensure_charges_for_tournament_periods, ensure_charges_up_to_current, generate_monthly_charges, resolve_fee_amount_for_player
from app.core.validators import normalize_rut
from app.domains.players.repo import get_player, get_player_by_rut, list_players
from app.domains.tournaments.repo import get_tournament

router = APIRouter(prefix="/fees", tags=["fees"])


async def _tournament_filter(tournament_id: str | None) -> dict | None:
    """Resuelve tournament_id a {series_ids, player_ids, start_month, end_month}. Si player_ids está definido y no vacío, se usa el plantel; si no, series_ids."""
    if not tournament_id or not tournament_id.strip():
        return None
    t = await get_tournament(tournament_id.strip())
    if not t:
        return None
    sids = t.get("series_ids") or []
    pids = t.get("player_ids") or []
    start = t.get("start_month")
    end = t.get("end_month")
    if not sids and not pids:
        return None
    out: dict = {"series_ids": [str(s) for s in sids], "start_month": start, "end_month": end}
    if pids:
        out["player_ids"] = [str(p) for p in pids]
    return out


def _as_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    return None


def _periods_overlap(
    from_a: datetime | date,
    to_a: datetime | date | None,
    from_b: datetime | date,
    to_b: datetime | date | None,
) -> bool:
    """True si los períodos [from_a, to_a] y [from_b, to_b] se solapan."""
    FAR_FUTURE = date(9999, 12, 31)
    fa = _as_date(from_a) or date.min
    ta = _as_date(to_a) if to_a else FAR_FUTURE
    fb = _as_date(from_b) or date.min
    tb = _as_date(to_b) if to_b else FAR_FUTURE
    return fa < tb and fb < ta


async def _validate_fee_rule(
    scope: str,
    scope_id: str | None,
    effective_from: datetime | date,
    effective_to: datetime | date | None,
    tournament_id: str,
    exclude_rule_id: str | None = None,
) -> None:
    """Valida restricciones por torneo: 1 general, 1 por serie, jugador sin períodos solapados."""
    if scope == "general":
        existing = await _raw_fee_rules(
            scope="general", tournament_id=tournament_id, exclude_rule_id=exclude_rule_id
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Solo puede existir una regla general por torneo.",
            )
    elif scope == "series":
        if not scope_id:
            raise HTTPException(status_code=400, detail="scope_id requerido para regla por serie")
        existing = await _raw_fee_rules(
            scope="series",
            scope_id=scope_id,
            tournament_id=tournament_id,
            exclude_rule_id=exclude_rule_id,
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Ya existe una regla para esta serie en este torneo.",
            )
    elif scope == "player":
        if not scope_id:
            raise HTTPException(status_code=400, detail="scope_id requerido para regla por jugador")
        existing = await _raw_fee_rules(
            scope="player",
            scope_id=scope_id,
            tournament_id=tournament_id,
            exclude_rule_id=exclude_rule_id,
        )
        for r in existing:
            if _periods_overlap(
                effective_from, effective_to,
                r.get("effective_from"), r.get("effective_to"),
            ):
                raise HTTPException(
                    status_code=400,
                    detail="El jugador ya tiene una regla en ese período. Las reglas por jugador no pueden superponerse.",
                )


@router.get("/rules", response_model=list[FeeRuleOut], dependencies=[Depends(require_roles("admin", "tesorero"))])
async def fee_rules_list(
    scope: str | None = None,
    scope_id: str | None = None,
    tournament_id: str | None = None,
    active: bool | None = None,
) -> list[FeeRuleOut]:
    docs = await list_fee_rules(
        scope=scope, scope_id=scope_id, tournament_id=tournament_id, active=active
    )
    return [FeeRuleOut(**d) for d in docs]


@router.post("/rules", response_model=FeeRuleOut, dependencies=[Depends(require_roles("admin", "tesorero"))])
async def fee_rules_create(payload: FeeRuleCreate, actor=Depends(get_current_user)) -> FeeRuleOut:
    data = payload.model_dump()
    tournament_id = data.get("tournament_id")
    if not tournament_id:
        raise HTTPException(status_code=400, detail="tournament_id requerido")
    data["tournament_id"] = oid(tournament_id)
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

    await _validate_fee_rule(
        scope=data["scope"],
        scope_id=str(data["scope_id"]) if data.get("scope_id") else None,
        effective_from=data["effective_from"],
        effective_to=data.get("effective_to"),
        tournament_id=tournament_id,
    )
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

    # Validar si se modifican fechas o si hay que revalidar
    eff_from = patch.get("effective_from") if "effective_from" in patch else before.get("effective_from")
    eff_to = patch.get("effective_to") if "effective_to" in patch else before.get("effective_to")
    scope = before["scope"]
    scope_id = before.get("scope_id")
    scope_id_str = str(scope_id) if scope_id else None
    t_id = patch.get("tournament_id") or before.get("tournament_id")
    if not t_id:
        raise HTTPException(
            status_code=400,
            detail="La regla debe estar asociada a un torneo. Actualice tournament_id.",
        )
    tournament_id_str = str(t_id)
    if "tournament_id" in patch and patch["tournament_id"]:
        patch["tournament_id"] = oid(patch["tournament_id"])
    await _validate_fee_rule(
        scope=scope,
        scope_id=scope_id_str,
        effective_from=eff_from,
        effective_to=eff_to,
        tournament_id=tournament_id_str,
        exclude_rule_id=rule_id,
    )

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
async def fees_player_period_matrix(series_id: str | None = None, tournament_id: str | None = None) -> dict:
    """Matriz jugador vs períodos con estado de cuota. Opcional: filtrar por series_id o tournament_id."""
    await ensure_charges_for_dashboard()
    tournament_filter = await _tournament_filter(tournament_id)
    return await get_player_period_matrix(series_id=series_id, tournament_filter=tournament_filter)


@router.get("/summary-by-period", dependencies=[Depends(require_roles("admin", "tesorero", "delegado"))])
async def fees_summary_by_period(series_id: str | None = None, tournament_id: str | None = None) -> dict:
    """Resumen por período + totales + desglose. Opcional: filtrar por series_id o tournament_id."""
    await ensure_charges_for_dashboard()
    today = date.today()
    current_ym = f"{today.year:04d}-{today.month:02d}"
    tournament_filter = await _tournament_filter(tournament_id)
    periods = await get_fees_summary_by_period(current_year_month=current_ym, series_id=series_id, tournament_filter=tournament_filter)
    total_collected, total_pending = await get_fees_totals(current_year_month=current_ym, series_id=series_id, tournament_filter=tournament_filter)
    collection_breakdown = await get_collection_breakdown(series_id=series_id, current_year_month=current_ym, tournament_filter=tournament_filter)
    return {
        "periods": periods,
        "total_collected": total_collected,
        "total_pending": total_pending,
        "collection_by_series": collection_breakdown["by_series"],
        "collection_by_tournament": collection_breakdown["by_tournament"],
        "collection_by_player": collection_breakdown["by_player"],
    }


@router.get("/dashboard-totals", dependencies=[Depends(require_roles("admin", "tesorero", "delegado"))])
async def fees_dashboard_totals(series_id: str | None = None, tournament_id: str | None = None) -> dict:
    """Totales recaudado/pendiente. Opcional: filtrar por series_id o tournament_id."""
    await ensure_charges_for_dashboard()
    today = date.today()
    current_ym = f"{today.year:04d}-{today.month:02d}"
    tournament_filter = await _tournament_filter(tournament_id)
    total_collected, total_pending = await get_fees_totals(current_year_month=current_ym, series_id=series_id, tournament_filter=tournament_filter)
    return {"total_collected": total_collected, "total_pending": total_pending}


@router.get("/dashboard-periods", dependencies=[Depends(require_roles("admin", "tesorero", "delegado"))])
async def fees_dashboard_periods(series_id: str | None = None, tournament_id: str | None = None) -> dict:
    """Resumen por período. Opcional: filtrar por series_id o tournament_id."""
    await ensure_charges_for_dashboard()
    today = date.today()
    current_ym = f"{today.year:04d}-{today.month:02d}"
    tournament_filter = await _tournament_filter(tournament_id)
    periods = await get_fees_summary_by_period(current_year_month=current_ym, series_id=series_id, tournament_filter=tournament_filter)
    return {"periods": periods}


@router.get("/dashboard-breakdown", dependencies=[Depends(require_roles("admin", "tesorero", "delegado"))])
async def fees_dashboard_breakdown(series_id: str | None = None, tournament_id: str | None = None) -> dict:
    """Desglose por serie/torneo/jugador. Opcional: filtrar por series_id o tournament_id."""
    await ensure_charges_for_dashboard()
    today = date.today()
    current_ym = f"{today.year:04d}-{today.month:02d}"
    tournament_filter = await _tournament_filter(tournament_id)
    breakdown = await get_collection_breakdown(
        series_id=series_id,
        current_year_month=current_ym,
        tournament_filter=tournament_filter,
        request_series_id=series_id,
    )
    return {
        "collection_by_series": breakdown["by_series"],
        "collection_by_tournament": breakdown["by_tournament"],
        "collection_by_player": breakdown["by_player"],
    }


@router.get("/unpaid-periods", dependencies=[Depends(require_roles("admin", "tesorero", "delegado"))])
async def fees_unpaid_periods(tournament_id: str) -> dict:
    """Periodos (meses) no pagados por jugador para un torneo con período de cuotas definido."""
    result = await get_unpaid_periods_for_tournament(tournament_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Torneo no encontrado")
    return result


@router.get("/player-fee", dependencies=[Depends(require_roles("admin", "tesorero", "delegado"))])
async def fees_player_fee(
    player_id: str, year_month: str, tournament_id: str | None = None
) -> dict:
    """Retorna la cuota mensual de un jugador para un mes dado según las reglas activas del torneo."""
    p = await get_player(player_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jugador no encontrado")
    ym = parse_year_month(year_month)
    fee_amount, fee_source = await resolve_fee_amount_for_player(
        player={"id": p["id"], "primary_series_id": p["primary_series_id"]},
        ym=ym,
        tournament_id=tournament_id,
    )
    return {"fee_amount": fee_amount, "fee_source": fee_source}


@router.get("/player-fee-by-rut", dependencies=[Depends(require_roles("admin", "tesorero", "delegado"))])
async def fees_player_fee_by_rut(
    rut: str, year_month: str, tournament_id: str | None = None
) -> dict:
    """Retorna la cuota mensual para un RUT y mes según las reglas activas del torneo."""
    try:
        rut_norm = normalize_rut(rut.strip())
    except ValueError:
        return {"fee_amount": None, "fee_source": None}
    p = await get_player_by_rut(rut_norm)
    if not p:
        return {"fee_amount": None, "fee_source": None}
    ym = parse_year_month(year_month)
    fee_amount, fee_source = await resolve_fee_amount_for_player(
        player={"id": p["id"], "primary_series_id": p["primary_series_id"]},
        ym=ym,
        tournament_id=tournament_id,
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
async def fees_status(series_id: str | None = None, tournament_id: str | None = None, active: bool = True) -> list[PlayerFeeStatusOut]:
    await ensure_charges_for_dashboard()
    tournament_filter = await _tournament_filter(tournament_id)
    primary_series_ids = None
    tournament_player_ids = None
    if tournament_filter:
        tournament_player_ids = tournament_filter.get("player_ids")
        if not tournament_player_ids and tournament_filter.get("series_ids"):
            primary_series_ids = tournament_filter["series_ids"]
    players = await list_players(
        active=active,
        series_id=series_id if not primary_series_ids and not tournament_player_ids else None,
        primary_series_ids=primary_series_ids,
        player_ids=tournament_player_ids,
        q=None,
    )
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
            player={"id": p["id"], "primary_series_id": p["primary_series_id"]},
            ym=ym,
            tournament_id=tournament_id if tournament_filter else None,
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

