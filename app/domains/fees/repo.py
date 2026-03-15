from __future__ import annotations

from datetime import date, datetime

from app.core.enums import FeeStatus, PaymentStatus
from app.core.dates import date_to_utc_datetime, dt_to_date, iter_year_months
from app.db.ids import oid
from app.db.mongo import get_db, now_utc


def _rule_to_out(d: dict) -> dict:
    d = {**d}
    d["id"] = str(d.pop("_id"))
    if d.get("scope_id") is not None:
        d["scope_id"] = str(d["scope_id"])
    if d.get("tournament_id") is not None:
        d["tournament_id"] = str(d["tournament_id"])
    if isinstance(d.get("effective_from"), datetime):
        d["effective_from"] = dt_to_date(d["effective_from"])
    if isinstance(d.get("effective_to"), datetime):
        d["effective_to"] = dt_to_date(d["effective_to"])
    return d


def _charge_ym(d: dict) -> str:
    """year_month desde period (date) o year_month (string)."""
    p = d.get("period")
    if p is not None:
        return p.strftime("%Y-%m") if hasattr(p, "strftime") else f"{p.year:04d}-{p.month:02d}"
    return d.get("year_month", "")


def _charge_to_out(d: dict, status: FeeStatus) -> dict:
    d = {**d}
    d["id"] = str(d.pop("_id"))
    d["player_id"] = str(d["player_id"])
    if isinstance(d.get("due_date"), datetime):
        d["due_date"] = d["due_date"].date()
    paid = int(d.get("paid", 0))
    amt = int(d.get("amount", 0))
    d["year_month"] = _charge_ym(d)
    d["amount"] = amt
    d["paid"] = paid
    d["remaining"] = max(0, amt - paid)
    d["status"] = status.value
    return d


async def create_fee_rule(doc: dict) -> dict:
    db = get_db()
    now = now_utc()
    doc = {**doc, "created_at": now, "updated_at": now}
    res = await db.fee_rules.insert_one(doc)
    created = await db.fee_rules.find_one({"_id": res.inserted_id})
    return _rule_to_out(created)


async def list_fee_rules(
    *,
    scope: str | None = None,
    scope_id: str | None = None,
    tournament_id: str | None = None,
    active: bool | None = None,
) -> list[dict]:
    db = get_db()
    q: dict = {}
    if scope:
        q["scope"] = scope
    if scope_id is not None:
        q["scope_id"] = None if scope == "general" else oid(scope_id)
    if tournament_id:
        q["tournament_id"] = oid(tournament_id)
    if active is not None:
        q["active"] = active
    cur = db.fee_rules.find(q).sort([("scope", 1), ("effective_from", -1)])
    out: list[dict] = []
    async for d in cur:
        out.append(_rule_to_out(d))
    return out


async def get_fee_rule(rule_id: str) -> dict | None:
    db = get_db()
    d = await db.fee_rules.find_one({"_id": oid(rule_id)})
    return _rule_to_out(d) if d else None


async def update_fee_rule(rule_id: str, patch: dict) -> dict | None:
    db = get_db()
    allow_none = {"effective_to"}
    patch = {k: v for k, v in patch.items() if v is not None or k in allow_none}
    if not patch:
        return await get_fee_rule(rule_id)
    patch["updated_at"] = now_utc()
    await db.fee_rules.update_one({"_id": oid(rule_id)}, {"$set": patch})
    return await get_fee_rule(rule_id)


async def delete_fee_rule(rule_id: str) -> bool:
    """Elimina una regla de cuota. Retorna True si se eliminó."""
    db = get_db()
    res = await db.fee_rules.delete_one({"_id": oid(rule_id)})
    return res.deleted_count > 0


