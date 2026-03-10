from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta


@dataclass(frozen=True)
class YearMonth:
    year: int
    month: int

    @property
    def key(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def parse_year_month(value: str) -> YearMonth:
    try:
        parts = value.split("-")
        if len(parts) != 2:
            raise ValueError
        year = int(parts[0])
        month = int(parts[1])
        if not (2000 <= year <= 2100):
            raise ValueError
        if not (1 <= month <= 12):
            raise ValueError
        return YearMonth(year=year, month=month)
    except Exception as e:
        raise ValueError("yearMonth inválido (formato YYYY-MM)") from e


def last_day_of_month(ym: YearMonth) -> date:
    first = date(ym.year, ym.month, 1)
    next_month = date(ym.year + 1, 1, 1) if ym.month == 12 else date(ym.year, ym.month + 1, 1)
    return next_month - timedelta(days=1)


def next_year_month(ym: YearMonth) -> YearMonth:
    """Siguiente mes (YYYY-MM). Ej: 2025-12 -> 2026-01."""
    if ym.month == 12:
        return YearMonth(year=ym.year + 1, month=1)
    return YearMonth(year=ym.year, month=ym.month + 1)


def iter_year_months(start_ym: str, end_ym: str):
    """Genera YYYY-MM desde start_ym hasta end_ym (inclusive). Ej: 2026-03, 2026-04, ..., 2026-12."""
    start = parse_year_month(start_ym)
    end = parse_year_month(end_ym)
    ym = start
    while (ym.year, ym.month) <= (end.year, end.month):
        yield ym.key
        if (ym.year, ym.month) == (end.year, end.month):
            break
        ym = next_year_month(ym)


def date_to_utc_datetime(d: date) -> datetime:
    # MongoDB/PyMongo no soporta datetime.date: usar datetime UTC.
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=UTC)


def dt_to_date(value: datetime | date) -> date:
    return value.date() if isinstance(value, datetime) else value

