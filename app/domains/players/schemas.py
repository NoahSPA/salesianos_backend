from __future__ import annotations

from datetime import date

from pydantic import Field, field_validator, model_validator

from app.core.schemas import APIModel, DocOut
from app.core.enums import PlayerPosition
from app.core.validators import normalize_rut

# Códigos legacy/alias → código estándar (para input y para normalizar salida desde DB)
POSITION_ALIASES: dict[str, str] = {
    "pt": "gk",
    "gk": "gk",
    "portero": "gk",
    "arquero": "gk",
    "ld": "rb",
    "rb": "rb",
    "lateral derecho": "rb",
    "lateral_derecho": "rb",
    "li": "lb",
    "lb": "lb",
    "lateral izquierdo": "lb",
    "lateral_izquierdo": "lb",
    "dc": "cb",
    "cb": "cb",
    "central": "cb",
    "defensa central": "cb",
    "defensa": "cb",
    "df": "cb",
    "carrilero derecho": "rwb",
            "carrilero_derecho": "rwb",
    "rwb": "rwb",
    "carrilero izquierdo": "lwb",
    "carrilero_izquierdo": "lwb",
    "lwb": "lwb",
    "md": "dm",
    "dm": "dm",
    "medio defensivo": "dm",
    "volante defensivo": "dm",
    "mc": "cm",
    "cm": "cm",
    "medio": "cm",
    "medio campo": "cm",
    "medio centro": "cm",
    "mediocampo": "cm",
    "mo": "am",
    "am": "am",
    "medio ofensivo": "am",
    "volante ofensivo": "am",
    "ed": "rw",
    "rw": "rw",
    "extremo derecho": "rw",
    "ei": "lw",
    "lw": "lw",
    "extremo izquierdo": "lw",
    "delantero": "st",
    "st": "st",
    "delantero centro": "st",
    "9": "st",
    "cf": "cf",
    "segundo delantero": "cf",
    "falso 9": "cf",
}


def _normalize_positions_from_legacy(primary: str | None, secondary: str | None) -> list[PlayerPosition]:
    def one(v: str | None) -> PlayerPosition | None:
        if v is None:
            return None
        s = (v or "").strip().lower()
        if not s:
            return None
        code = POSITION_ALIASES.get(s) or POSITION_ALIASES.get(s.replace("-", " ").replace("_", " ")) or s
        code = code.lower().strip()
        try:
            return PlayerPosition(code)
        except Exception:
            raise ValueError(f"posición inválida: {v!r}. Usa códigos como gk, rb, cb, cm, st.")

    out: list[PlayerPosition] = []
    for v in (one(primary), one(secondary)):
        if v is None:
            continue
        if v not in out:
            out.append(v)
    return out


def normalize_positions_for_output(raw: list) -> list[str]:
    """Convierte códigos legacy en DB (ej. DF) a códigos válidos PlayerPosition para la API."""
    result: list[str] = []
    for x in raw:
        s = (getattr(x, "value", x) if hasattr(x, "value") else str(x)).strip().lower()
        if not s:
            continue
        code = POSITION_ALIASES.get(s) or POSITION_ALIASES.get(s.replace("-", " ").replace("_", " ")) or s
        try:
            result.append(PlayerPosition(code).value)
        except Exception:
            result.append(POSITION_ALIASES.get(s, "cb"))
    return result


def _normalize_level_stars_from_legacy(level: str | None) -> int:
    if level is None:
        return 3
    s = (level or "").strip().lower()
    if not s:
        return 3
    # Si viene como número
    try:
        n = int(s)
        return max(1, min(5, n))
    except Exception:
        pass
    # Palabras comunes
    if s in ("muy bajo", "muybajo"):
        return 1
    if s == "bajo":
        return 2
    if s in ("medio", "media"):
        return 3
    if s == "alto":
        return 4
    if s in ("muy alto", "muyalto", "pro"):
        return 5
    return 3