async def _raw_fee_rules(
    scope: str | None = None,
    scope_id: str | None = None,
    tournament_id: str | None = None,
    exclude_rule_id: str | None = None,
) -> list[dict]:
    """Reglas en crudo (para validación). Filtra por torneo cuando se indica."""
    db = get_db()
    q: dict = {}
    if scope:
        q["scope"] = scope
        if scope == "general":
            q["scope_id"] = None
        elif scope_id:
            q["scope_id"] = oid(scope_id)
    if tournament_id:
        q["tournament_id"] = oid(tournament_id)
    if exclude_rule_id:
        q["_id"] = {"$ne": oid(exclude_rule_id)}
    return await db.fee_rules.find(q).to_list(length=1000)


async def list_charges_for_player(*, player_id: str) -> list[dict]:
    db = get_db()
    cur = db.monthly_charges.find({"player_id": oid(player_id)}).sort([("year_month", -1)])
    out: list[dict] = []
    async for d in cur:
        out.append(d)
    return out


async def list_charges_for_players_up_to(*, player_ids: list[str], up_to_due_date: date) -> list[dict]:
    db = get_db()
    oids = [oid(x) for x in player_ids]
    cur = db.monthly_charges.find({"player_id": {"$in": oids}, "due_date": {"$lte": date_to_utc_datetime(up_to_due_date)}})
    out: list[dict] = []
    async for d in cur:
        out.append(d)
    return out


async def get_players_contribution(*, player_ids: list[str]) -> dict[str, dict]:
    """
    Por cada player_id retorna total_contributed (suma de paid en sus cargos) y
    paid_months_count (cuántos cargos tienen paid >= amount). Incluye adelantos.
    """
    if not player_ids:
        return {}
    db = get_db()
    oids = [oid(x) for x in player_ids]
    pipeline = [
        {"$match": {"player_id": {"$in": oids}}},
        {
            "$group": {
                "_id": "$player_id",
                "total_contributed": {"$sum": {"$ifNull": ["$paid", 0]}},
                "paid_months_count": {"$sum": {"$cond": [{"$gte": [{"$ifNull": ["$paid", 0]}, "$amount"]}, 1, 0]}},
            }
        },
    ]
    result: dict[str, dict] = {}
    async for doc in db.monthly_charges.aggregate(pipeline):
        pid = str(doc["_id"])
        result[pid] = {
            "total_contributed": int(doc.get("total_contributed", 0)),
            "paid_months_count": int(doc.get("paid_months_count", 0)),
        }
    for pid in player_ids:
        if pid not in result:
            result[pid] = {"total_contributed": 0, "paid_months_count": 0}
    return result


