from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from app.core.enums import PaymentStatus
from app.core.schemas import APIModel, DocOut


class PaymentAllocationItem(APIModel):
    """Asignación de un pago a un cargo (fee_charge)."""
    fee_charge_id: str = Field(description="ID del cargo mensual (monthly_charge)")
    amount: int = Field(ge=1, description="Monto aplicado a este cargo en pesos CLP")


class PaymentCreate(APIModel):
    """Registro de un pago. Si no se envían allocations, el tesorero asigna al confirmar."""
    player_id: str
    payment_date: date | None = Field(default=None, description="Fecha del pago (default: hoy)")
    amount_total: int = Field(ge=1, le=1_000_000_000, description="Monto total (se puede enviar como 'amount' por compat)")
    amount: int | None = Field(default=None, ge=1, le=1_000_000_000, description="Alias de amount_total (compat)")
    payment_method: str = Field(default="transfer", max_length=30, description="Método: transfer, cash, etc.")
    reference_number: str | None = Field(default=None, max_length=100, description="Número de transferencia o comprobante")
    transfer_ref: str | None = Field(default=None, max_length=100, description="Alias de reference_number (compat)")
    notes: str | None = Field(default=None, max_length=500)
    notes_player: str | None = Field(default=None, max_length=500, description="Alias de notes (compat)")
    target_month: str | None = Field(default=None, max_length=7, description="YYYY-MM; usado si no se envían allocations")
    tournament_id: str | None = Field(default=None, description="Torneo al que corresponde el pago")
    allocations: list[PaymentAllocationItem] | None = Field(default=None, description="Asignación explícita a cargos (opcional)")
    currency: str = Field(default="CLP", max_length=10, description="Moneda (p. ej. CLP)")

    @model_validator(mode="before")
    @classmethod
    def normalize_amount_and_date(cls, data: dict) -> dict:
        if isinstance(data, dict):
            at = data.get("amount_total") or data.get("amount")
            if at is None:
                raise ValueError("amount_total o amount es requerido")
            data = {**data, "amount_total": int(at)}
            if data.get("payment_date") is None:
                data = {**data, "payment_date": date.today().isoformat()}
            if data.get("reference_number") is None and data.get("transfer_ref") is not None:
                data = {**data, "reference_number": data.get("transfer_ref")}
            if data.get("notes") is None and data.get("notes_player") is not None:
                data = {**data, "notes": data.get("notes_player")}
        return data


class PaymentAllocationOut(APIModel):
    id: str
    payment_id: str
    fee_charge_id: str
    amount_applied: int
    created_at: str | None = None


class PaymentOut(DocOut):
    player_id: str
    amount_total: int
    amount: int = 0  # alias de amount_total (compat frontend)
    currency: str = "CLP"
    status: PaymentStatus
    payment_date: str | None = None
    payment_method: str | None = None
    reference_number: str | None = None
    notes: str | None = None
    notes_treasurer: str | None = None
    allocations: list[PaymentAllocationOut] = Field(default_factory=list)
    created_by_user_id: str
    treasurer_user_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    player_name: str | None = None
    target_month: str | None = None
    tournament_id: str | None = None
    tournament_name: str | None = None
    series_id: str | None = None
    series_name: str | None = None
    receipt_file_id: str | None = Field(default=None, description="ID del comprobante en GridFS")


class PaymentSelfRegisterIn(APIModel):
    """Registro de pago por jugador: identifica por RUT, sin lista de jugadores."""
    rut: str = Field(min_length=7, max_length=15, description="RUT del jugador que paga")
    payment_date: date | None = Field(default=None)
    amount_total: int = Field(ge=1, le=1_000_000_000)
    amount: int | None = Field(default=None, ge=1, le=1_000_000_000)
    payment_method: str = Field(default="transfer", max_length=30)
    reference_number: str | None = Field(default=None, max_length=100)
    transfer_ref: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)
    notes_player: str | None = Field(default=None, max_length=500)
    target_month: str | None = Field(default=None, max_length=7, pattern=r"^\d{4}-\d{2}$")
    currency: str = Field(default="CLP", max_length=10)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: dict) -> dict:
        if isinstance(data, dict):
            at = data.get("amount_total") or data.get("amount")
            if at is None:
                raise ValueError("amount_total o amount es requerido")
            data = {**data, "amount_total": int(at)}
            if data.get("payment_date") is None:
                data = {**data, "payment_date": date.today().isoformat()}
            if data.get("reference_number") is None and data.get("transfer_ref"):
                data = {**data, "reference_number": data.get("transfer_ref")}
            if data.get("notes") is None and data.get("notes_player"):
                data = {**data, "notes": data.get("notes_player")}
        return data


class PaymentValidateIn(APIModel):
    notes_treasurer: str | None = Field(default=None, max_length=300)


class PaymentRejectIn(APIModel):
    notes_treasurer: str | None = Field(default=None, max_length=300)
