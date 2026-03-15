from __future__ import annotations

import asyncio
from datetime import date
from app.core.dates import YearMonth, date_to_utc_datetime, dt_to_date, iter_year_months, last_day_of_month, parse_year_month
from app.core.enums import FeeStatus
from app.db.ids import oid
from app.db.mongo import get_db, now_utc

# Cache para evitar ensure_charges repetido (requests paralelos)
_ensure_lock = asyncio.Lock()
_ensure_cache: dict[str, float] = {}
_ensure_ttl_seconds = 60


def _month_anchor(ym: YearMonth) -> date:
    return date(ym.year, ym.month, 1)


async def resolve_fee_amount_for_player(
    *, player: dict, ym: YearMonth, tournament_id: str | None = None
) -> tuple[int | None, str]:
    """
    Retorna (amount|None, source) en pesos CLP. source ∈ {'player','series','general','none'}.
    Las reglas se filtran por tournament_id cuando se indica.
    """
    anchor = _month_anchor(ym)
    anchor_dt = date_to_utc_datetime(anchor)
    db = get_db()
    conditions: list[dict] = [
        {"active": True},
        {"effective_from": {"$lte": anchor_dt}},
        {"$or": [{"effective_to": None}, {"effective_to": {"$gte": anchor_dt}}]},
    ]
    if tournament_id:
        conditions.append({"tournament_id": oid(tournament_id)})
    else:
        conditions.append({"$or": [{"tournament_id": {"$exists": False}}, {"tournament_id": None}]})
    base_match = {"$and": conditions}

    # Player rule
    q_player = {**base_match, "scope": "player", "scope_id": oid(player["id"])}
    r = await db.fee_rules.find(q_player).sort("effective_from", -1).limit(1).to_list(length=1)
    if r:
        return int(r[0].get("amount", 0)), "player"

    # Series (primary)
    q_series = {
        **base_match,
        "scope": "series",
        "scope_id": oid(player["primary_series_id"]),
    }
    r = await db.fee_rules.find(q_series).sort("effective_from", -1).limit(1).to_list(length=1)
    if r:
        return int(r[0].get("amount", 0)), "series"

    # General
    q_general = {**base_match, "scope": "general", "scope_id": None}
    r = await db.fee_rules.find(q_general).sort("effective_from", -1).limit(1).to_list(length=1)
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


def _resolve_amount_in_memory(
    *,
    pid: str,
    primary_series_id: str,
    rules_by_player: dict,
    rules_by_series: dict,
    general_amount: int | None,
) -> int | None:
    """Resuelve monto usando reglas pre-cargadas (player > series > general)."""
    if pid in rules_by_player:
        return rules_by_player[pid]
    if primary_series_id in rules_by_series:
        return rules_by_series[primary_series_id]
    return general_amount


