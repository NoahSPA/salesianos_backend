from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from pydantic import Field
from pydantic import field_validator

from app.core.schemas import APIModel, DocOut


class TournamentLocation(APIModel):
    name: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=200)
    map_url: str | None = Field(default=None, max_length=500)
    lat: float | None = None
    lng: float | None = None

    @field_validator("map_url")
    @classmethod
    def _validate_map_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        u = (v or "").strip()
        if not u:
            return None
        p = urlparse(u)
        if p.scheme not in ("http", "https"):
            raise ValueError("map_url inválida")
        host = (p.netloc or "").lower()
        # Permitimos links típicos de Google Maps
        allowed = ("maps.app.goo.gl", "www.google.com", "google.com", "goo.gl")
        if not any(host == a or host.endswith("." + a) for a in allowed):
            raise ValueError("map_url debe ser de Google Maps")
        return u


def _year_month_pattern() -> str:
    return r"^\d{4}-(0[1-9]|1[0-2])$"


class TournamentCreate(APIModel):
    name: str = Field(min_length=2, max_length=80)
    season_year: int = Field(ge=2000, le=2100)
    league: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    start_date: date | None = None
    end_date: date | None = None
    start_month: str | None = Field(default=None, pattern=_year_month_pattern(), description="Mes inicio período cuotas (YYYY-MM)")
    end_month: str | None = Field(default=None, pattern=_year_month_pattern(), description="Mes término período cuotas (YYYY-MM)")
    active: bool = True
    series_ids: list[str] = Field(default_factory=list)
    location: TournamentLocation | None = None


class TournamentUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    season_year: int | None = Field(default=None, ge=2000, le=2100)
    league: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    start_date: date | None = None
    end_date: date | None = None
    start_month: str | None = Field(default=None, pattern=_year_month_pattern())
    end_month: str | None = Field(default=None, pattern=_year_month_pattern())
    active: bool | None = None
    series_ids: list[str] | None = None
    location: TournamentLocation | None = None


class TournamentOut(DocOut):
    name: str
    season_year: int
    league: str | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    start_month: str | None = None
    end_month: str | None = None
    active: bool
    series_ids: list[str]
    location: TournamentLocation | None = None