async def get_collection_breakdown(
    series_id: str | None = None,
    current_year_month: str | None = None,
    tournament_filter: dict | None = None,
    *,
    request_series_id: str | None = None,
) -> dict:
    """
    Recaudación desglosada por serie, torneo y jugador.
    Si tournament_filter, filtra por series_ids y rango year_month del torneo.
    """
    db = get_db()
    sid, sids, pids, ym_start, ym_end = _resolve_filter(series_id, tournament_filter)
    ym_upper = min(ym_end, current_year_month) if (ym_end and current_year_month) else current_year_month
    ym_match_series: dict | None = None
    if ym_start and ym_end and current_year_month:
        ym_match_series = {"$gte": ym_start, "$lte": ym_upper or current_year_month}

    # Un solo pipeline por serie: total_collected y total_pending en la misma agregación para evitar cruce de montos
    if ym_match_series:
        ym_filter = ym_match_series
    elif current_year_month and ym_start and ym_end:
        ym_filter = {"$gte": ym_start, "$lte": min(ym_end, current_year_month)}
    elif current_year_month:
        ym_filter = {"$lte": current_year_month}
    else:
        ym_filter = None

    pipeline_series: list[dict] = []
    if ym_filter:
        pipeline_series.append({"$match": {"year_month": ym_filter}})
    if pids:
        pipeline_series.append({"$match": {"player_id": {"$in": [oid(p) for p in pids]}}})
    pipeline_series.extend([
        {"$lookup": {"from": "players", "localField": "player_id", "foreignField": "_id", "as": "pl"}},
        {"$unwind": {"path": "$pl", "preserveNullAndEmptyArrays": False}},
    ])
    if sids:
        pipeline_series.append({"$match": {"pl.primary_series_id": {"$in": [oid(s) for s in sids]}}})
    elif sid:
        pipeline_series.append({"$match": {"pl.primary_series_id": oid(sid)}})
    pipeline_series.append({
        "$group": {
            "_id": "$pl.primary_series_id",
            "total_collected": {"$sum": {"$ifNull": ["$paid", 0]}},
            "total_pending": {"$sum": {"$max": [0, {"$subtract": ["$amount", {"$ifNull": ["$paid", 0]}]}]}},
        }
    })
    by_series_raw: list[dict] = []
    async for doc in db.monthly_charges.aggregate(pipeline_series):
        series_id_str = str(doc["_id"])
        by_series_raw.append({
            "series_id": series_id_str,
            "total_collected": int(doc.get("total_collected", 0)),
            "total_pending": int(doc.get("total_pending", 0)),
        })

    # Nombres de series
    series_ids = [d["series_id"] for d in by_series_raw]
    series_names: dict[str, str] = {}
    if series_ids:
        async for s in db.series.find({"_id": {"$in": [oid(sid) for sid in series_ids]}}, projection={"name": 1}):
            series_names[str(s["_id"])] = s.get("name", "")

    by_series = [
        {
            "series_id": d["series_id"],
            "series_name": series_names.get(d["series_id"], d["series_id"]),
            "total_collected": d["total_collected"],
            "total_pending": d["total_pending"],
        }
        for d in by_series_raw
    ]
    by_series.sort(key=lambda x: (-x["total_collected"], x["series_name"]))

    # Por torneo: total_collected desde payments (tienen tournament_id); total_expected/total_pending desde charges
    from app.domains.tournaments.repo import list_tournaments
    tournaments = await list_tournaments(active=None)
    # Recaudado por torneo desde pagos validados
    pay_pipeline: list[dict] = [
        {"$match": {"status": {"$in": [PaymentStatus.confirmed.value, "validated"]}, "tournament_id": {"$ne": None, "$exists": True}}},
    ]
    if pids:
        pay_pipeline.append({"$match": {"player_id": {"$in": [oid(p) for p in pids]}}})
    elif sid or sids:
        pay_pipeline.extend([
            {"$lookup": {"from": "players", "localField": "player_id", "foreignField": "_id", "as": "_pl"}},
            {"$unwind": {"path": "$_pl", "preserveNullAndEmptyArrays": False}},
            {"$match": {"_pl.primary_series_id": oid(sid) if sid else {"$in": [oid(s) for s in sids]}}},
        ])
    pay_pipeline.append({
        "$group": {"_id": "$tournament_id", "total_collected": {"$sum": {"$ifNull": ["$amount_total", "$amount"]}}},
    })
    collected_by_tid: dict[str, int] = {}
    async for doc in db.payments.aggregate(pay_pipeline):
        collected_by_tid[str(doc["_id"])] = int(doc.get("total_collected", 0))

    # Serie del filtro: solo torneos que la incluyen
    filter_series = request_series_id or sid
    by_tournament = []
    for t in tournaments:
        t_sids = [str(x) for x in (t.get("series_ids") or [])]
        t_pids = [str(x) for x in (t.get("player_ids") or [])]
        if filter_series and filter_series not in t_sids:
            continue
        if sids and not filter_series and not any(s in t_sids for s in sids):
            continue
        tid = t.get("id") or str(t.get("_id", ""))
        total = collected_by_tid.get(tid, 0)
        start_month = t.get("start_month")
        end_month = t.get("end_month")
        total_expected = total_pending_period = 0
        if start_month and end_month and start_month <= end_month and (t_sids or t_pids):
            pipeline = [{"$match": {"year_month": {"$gte": start_month, "$lte": end_month}}}]
            if t_pids:
                pipeline.append({"$match": {"player_id": {"$in": [oid(p) for p in t_pids]}}})
            else:
                sids_oids = [oid(s) for s in (sids if sids else [sid] if sid else t_sids)]
                pipeline.extend([
                    {"$lookup": {"from": "players", "localField": "player_id", "foreignField": "_id", "as": "pl"}},
                    {"$unwind": {"path": "$pl", "preserveNullAndEmptyArrays": False}},
                    {"$match": {"pl.primary_series_id": {"$in": sids_oids}}},
                ])
            pipeline.append({
                "$group": {
                    "_id": None,
                    "total_expected": {"$sum": "$amount"},
                    "total_pending_period": {"$sum": {"$max": [0, {"$subtract": ["$amount", {"$ifNull": ["$paid", 0]}]}]}},
                }
            })
            res = await db.monthly_charges.aggregate(pipeline).to_list(length=1)
            if res:
                total_expected = int(res[0].get("total_expected", 0))
                total_pending_period = int(res[0].get("total_pending_period", 0))
        by_tournament.append({
            "tournament_id": tid,
            "tournament_name": t.get("name", ""),
            "total_collected": total,
            "total_expected": total_expected,
            "total_pending": total_pending_period,
        })
    by_tournament.sort(key=lambda x: (-x["total_collected"], x["tournament_name"]))

    # Por jugador: group by player_id, sum paid; lookup player name
    pipeline_player: list[dict] = []
    if ym_match_series:
        pipeline_player.append({"$match": {"year_month": ym_match_series}})
    if sids:
        pipeline_player.extend([
            {"$lookup": {"from": "players", "localField": "player_id", "foreignField": "_id", "as": "pl"}},
            {"$unwind": {"path": "$pl", "preserveNullAndEmptyArrays": False}},
            {"$match": {"pl.primary_series_id": {"$in": [oid(s) for s in sids]}}},
        ])
    elif sid:
        pipeline_player.extend([
            {"$lookup": {"from": "players", "localField": "player_id", "foreignField": "_id", "as": "pl"}},
            {"$unwind": {"path": "$pl", "preserveNullAndEmptyArrays": False}},
            {"$match": {"pl.primary_series_id": oid(sid)}},
        ])
    pipeline_player.extend([
        {"$group": {"_id": "$player_id", "total_collected": {"$sum": {"$ifNull": ["$paid", 0]}}}},
        {"$lookup": {"from": "players", "localField": "_id", "foreignField": "_id", "as": "pl"}},
        {"$unwind": {"path": "$pl", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "_id": 0,
                "player_id": {"$toString": "$_id"},
                "total_collected": {"$add": ["$total_collected", {"$ifNull": ["$pl.credit_balance", 0]}]},
                "player_name": {"$concat": [{"$ifNull": ["$pl.first_name", ""]}, " ", {"$ifNull": ["$pl.last_name", ""]}]},
            }
        },
    ])
    by_player = []
    async for doc in db.monthly_charges.aggregate(pipeline_player):
        by_player.append({
            "player_id": doc.get("player_id", ""),
            "player_name": (doc.get("player_name") or "").strip() or "—",
            "total_collected": int(doc.get("total_collected", 0)),
        })
    by_player.sort(key=lambda x: (-x["total_collected"], x["player_name"]))

    return {"by_series": by_series, "by_tournament": by_tournament, "by_player": by_player}


