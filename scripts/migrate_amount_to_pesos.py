"""
Migración: montos de "unidades de mil" a "pesos" (campo único amount/paid/credit_balance).

Ejecutar una sola vez si tu BD tiene amount_thousands/paid_thousands:
  python -m scripts.migrate_amount_to_pesos

- fee_rules: amount_thousands → amount (amount = amount_thousands * 1000)
- monthly_charges: amount_thousands → amount, paid_thousands → paid
- payments: amount_thousands → amount
- players: credit_balance_thousands → credit_balance
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.mongo import get_db


async def migrate() -> None:
    db = get_db()

    # fee_rules
    print("Migrating fee_rules amount_thousands → amount...")
    async for doc in db.fee_rules.find({"amount_thousands": {"$exists": True}}):
        val = int(doc["amount_thousands"])
        await db.fee_rules.update_one(
            {"_id": doc["_id"]},
            {"$set": {"amount": val * 1000}, "$unset": {"amount_thousands": ""}},
        )
    print("  done.")

    # monthly_charges
    print("Migrating monthly_charges amount_thousands/paid_thousands → amount/paid...")
    async for doc in db.monthly_charges.find({}):
        updates = {}
        unset = {}
        if "amount_thousands" in doc:
            updates["amount"] = int(doc["amount_thousands"]) * 1000
            unset["amount_thousands"] = ""
        if "paid_thousands" in doc:
            updates["paid"] = int(doc.get("paid_thousands", 0)) * 1000
            unset["paid_thousands"] = ""
        if updates:
            await db.monthly_charges.update_one(
                {"_id": doc["_id"]},
                {"$set": updates, "$unset": unset},
            )
    print("  done.")

    # payments
    print("Migrating payments amount_thousands → amount...")
    async for doc in db.payments.find({"amount_thousands": {"$exists": True}}):
        val = int(doc["amount_thousands"])
        await db.payments.update_one(
            {"_id": doc["_id"]},
            {"$set": {"amount": val * 1000}, "$unset": {"amount_thousands": ""}},
        )
    # applied_to[].amount_thousands → amount
    async for doc in db.payments.find({"applied_to.0": {"$exists": True}}):
        applied = doc.get("applied_to") or []
        if not applied:
            continue
        new_applied = []
        changed = False
        for item in applied:
            if "amount_thousands" in item:
                new_applied.append({
                    "charge_id": item["charge_id"],
                    "amount": int(item["amount_thousands"]) * 1000,
                })
                changed = True
            else:
                new_applied.append(item)
        if changed:
            await db.payments.update_one({"_id": doc["_id"]}, {"$set": {"applied_to": new_applied}})
    print("  done.")

    # players: credit_balance_thousands → credit_balance
    print("Migrating players credit_balance_thousands → credit_balance...")
    async for doc in db.players.find({"credit_balance_thousands": {"$exists": True}}):
        val = int(doc["credit_balance_thousands"])
        await db.players.update_one(
            {"_id": doc["_id"]},
            {"$set": {"credit_balance": val * 1000}, "$unset": {"credit_balance_thousands": ""}},
        )
    print("  done.")

    print("Migration finished.")


if __name__ == "__main__":
    asyncio.run(migrate())
