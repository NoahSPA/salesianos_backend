from __future__ import annotations

from datetime import date
from pydantic import ConfigDict, Field, field_validator, model_validator

from app.core.schemas import APIModel, DocOut
from app.core.enums import PlayerPosition

TALLA_CHOICES: tuple[str, ...] = ("XS", "S", "M", "L", "XL", "XXL", "XXXL")
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
    first_name: str = Field(min_length=1, max_length=50, description="Primer nombre")
    second_first_name: str | None = Field(default=None, max_length=50, description="Segundo nombre")
    last_name: str = Field(min_length=1, max_length=50, description="Primer apellido")
    second_last_name: str | None = Field(default=None, max_length=50, description="Segundo apellido")
    rut: str | None = Field(default=None, min_length=7, max_length=15, description="Opcional para jugadores en memoria")
    birth_date: date | None = Field(default=None, description="Opcional para jugadores en memoria")
    phone: str | None = Field(default=None, min_length=6, max_length=30, description="Opcional para jugadores en memoria")
    email: str | None = Field(default=None, max_length=255)

    primary_series_id: str | None = Field(default=None, description="ID serie principal. Opcional para jugadores en memoria")
    series_ids: list[str] = Field(default_factory=list)

    dorsal: int | None = Field(default=None, ge=1, le=99, description="Número de camiseta")
    talla: str | None = Field(default=None, max_length=10, description="Talla de camiseta (XS, S, M, L, XL, XXL, XXXL)")

    # Nuevo modelo: posiciones múltiples + nivel 1..5
    positions: list[PlayerPosition] | None = None
    level_stars: int | None = Field(default=None, ge=1, le=5)

    # Legacy (compatibilidad): se aceptan pero se normalizan a positions/level_stars
    position_primary: str | None = Field(default=None, min_length=1, max_length=20)
    position_secondary: str | None = Field(default=None, max_length=20)
    level: str | None = Field(default=None, min_length=1, max_length=20)
    active: bool = True
    in_memoriam: bool = Field(default=False, description="Jugador fallecido, en memoria")
    notes: str | None = Field(default=None, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=500, description="URL de la foto del jugador")

    @field_validator("rut")
    @classmethod
    def _rut(cls, v: str | None) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return normalize_rut(v)

    @field_validator("talla")
    @classmethod
    def _talla(cls, v: str | None) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        s = v.strip().upper()
        if s in TALLA_CHOICES:
            return s
        raise ValueError(f"Talla inválida: {v!r}. Usa: XS, S, M, L, XL, XXL, XXXL")

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
        if not self.in_memoriam:
            if not self.rut or not self.rut.strip():
                raise ValueError("RUT es obligatorio")
            if self.birth_date is None:
                raise ValueError("Fecha de nacimiento es obligatoria")
            if not self.phone or not str(self.phone).strip():
                raise ValueError("Teléfono es obligatorio")
            if not self.primary_series_id or not str(self.primary_series_id).strip():
                raise ValueError("Serie principal es obligatoria")
        else:
            updates: dict = {}
            if self.rut is None or (isinstance(self.rut, str) and not self.rut.strip()):
                updates["rut"] = "11111111-1"
            if self.birth_date is None:
                updates["birth_date"] = date(1900, 1, 1)
            if self.phone is None or (isinstance(self.phone, str) and not str(self.phone).strip()):
                updates["phone"] = "00000000"
            if updates:
                self = self.model_copy(update=updates)
        positions = self.positions
        if not positions:
            positions = _normalize_positions_from_legacy(self.position_primary, self.position_secondary)
        if not positions:
            positions = [PlayerPosition.cm]
        level_stars = self.level_stars
        if level_stars is None:
            level_stars = _normalize_level_stars_from_legacy(self.level)
        return self.model_copy(update={"positions": positions, "level_stars": level_stars})


class PlayerUpdate(APIModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=50)
    second_first_name: str | None = Field(default=None, max_length=50)
    last_name: str | None = Field(default=None, min_length=1, max_length=50)
    second_last_name: str | None = Field(default=None, max_length=50)
    rut: str | None = Field(default=None, min_length=7, max_length=15)
    birth_date: date | None = None
    phone: str | None = Field(default=None, min_length=6, max_length=30)
    email: str | None = Field(default=None, max_length=255)

    primary_series_id: str | None = None
    series_ids: list[str] | None = None

    dorsal: int | None = Field(default=None, ge=1, le=99)
    talla: str | None = Field(default=None, max_length=10)

    positions: list[PlayerPosition] | None = None
    level_stars: int | None = Field(default=None, ge=1, le=5)

    # Legacy
    position_primary: str | None = Field(default=None, min_length=1, max_length=20)
    position_secondary: str | None = Field(default=None, max_length=20)
    level: str | None = Field(default=None, min_length=1, max_length=20)
    active: bool | None = None
    in_memoriam: bool | None = None
    notes: str | None = Field(default=None, max_length=500)
    avatar_url: str | None = Field(default=None, max_length=500)

    @field_validator("rut")
    @classmethod
    def _rut(cls, v: str | None) -> str | None:
        return normalize_rut(v) if v is not None else None

    @field_validator("talla")
    @classmethod
    def _talla(cls, v: str | None) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        s = v.strip().upper()
        if s in TALLA_CHOICES:
            return s
        raise ValueError(f"Talla inválida: {v!r}. Usa: XS, S, M, L, XL, XXL, XXXL")

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
    """Schema de salida de jugador. Ignora campos extra del documento para evitar extra_forbidden."""
    model_config = ConfigDict(extra="ignore")

    first_name: str
    second_first_name: str | None = None
    last_name: str
    second_last_name: str | None = None
    rut: str
    birth_date: date
    phone: str
    email: str | None = None
    primary_series_id: str
    series_ids: list[str]
    positions: list[PlayerPosition]
    level_stars: int = Field(ge=1, le=5)

    dorsal: int | None = Field(default=None, description="Número de camiseta")
    talla: str | None = Field(default=None, description="Talla de camiseta (XS, S, M, L, XL, XXL, XXXL)")

    # Legacy (solo lectura): para UI antigua / compat
    position_primary: str | None = None
    position_secondary: str | None = None
    level: str | None = None
    active: bool
    in_memoriam: bool = Field(default=False, description="Jugador fallecido, en memoria")
    notes: str | None = None
    avatar_url: str | None = None
    avatar_file_id: str | None = Field(default=None, description="ID del archivo en GridFS (avatar subido)")


class PlayerImportResult(APIModel):
    inserted: int
    updated: int
    skipped: int
    errors: list[dict] = Field(default_factory=list)

