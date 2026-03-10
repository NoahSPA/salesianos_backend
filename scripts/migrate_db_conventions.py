"""
Migración: montos en unidades de mil, birth_date como date, period como date.

Ejecutar: python -m scripts.migrate_db_conventions

- fee_rules: amount_cents → amount_thousands (miles de CLP). amount_thousands = amount_cents // 100000
- monthly_charges: amount_cents, paid_cents → amount_thousands, paid_thousands; year_month → period (date)
- payments: amount_cents → amount_thousands
- players: birth_date normalizado a datetime 00:00 (date sin hora)

Conversión montos: amount_cents (centavos, 1500000=15.000 CLP) → amount_thousands = amount_cents // 1000
  (1500000 // 1000 = 1500... no. 15.000 CLP en centavos = 1.500.000. amount_thousands = 15. 
   Entonces: amount_thousands = amount_cents // 100_000)
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.dates import date_to_utc_datetime
from app.db.ids import oid
from app.db.mongo import get_db


def _cents_to_thousands(cents: int) -> int:
    """Centavos (CLP*100) → unidades de mil. 1.500.000 centavos = 15.000 CLP = 15 miles."""
    return max(0, cents // 100_000)


def _to_period_dt(year_month: str):
    """'2025-03' → datetime(2025, 3, 1, 0, 0, 0, tzinfo=UTC)."""
    from datetime import UTC
    parts = year_month.split("-")
    return datetime(int(parts[0]), int(parts[1]), 1, 0, 0, 0, tzinfo=UTC)


async def migrate() -> None:
    db = get_db()

    # 1. fee_rules: amount_cents → amount_thousands
    print("Migrating fee_rules...")
    async for doc in db.fee_rules.find({}):
        old = doc.get("amount_cents")
        if old is not None and "amount_thousands" not in doc:
            thousands = _cents_to_thousands(int(old))
            await db.fee_rules.update_one(
                {"_id": doc["_id"]},
                {"$set": {"amount_thousands": thousands}, "$unset": {"amount_cents": ""}},
            )
    print("  fee_rules done.")

    # 2. monthly_charges: amount_cents, paid_cents → amount_thousands, paid_thousands; year_month → period
    print("Migrating monthly_charges...")
    async for doc in db.monthly_charges.find({}):
        updates = {}
        if "amount_cents" in doc and "amount_thousands" not in doc:
            updates["amount_thousands"] = _cents_to_thousands(int(doc["amount_cents"]))
            updates["$unset"] = updates.get("$unset", {})
            updates["$unset"]["amount_cents"] = ""
        if "paid_cents" in doc and "paid_thousands" not in doc:
            updates["paid_thousands"] = _cents_to_thousands(int(doc.get("paid_cents", 0)))
            updates["$unset"] = updates.get("$unset", {})
            updates["$unset"]["paid_cents"] = ""
        if "year_month" in doc and "period" not in doc:
            updates["period"] = _to_period_dt(doc["year_month"])
            # Mantener year_month para queries (no eliminar)
        if updates:
            unset = updates.pop("$unset", None)
            if unset:
                await db.monthly_charges.update_one({"_id": doc["_id"]}, {"$set": updates, "$unset": unset})
            else:
                await db.monthly_charges.update_one({"_id": doc["_id"]}, {"$set": updates})
    print("  monthly_charges done.")

    # 3. payments: amount_cents → amount_thousands
    print("Migrating payments...")
    async for doc in db.payments.find({}):
        if "amount_cents" in doc and "amount_thousands" not in doc:
            thousands = _cents_to_thousands(int(doc["amount_cents"]))
            await db.payments.update_one(
                {"_id": doc["_id"]},
                {"$set": {"amount_thousands": thousands}, "$unset": {"amount_cents": ""}},
            )
    print("  payments done.")

    # 4. players: birth_date → datetime 00:00 (date)
    print("Migrating players birth_date...")
    async for doc in db.players.find({"birth_date": {"$exists": True, "$ne": None}}):
        bd = doc["birth_date"]
        if hasattr(bd, "date"):
            dt = bd
        else:
            dt = bd
        if hasattr(dt, "hour") and (dt.hour != 0 or dt.minute != 0 or dt.second != 0):
            d = dt.date() if hasattr(dt, "date") else dt
            from datetime import date
            if isinstance(d, datetime):
                d = d.date()
            clean = date_to_utc_datetime(d)
            await db.players.update_one({"_id": doc["_id"]}, {"$set": {"birth_date": clean}})
    print("  players done.")

    print("Migration complete.")


if __name__ == "__main__":
    asyncio.run(migrate())