def _player_ids_match_stage(player_ids: list[str] | None) -> list[dict]:
    """Si player_ids está definido, retorna [$match player_id in list]. Si no, []."""
    if not player_ids:
        return []
    return [{"$match": {"player_id": {"$in": [oid(p) for p in player_ids]}}}]


def _series_match_stage(series_id: str | None, series_ids: list[str] | None = None, player_ids: list[str] | None = None):
    """Si player_ids está definido, retorna match por player_id. Si series_ids/series_id, retorna [$lookup, $unwind, $match]. Si no, []."""
    if player_ids and len(player_ids) > 0:
        return _player_ids_match_stage(player_ids)
    if series_ids and len(series_ids) > 0:
        return [
            {"$lookup": {"from": "players", "localField": "player_id", "foreignField": "_id", "as": "_pl"}},
            {"$unwind": {"path": "$_pl", "preserveNullAndEmptyArrays": False}},
            {"$match": {"_pl.primary_series_id": {"$in": [oid(s) for s in series_ids]}}},
        ]
    if not series_id:
        return []
    return [
        {"$lookup": {"from": "players", "localField": "player_id", "foreignField": "_id", "as": "_pl"}},
        {"$unwind": {"path": "$_pl", "preserveNullAndEmptyArrays": False}},
        {"$match": {"_pl.primary_series_id": oid(series_id)}},
    ]