class PlayerCreate(APIModel):
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    rut: str = Field(min_length=7, max_length=15)
    birth_date: date
    phone: str = Field(min_length=6, max_length=30)

    primary_series_id: str = Field(min_length=1, description="ID de la serie principal")
    series_ids: list[str] = Field(default_factory=list)

    # Nuevo modelo: posiciones múltiples + nivel 1..5
    positions: list[PlayerPosition] | None = None
    level_stars: int | None = Field(default=None, ge=1, le=5)

    # Legacy (compatibilidad): se aceptan pero se normalizan a positions/level_stars
    position_primary: str | None = Field(default=None, min_length=1, max_length=20)
    position_secondary: str | None = Field(default=None, max_length=20)
    level: str | None = Field(default=None, min_length=1, max_length=20)
    active: bool = True
    notes: str | None = Field(default=None, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=500, description="URL de la foto del jugador")

    @field_validator("rut")
    @classmethod
    def _rut(cls, v: str) -> str:
        return normalize_rut(v)

    @field_validator("positions", mode="before")
    @classmethod
    def _positions_normalize(cls, v: list[str] | list[PlayerPosition] | None) -> list[str] | None:
        """Acepta códigos en mayúsculas/minúsculas y los normaliza a minúsculas para el enum."""
        if v is None:
            return None
        out: list[str] = []
        for x in v:
            if isinstance(x, PlayerPosition):
                out.append(x.value)
            elif isinstance(x, str):
                out.append(x.strip().lower() if x.strip() else "")
        return [a for a in out if a]

    @field_validator("series_ids")
    @classmethod
    def _series_nonempty(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys([x for x in v if x]))

    @model_validator(mode="after")
    def _normalize_model(self) -> "PlayerCreate":
        positions = self.positions
        if not positions:
            positions = _normalize_positions_from_legacy(self.position_primary, self.position_secondary)
        if not positions:
            raise ValueError("Debe indicar al menos una posición")
        level_stars = self.level_stars
        if level_stars is None:
            level_stars = _normalize_level_stars_from_legacy(self.level)
        if self.positions == positions and self.level_stars == level_stars:
            return self
        return self.model_copy(update={"positions": positions, "level_stars": level_stars})


class PlayerUpdate(APIModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=50)
    last_name: str | None = Field(default=None, min_length=1, max_length=50)
    rut: str | None = Field(default=None, min_length=7, max_length=15)
    birth_date: date | None = None
    phone: str | None = Field(default=None, min_length=6, max_length=30)

    primary_series_id: str | None = None
    series_ids: list[str] | None = None

    positions: list[PlayerPosition] | None = None
    level_stars: int | None = Field(default=None, ge=1, le=5)

    # Legacy
    position_primary: str | None = Field(default=None, min_length=1, max_length=20)
    position_secondary: str | None = Field(default=None, max_length=20)
    level: str | None = Field(default=None, min_length=1, max_length=20)
    active: bool | None = None
    notes: str | None = Field(default=None, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=500)

    @field_validator("rut")
    @classmethod
    def _rut(cls, v: str | None) -> str | None:
        return normalize_rut(v) if v is not None else None

    @field_validator("positions", mode="before")
    @classmethod
    def _positions_normalize(cls, v: list[str] | list[PlayerPosition] | None) -> list[str] | None:
        if v is None:
            return None
        out: list[str] = []
        for x in v:
            if isinstance(x, PlayerPosition):
                out.append(x.value)
            elif isinstance(x, str):
                out.append(x.strip().lower() if x.strip() else "")
        return [a for a in out if a]

    @model_validator(mode="after")
    def _normalize_model(self) -> "PlayerUpdate":
        positions = self.positions
        if positions is None and (self.position_primary is not None or self.position_secondary is not None):
            positions = _normalize_positions_from_legacy(self.position_primary, self.position_secondary)
        level_stars = self.level_stars
        if level_stars is None and self.level is not None:
            level_stars = _normalize_level_stars_from_legacy(self.level)
        if positions is None and level_stars is None:
            return self
        updates = {}
        if positions is not None:
            updates["positions"] = positions
        if level_stars is not None:
            updates["level_stars"] = level_stars
        return self.model_copy(update=updates)


class PlayerOut(DocOut):
    first_name: str
    last_name: str
    rut: str
    birth_date: date
    phone: str
    primary_series_id: str
    series_ids: list[str]
    positions: list[PlayerPosition]
    level_stars: int = Field(ge=1, le=5)

    # Legacy (solo lectura): para UI antigua / compat
    position_primary: str | None = None
    position_secondary: str | None = None
    level: str | None = None
    active: bool
    notes: str | None = None
    avatar_url: str | None = None
    avatar_file_id: str | None = Field(default=None, description="ID del archivo en GridFS (avatar subido)")


class PlayerImportResult(APIModel):
    inserted: int
    updated: int
    skipped: int
    errors: list[dict] = Field(default_factory=list)

