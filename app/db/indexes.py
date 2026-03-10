from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    # users
    await db.users.create_index("username", unique=True)
    await db.users.create_index([("role", 1), ("active", 1)])

    # players
    await db.players.create_index("rut", unique=True)
    await db.players.create_index([("active", 1), ("last_name", 1), ("first_name", 1)])
    await db.players.create_index("series_ids")
    await db.players.create_index([("primary_series_id", 1), ("active", 1)])
    await db.players.create_index("birth_date")

    # series
    await db.series.create_index("name", unique=True)
    await db.series.create_index([("active", 1), ("name", 1)])

    # rivals
    await db.rivals.create_index([("active", 1), ("name", 1)])
    await db.rivals.create_index("series_ids")

    # tournaments
    await db.tournaments.create_index([("season_year", 1), ("name", 1)], unique=True)
    await db.tournaments.create_index([("active", 1), ("season_year", -1)])

    # matches
    await db.matches.create_index([("series_id", 1), ("match_date", 1)])
    await db.matches.create_index([("tournament_id", 1), ("match_date", 1)])
    await db.matches.create_index([("status", 1), ("match_date", 1)])

    # convocations
    await db.convocations.create_index([("match_id", 1), ("series_id", 1)], unique=True)
    await db.convocations.create_index("public_link_id", unique=True, sparse=True)

    # attendance current + events
    await db.attendance_current.create_index([("convocation_id", 1), ("player_id", 1)], unique=True)
    await db.attendance_events.create_index([("player_id", 1), ("created_at", -1)])
    await db.attendance_events.create_index([("match_id", 1), ("created_at", -1)])

    # fee rules
    await db.fee_rules.create_index([("scope", 1), ("scope_id", 1), ("active", 1)])

    # monthly charges
    await db.monthly_charges.create_index([("player_id", 1), ("year_month", 1)], unique=True)
    await db.monthly_charges.create_index([("year_month", 1), ("due_date", 1)])
    await db.monthly_charges.create_index([("status", 1), ("due_date", 1)])

    # payments (Payment model - Club Treasury)
    await db.payments.create_index([("player_id", 1), ("created_at", -1)])
    await db.payments.create_index([("status", 1), ("created_at", -1)])
    await db.payments.create_index([("payment_date", -1)])

    # payment_allocations (PaymentAllocation: payment -> fee_charge)
    await db.payment_allocations.create_index([("payment_id", 1)])
    await db.payment_allocations.create_index([("fee_charge_id", 1)])

    # refresh tokens
    await db.refresh_tokens.create_index([("user_id", 1), ("jti", 1)], unique=True)
    await db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)

    # audit
    await db.audit_logs.create_index([("entity_type", 1), ("entity_id", 1), ("created_at", -1)])
    await db.audit_logs.create_index([("actor_user_id", 1), ("created_at", -1)])
    await db.audit_logs.create_index([("action", 1), ("created_at", -1)])

