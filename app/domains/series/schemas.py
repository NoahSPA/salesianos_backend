from __future__ import annotations

import re

from pydantic import Field, field_validator

from app.core.schemas import APIModel, DocOut

HEX_COLOR_PATTERN = re.compile(r"^#?[0-9A-Fa-f]{6}$")


def _validate_hex_color(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    v = v.strip()
    if not v:
        return None
    if not HEX_COLOR_PATTERN.match(v):
        raise ValueError("Color debe ser hexadecimal (ej. #3B82F6 o 3B82F6)")
    return v if v.startswith("#") else f"#{v}"


class SeriesCreate(APIModel):
    name: str = Field(min_length=2, max_length=50)
    code: str | None = Field(default=None, max_length=10)
    active: bool = True
    color: str | None = Field(default=None, max_length=7, description="Color hex para badges (ej. #3B82F6)")
    delegate_user_id: str | None = None
    delegate_player_id: str | None = None
    treasurer_user_id: str | None = None
    treasurer_player_id: str | None = None
    whatsapp_group_url: str | None = Field(default=None, max_length=300)

    @field_validator("color")
    @classmethod
    def color_hex(cls, v: str | None) -> str | None:
        return _validate_hex_color(v)


class SeriesUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=50)
    code: str | None = Field(default=None, max_length=10)
    active: bool | None = None
    color: str | None = Field(default=None, max_length=7, description="Color hex para badges (ej. #3B82F6)")
    delegate_user_id: str | None = None
    delegate_player_id: str | None = None
    treasurer_user_id: str | None = None
    treasurer_player_id: str | None = None
    whatsapp_group_url: str | None = Field(default=None, max_length=300)

    @field_validator("color")
    @classmethod
    def color_hex(cls, v: str | None) -> str | None:
        return _validate_hex_color(v)


class SeriesOut(DocOut):
    name: str
    code: str | None = None
    active: bool
    color: str | None = None
    delegate_user_id: str | None = None
    delegate_player_id: str | None = None
    treasurer_user_id: str | None = None
    treasurer_player_id: str | None = None
    whatsapp_group_url: str | None = None