async def generate_monthly_charges(*, year_month: str) -> dict:
    ym = parse_year_month(year_month)
    due = date_to_utc_datetime(last_day_of_month(ym))
    anchor = _month_anchor(ym)
    anchor_dt = date_to_utc_datetime(anchor)
    db = get_db()

    # 1. Cargar jugadores activos en lote
    players = await db.players.find(
        {"active": True},
        projection={"_id": 1, "primary_series_id": 1, "credit_balance": 1},
    ).to_list(length=5000)
    if not players:
        return {"year_month": year_month, "created": 0, "skipped_existing": 0, "skipped_no_rule": 0}

    pids = [p["_id"] for p in players]
    # 2. Cargos existentes para este mes (bulk)
    existing_docs = await db.monthly_charges.find(
        {"player_id": {"$in": pids}, "year_month": year_month},
        projection={"player_id": 1},
    ).to_list(length=5000)
    existing_pids = {str(d["player_id"]) for d in existing_docs}
    skipped_existing = len(existing_pids)

    # 3. Reglas activas aplicables (sin tournament) - bulk
    base_conditions = [
        {"active": True},
        {"effective_from": {"$lte": anchor_dt}},
        {"$or": [{"effective_to": None}, {"effective_to": {"$gte": anchor_dt}}]},
        {"$or": [{"tournament_id": {"$exists": False}}, {"tournament_id": None}]},
    ]
    rules = await db.fee_rules.find({"$and": base_conditions}).sort("effective_from", -1).to_list(length=500)
    rules_by_player: dict[str, int] = {}
    rules_by_series: dict[str, int] = {}
    general_amount: int | None = None
    for r in rules:
        amt = int(r.get("amount", 0))
        if r.get("scope") == "player" and r.get("scope_id"):
            sid = str(r["scope_id"])
            if sid not in rules_by_player:
                rules_by_player[sid] = amt
        elif r.get("scope") == "series" and r.get("scope_id"):
            sid = str(r["scope_id"])
            if sid not in rules_by_series:
                rules_by_series[sid] = amt
        elif r.get("scope") == "general" and general_amount is None:
            general_amount = amt

    # 4. Construir cargos a insertar
    now = now_utc()
    period_dt = date_to_utc_datetime(anchor)
    to_insert: list[dict] = []
    credit_updates: list[tuple[str, int, int]] = []  # (pid, apply_credit, charge_amount)

    for p in players:
        pid = str(p["_id"])
        if pid in existing_pids:
            continue
        amount = _resolve_amount_in_memory(
            pid=pid,
            primary_series_id=str(p["primary_series_id"]),
            rules_by_player=rules_by_player,
            rules_by_series=rules_by_series,
            general_amount=general_amount,
        )
        if amount is None:
            continue
        charge_amount = int(amount)
        credit = int(p.get("credit_balance", 0) or 0)
        paid_initial = 0
        if credit > 0:
            paid_initial = min(credit, charge_amount)
            credit_updates.append((pid, paid_initial, charge_amount))
        to_insert.append({
            "player_id": oid(pid),
            "year_month": year_month,
            "period": period_dt,
            "due_date": due,
            "amount": charge_amount,
            "paid": paid_initial,
            "created_at": now,
            "updated_at": now,
        })

    skipped_no_rule = len(players) - skipped_existing - len(to_insert)

    # 5. Aplicar créditos (updates individuales, típicamente pocos)
    for pid, apply_credit, _ in credit_updates:
        await db.players.update_one({"_id": oid(pid)}, {"$inc": {"credit_balance": -apply_credit}})

    # 6. Bulk insert
    if to_insert:
        await db.monthly_charges.insert_many(to_insert)

    return {"year_month": year_month, "created": len(to_insert), "skipped_existing": skipped_existing, "skipped_no_rule": skipped_no_rule}


