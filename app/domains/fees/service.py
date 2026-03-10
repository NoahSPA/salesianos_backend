from __future__ import annotations

from datetime import date
from app.core.dates import YearMonth, date_to_utc_datetime, dt_to_date, iter_year_months, last_day_of_month, parse_year_month
from app.core.enums import FeeStatus
from app.db.ids import oid
from app.db.mongo import get_db, now_utc


def _month_anchor(ym: YearMonth) -> date:
    return date(ym.year, ym.month, 1)


async def resolve_fee_amount_for_player(*, player: dict, ym: YearMonth) -> tuple[int | None, str]:
    """
    Retorna (amount|None, source) en pesos CLP. source ∈ {'player','series','general','none'}.
    """
    anchor = _month_anchor(ym)
    anchor_dt = date_to_utc_datetime(anchor)
    db = get_db()

    # Player rule
    r = await db.fee_rules.find(
        {
            "scope": "player",
            "scope_id": oid(player["id"]),
            "active": True,
            "effective_from": {"$lte": anchor_dt},
            "$or": [{"effective_to": None}, {"effective_to": {"$gte": anchor_dt}}],
        }
    ).sort("effective_from", -1).limit(1).to_list(length=1)
    if r:
        return int(r[0].get("amount", 0)), "player"

    # Series (primary)
    r = await db.fee_rules.find(
        {
            "scope": "series",
            "scope_id": oid(player["primary_series_id"]),
            "active": True,
            "effective_from": {"$lte": anchor_dt},
            "$or": [{"effective_to": None}, {"effective_to": {"$gte": anchor_dt}}],
        }
    ).sort("effective_from", -1).limit(1).to_list(length=1)
    if r:
        return int(r[0].get("amount", 0)), "series"

    # General
    r = await db.fee_rules.find(
        {
            "scope": "general",
            "scope_id": None,
            "active": True,
            "effective_from": {"$lte": anchor_dt},
            "$or": [{"effective_to": None}, {"effective_to": {"$gte": anchor_dt}}],
        }
    ).sort("effective_from", -1).limit(1).to_list(length=1)
    if r:
        return int(r[0].get("amount", 0)), "general"

    return None, "none"


def compute_fee_status_for_player(*, charges: list[dict], today: date) -> FeeStatus:
    for ch in charges:
        amt = int(ch.get("amount", 0))
        paid = int(ch.get("paid", 0))
        remaining = amt - paid
        due = ch.get("due_date")
        due_d = dt_to_date(due) if due is not None else None
        if remaining > 0 and due_d is not None and due_d < today:
            return FeeStatus.atrasado
    for ch in charges:
        amt = int(ch.get("amount", 0))
        paid = int(ch.get("paid", 0))
        remaining = amt - paid
        due = ch.get("due_date")
        due_d = dt_to_date(due) if due is not None else None
        if remaining > 0 and due_d is not None and due_d >= today:
            return FeeStatus.pendiente
    return FeeStatus.al_dia


async def generate_monthly_charges(*, year_month: str) -> dict:
    ym = parse_year_month(year_month)
    due = date_to_utc_datetime(last_day_of_month(ym))
    anchor = _month_anchor(ym)
    db = get_db()

    players_cur = db.players.find({"active": True}, projection={"password_hash": 0})

    created = skipped_existing = skipped_no_rule = 0
    async for p in players_cur:
        pid = str(p["_id"])
        existing = await db.monthly_charges.find_one({"player_id": oid(pid), "year_month": year_month})
        if existing:
            skipped_existing += 1
            continue

        player_out = {
            "id": pid,
            "primary_series_id": str(p["primary_series_id"]),
        }
        amount, _source = await resolve_fee_amount_for_player(player=player_out, ym=ym)
        if amount is None:
            skipped_no_rule += 1
            continue

        now = now_utc()
        period_dt = date_to_utc_datetime(anchor)
        charge_amount = int(amount)
        paid_initial = 0
        credit = int(p.get("credit_balance", 0) or 0)
        if credit > 0:
            apply_credit = min(credit, charge_amount)
            paid_initial = apply_credit
            await db.players.update_one(
                {"_id": oid(pid)},
                {"$inc": {"credit_balance": -apply_credit}},
            )
        await db.monthly_charges.insert_one(
            {
                "player_id": oid(pid),
                "year_month": year_month,
                "period": period_dt,
                "due_date": due,
                "amount": charge_amount,
                "paid": paid_initial,
                "created_at": now,
                "updated_at": now,
            }
        )
        created += 1

    return {"year_month": year_month, "created": created, "skipped_existing": skipped_existing, "skipped_no_rule": skipped_no_rule}


async def ensure_charges_up_to_current() -> None:
    """
    Genera cargos dinámicamente para todos los jugadores activos desde enero hasta
    el mes siguiente al actual (para permitir adelantos), si no existen.
    """
    today = date.today()
    end_month = today.month + 1
    end_year = today.year
    if end_month > 12:
        end_month = 1
        end_year += 1
    for m in range(1, today.month + 1):
        ym_str = f"{today.year:04d}-{m:02d}"
        await generate_monthly_charges(year_month=ym_str)
    ym_next = f"{end_year:04d}-{end_month:02d}"
    await generate_monthly_charges(year_month=ym_next)


async def ensure_charges_for_tournament_periods() -> None:
    """
    Genera cargos para todos los meses del período de cuotas de cada torneo (hasta el mes actual),
    para que el desglose por torneo muestre total_expected y total_pending correctos.
    """
    from app.domains.tournaments.repo import list_tournaments

    today = date.today()
    current_ym = f"{today.year:04d}-{today.month:02d}"
    tournaments = await list_tournaments(active=None)
    seen_ym: set[str] = set()
    for t in tournaments:
        start_month = t.get("start_month")
        end_month = t.get("end_month")
        if not start_month or not end_month or start_month > end_month:
            continue
        for ym in iter_year_months(start_month, end_month):
            if ym <= current_ym and ym not in seen_ym:
                seen_ym.add(ym)
                await generate_monthly_charges(year_month=ym)
