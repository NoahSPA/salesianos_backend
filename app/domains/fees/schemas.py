from __future__ import annotations

from datetime import date

from pydantic import Field

from app.core.enums import FeeStatus
from app.core.schemas import APIModel, DocOut


class FeeRuleScope(APIModel):
    scope: str  # 'general' | 'series' | 'player'
    scope_id: str | None = None


class FeeRuleCreate(APIModel):
    scope: str = Field(pattern="^(general|series|player)$")
    scope_id: str | None = None
    tournament_id: str = Field(description="Torneo al que aplica la regla")
    amount: int = Field(ge=0, le=10_000_000, description="Monto mensual en pesos CLP")
    currency: str = Field(default="CLP", max_length=10)
    active: bool = True
    effective_from: date = Field(default_factory=date.today)
    effective_to: date | None = None


class FeeRuleUpdate(APIModel):
    tournament_id: str | None = None
    amount: int | None = Field(default=None, ge=0, le=10_000_000)
    currency: str | None = Field(default=None, max_length=10)
    active: bool | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class FeeRuleOut(DocOut):
    scope: str
    scope_id: str | None = None
    tournament_id: str | None = None
    amount: int
    currency: str
    active: bool
    effective_from: date
    effective_to: date | None = None


class MonthlyChargeOut(DocOut):
    player_id: str
    year_month: str
    due_date: date
    amount: int
    paid: int
    remaining: int
    status: FeeStatus


class PlayerFeeStatusOut(APIModel):
    player_id: str
    player_name: str
    series_id: str
    status: FeeStatus
    fee_amount: int | None = None
    fee_source: str | None = None  # 'general' | 'series' | 'player' | None
    total_pending: int = 0
    pending_months_count: int = 0
    credit_balance: int = 0  # saldo a favor
    total_contributed: int = 0  # valor aportado (suma de pagado en cargos, incl. adelantos)
    paid_months_count: int = 0  # meses con cuota cubierta (incl. adelantos)


class GenerateMonthResult(APIModel):
    year_month: str
    created: int
    skipped_existing: int
    skipped_no_rule: int