async def generate_monthly_charges_for_tournament(
    *,
    year_month: str,
    tournament_id: str,
    series_ids: list[str],
    player_ids: list[str] | None,
) -> dict:
    """
    Genera cargos para un mes y torneo usando reglas del torneo.
    Solo crea cargos para jugadores del plantel (player_ids) o de las series (series_ids).
    """
    ym = parse_year_month(year_month)
    due = date_to_utc_datetime(last_day_of_month(ym))
    anchor = _month_anchor(ym)
    anchor_dt = date_to_utc_datetime(anchor)
    db = get_db()
    tid = oid(tournament_id)

    # 1. Jugadores del torneo
    q_players: dict = {"active": True}
    if player_ids:
        q_players["_id"] = {"$in": [oid(p) for p in player_ids]}
    elif series_ids:
        q_players["primary_series_id"] = {"$in": [oid(s) for s in series_ids]}
    else:
        return {"year_month": year_month, "created": 0, "skipped_existing": 0, "skipped_no_rule": 0}

    players = await db.players.find(
        q_players,
        projection={"_id": 1, "primary_series_id": 1, "credit_balance": 1},
    ).to_list(length=5000)
    if not players:
        return {"year_month": year_month, "created": 0, "skipped_existing": 0, "skipped_no_rule": 0}

    pids = [p["_id"] for p in players]

    # 2. Cargos existentes
    existing_docs = await db.monthly_charges.find(
        {"player_id": {"$in": pids}, "year_month": year_month},
        projection={"player_id": 1},
    ).to_list(length=5000)
    existing_pids = {str(d["player_id"]) for d in existing_docs}
    skipped_existing = len(existing_pids)

    # 3. Reglas del torneo
    base_conditions = [
        {"active": True},
        {"tournament_id": tid},
        {"effective_from": {"$lte": anchor_dt}},
        {"$or": [{"effective_to": None}, {"effective_to": {"$gte": anchor_dt}}]},
    ]
    rules = await db.fee_rules.find({"$and": base_conditions}).sort("effective_from", -1).to_list(length=500)
    rules_by_player: dict[str, int] = {}
    rules_by_series: dict[str, int] = {}
    general_amount: int | None = None
    for r in rules:
        amt = int(r.get("amount", 0))
        if r.get("scope") == "player" and r.get("scope_id"):
            sid = str(r["scope_id"])
            if sid not in rules_by_player:
                rules_by_player[sid] = amt
        elif r.get("scope") == "series" and r.get("scope_id"):
            sid = str(r["scope_id"])
            if sid not in rules_by_series:
                rules_by_series[sid] = amt
        elif r.get("scope") == "general" and general_amount is None:
            general_amount = amt

    # 4. Construir cargos
    now = now_utc()
    period_dt = date_to_utc_datetime(anchor)
    to_insert: list[dict] = []
    credit_updates: list[tuple[str, int, int]] = []

    for p in players:
        pid = str(p["_id"])
        if pid in existing_pids:
            continue
        amount = _resolve_amount_in_memory(
            pid=pid,
            primary_series_id=str(p["primary_series_id"]),
            rules_by_player=rules_by_player,
            rules_by_series=rules_by_series,
            general_amount=general_amount,
        )
        if amount is None:
            continue
        charge_amount = int(amount)
        credit = int(p.get("credit_balance", 0) or 0)
        paid_initial = 0
        if credit > 0:
            paid_initial = min(credit, charge_amount)
            credit_updates.append((pid, paid_initial, charge_amount))
        to_insert.append({
            "player_id": oid(pid),
            "year_month": year_month,
            "period": period_dt,
            "due_date": due,
            "amount": charge_amount,
            "paid": paid_initial,
            "created_at": now,
            "updated_at": now,
        })

    skipped_no_rule = len(players) - skipped_existing - len(to_insert)

    for pid, apply_credit, _ in credit_updates:
        await db.players.update_one({"_id": oid(pid)}, {"$inc": {"credit_balance": -apply_credit}})
    if to_insert:
        await db.monthly_charges.insert_many(to_insert)

    return {"year_month": year_month, "created": len(to_insert), "skipped_existing": skipped_existing, "skipped_no_rule": skipped_no_rule}


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


async def ensure_charges_for_dashboard() -> None:
    """
    Ejecuta ensure_charges_up_to_current y ensure_charges_for_tournament_periods
    con TTL de 60s para evitar trabajo redundante en requests paralelos.
    """
    import time
    key = "dashboard"
    async with _ensure_lock:
        now = time.monotonic()
        if key in _ensure_cache and (now - _ensure_cache[key]) < _ensure_ttl_seconds:
            return
        await ensure_charges_up_to_current()
        await ensure_charges_for_tournament_periods()
        _ensure_cache[key] = now


async def ensure_charges_for_tournament_periods() -> None:
    """
    Genera cargos para los meses del período de cada torneo usando sus reglas (tournament_id).
    ensure_charges_up_to_current ya cubre reglas generales (sin torneo).
    """
    from app.domains.tournaments.repo import list_tournaments

    today = date.today()
    current_ym = f"{today.year:04d}-{today.month:02d}"
    tournaments = await list_tournaments(active=None)

    for t in tournaments:
        start_month = t.get("start_month")
        end_month = t.get("end_month")
        if not start_month or not end_month or start_month > end_month:
            continue
        sids = [str(s) for s in (t.get("series_ids") or [])]
        pids = [str(p) for p in (t.get("player_ids") or [])]
        if not sids and not pids:
            continue
        tid = str(t.get("_id", t.get("id", "")))
        for ym in iter_year_months(start_month, end_month):
            if ym <= current_ym:
                await generate_monthly_charges_for_tournament(
                    year_month=ym,
                    tournament_id=tid,
                    series_ids=sids,
                    player_ids=pids if pids else None,
                )