def _resolve_filter(
    series_id: str | None,
    tournament_filter: dict | None,
) -> tuple[str | None, list[str] | None, list[str] | None, str | None, str | None]:
    """
    Retorna (series_id, series_ids, player_ids, year_month_start, year_month_end).
    Si tournament_filter tiene player_ids, se usa el plantel; si no, series_ids.
    """
    if tournament_filter:
        pids = tournament_filter.get("player_ids") or []
        sids = tournament_filter.get("series_ids") or []
        start = tournament_filter.get("start_month")
        end = tournament_filter.get("end_month")
        return (None, sids if sids else None, pids if pids else None, start, end)
    return (series_id, None, None, None, None)


async def get_fees_totals(
    *,
    current_year_month: str,
    series_id: str | None = None,
    tournament_filter: dict | None = None,
) -> tuple[int, int]:
    """
    Retorna (total_collected, total_pending) en pesos CLP.
    Si tournament_filter está definido, filtra por series_ids del torneo y rango year_month.
    """
    db = get_db()
    sid, sids, pids, ym_start, ym_end = _resolve_filter(series_id, tournament_filter)
    series_match = _series_match_stage(sid, sids, pids)

    ym_match = {"$lte": current_year_month}
    if ym_start and ym_end:
        ym_match = {"$gte": ym_start, "$lte": min(ym_end, current_year_month)}

    coll_pipeline = [
        {"$match": {"status": {"$in": [PaymentStatus.confirmed.value, "validated"]}}},
    ]
    if sid or sids:
        coll_pipeline.extend([
            {"$lookup": {"from": "players", "localField": "player_id", "foreignField": "_id", "as": "_pl"}},
            {"$unwind": {"path": "$_pl", "preserveNullAndEmptyArrays": False}},
            {"$match": {"_pl.primary_series_id": oid(sid) if sid else {"$in": [oid(s) for s in sids]}}},
        ])
    coll_pipeline.append({"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$amount_total", "$amount"]}}}})
    # Para payments no hay year_month directo; el filtro por torneo se aplica en charges
    coll_result = await db.payments.aggregate(coll_pipeline).to_list(length=1)
    total_collected = int(coll_result[0]["total"]) if coll_result else 0

    pipeline = [
        {"$match": {"year_month": ym_match}},
        *series_match,
        {"$project": {"rem": {"$subtract": ["$amount", {"$ifNull": ["$paid", 0]}]}}},
        {"$match": {"rem": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$rem"}}},
    ]
    pend_result = await db.monthly_charges.aggregate(pipeline).to_list(length=1)
    total_pending = int(pend_result[0]["total"]) if pend_result else 0
    return total_collected, total_pending


async def get_fees_summary_by_period(
    current_year_month: str,
    series_id: str | None = None,
    tournament_filter: dict | None = None,
) -> list[dict]:
    """
    Resumen por período. Si tournament_filter, solo meses en [start_month, end_month].
    """
    db = get_db()
    sid, sids, pids, ym_start, ym_end = _resolve_filter(series_id, tournament_filter)
    ym_upper = min(ym_end, current_year_month) if ym_end else current_year_month
    base_ym = {"$lte": ym_upper}
    if ym_start and ym_end:
        base_ym = {"$gte": ym_start, "$lte": ym_upper}
    base_match: dict = {"year_month": base_ym}
    if pids:
        base_match["player_id"] = {"$in": [oid(p) for p in pids]}
    elif sids:
        player_ids_cursor = db.players.find({"primary_series_id": {"$in": [oid(s) for s in sids]}}, projection={"_id": 1})
        player_ids = [p["_id"] async for p in player_ids_cursor]
        if not player_ids:
            return []
        base_match["player_id"] = {"$in": player_ids}
    elif sid:
        player_ids_cursor = db.players.find({"primary_series_id": oid(sid)}, projection={"_id": 1})
        player_ids = [p["_id"] async for p in player_ids_cursor]
        if not player_ids:
            return []
        base_match["player_id"] = {"$in": player_ids}
    months: list[str] = await db.monthly_charges.distinct("year_month", base_match)
    months.sort(reverse=True)

    out: list[dict] = []
    for ym in months:
        pipeline = [
            {"$match": {"year_month": ym}},
            *_series_match_stage(sid, sids, pids),
            {
                "$group": {
                    "_id": None,
                    "total_expected": {"$sum": "$amount"},
                    "total_collected": {"$sum": {"$ifNull": ["$paid", 0]}},
                    "players_total": {"$sum": 1},
                    "players_paid": {"$sum": {"$cond": [{"$gte": [{"$ifNull": ["$paid", 0]}, "$amount"]}, 1, 0]}},
                }
            },
        ]
        result = await db.monthly_charges.aggregate(pipeline).to_list(length=1)
        if not result:
            continue
        r = result[0]
        total_expected = int(r["total_expected"])
        total_collected = int(r["total_collected"])
        total_pending = max(0, total_expected - total_collected)
        players_total = int(r["players_total"])
        players_paid = int(r["players_paid"])
        out.append({
            "year_month": ym,
            "status": "al_dia" if total_pending <= 0 else "pendiente",
            "total_expected": total_expected,
            "total_collected": total_collected,
            "total_pending": total_pending,
            "players_total": players_total,
            "players_paid": players_paid,
        })
    return out


async def get_player_period_matrix(
    series_id: str | None = None,
    tournament_filter: dict | None = None,
) -> dict:
    """
    Retorna matriz jugador vs períodos. Si tournament_filter, solo jugadores de esas series
    y solo cargos en el rango [start_month, end_month].
    """
    db = get_db()
    sid, sids, pids, ym_start, ym_end = _resolve_filter(series_id, tournament_filter)

    q_players: dict = {"active": True}
    if pids:
        q_players["_id"] = {"$in": [oid(p) for p in pids]}
    elif sids:
        q_players["primary_series_id"] = {"$in": [oid(s) for s in sids]}
    elif sid:
        q_players["primary_series_id"] = oid(sid)
    players_cur = db.players.find(q_players, projection={"password_hash": 0})

    player_ids: list[str] = []
    players_info: list[dict] = []
    async for p in players_cur:
        pid = str(p["_id"])
        player_ids.append(pid)
        players_info.append({
            "player_id": pid,
            "player_name": f"{p['first_name']} {p['last_name']}",
            "series_id": str(p["primary_series_id"]),
        })

    if not player_ids:
        return {"periods": [], "players": []}

    oids = [oid(x) for x in player_ids]
    charges_query: dict = {"player_id": {"$in": oids}}
    if ym_start and ym_end:
        charges_query["year_month"] = {"$gte": ym_start, "$lte": ym_end}
    months = await db.monthly_charges.distinct("year_month", charges_query)
    months.sort(reverse=True)

    charges_cur = db.monthly_charges.find(charges_query)

    by_player: dict[str, dict[str, dict]] = {pid: {} for pid in player_ids}
    async for ch in charges_cur:
        pid = str(ch["player_id"])
        ym = _charge_ym(ch)
        amt = int(ch.get("amount", 0))
        paid = int(ch.get("paid", 0))
        status = "pagado" if paid >= amt else "pendiente"
        by_player.setdefault(pid, {})[ym] = {
            "status": status,
            "amount": amt,
            "paid": paid,
        }

    players_out = []
    for info in players_info:
        pid = info["player_id"]
        players_out.append({
            **info,
            "periods": by_player.get(pid, {}),
        })
    return {"periods": months, "players": players_out}


async def get_unpaid_periods_for_tournament(tournament_id: str) -> dict | None:
    """
    Para un torneo con start_month/end_month y series_ids, retorna los periodos (meses) no pagados
    por cada jugador de esas series. Un mes es no pagado si no existe cargo o si paid < amount.
    Retorna: { tournament_id, tournament_name, start_month, end_month, players: [ { player_id, player_name, series_id, unpaid_months: [ym,...] } ] }
    """
    from app.domains.tournaments.repo import get_tournament

    t = await get_tournament(tournament_id)
    if not t:
        return None
    start_month = t.get("start_month")
    end_month = t.get("end_month")
    sids = t.get("series_ids") or []
    pids = t.get("player_ids") or []
    if not start_month or not end_month or start_month > end_month or (not sids and not pids):
        return {
            "tournament_id": tournament_id,
            "tournament_name": t.get("name", ""),
            "start_month": start_month,
            "end_month": end_month,
            "players": [],
        }

    db = get_db()
    if pids:
        players_cur = db.players.find(
            {"active": True, "_id": {"$in": [oid(p) for p in pids]}},
            projection={"password_hash": 0},
        )
    else:
        sids_oids = [oid(s) for s in sids]
        players_cur = db.players.find(
            {"active": True, "primary_series_id": {"$in": sids_oids}},
            projection={"password_hash": 0},
        )
    player_ids: list[str] = []
    players_info: list[dict] = []
    async for p in players_cur:
        pid = str(p["_id"])
        player_ids.append(pid)
        players_info.append({
            "player_id": pid,
            "player_name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or "—",
            "series_id": str(p["primary_series_id"]),
        })

    if not player_ids:
        return {
            "tournament_id": tournament_id,
            "tournament_name": t.get("name", ""),
            "start_month": start_month,
            "end_month": end_month,
            "players": [],
        }

    # Cargos de esos jugadores en el rango [start_month, end_month]
    oids = [oid(x) for x in player_ids]
    charges_cur = db.monthly_charges.find({
        "player_id": {"$in": oids},
        "year_month": {"$gte": start_month, "$lte": end_month},
    })
    by_player_charges: dict[str, dict[str, dict]] = {pid: {} for pid in player_ids}
    async for ch in charges_cur:
        pid = str(ch["player_id"])
        ym = _charge_ym(ch)
        amt = int(ch.get("amount", 0))
        paid = int(ch.get("paid", 0))
        by_player_charges.setdefault(pid, {})[ym] = {"amount": amt, "paid": paid}

    expected_months = list(iter_year_months(start_month, end_month))
    players_out = []
    for info in players_info:
        pid = info["player_id"]
        charges = by_player_charges.get(pid, {})
        unpaid = [
            ym for ym in expected_months
            if ym not in charges or charges[ym]["paid"] < charges[ym]["amount"]
        ]
        players_out.append({
            **info,
            "unpaid_months": unpaid,
        })

    return {
        "tournament_id": tournament_id,
        "tournament_name": t.get("name", ""),
        "start_month": start_month,
        "end_month": end_month,
        "players": players_out,
    }
