from __future__ import annotations

import re

from pydantic import field_validator

from app.core.schemas import APIModel

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class MatchStatusOut(APIModel):
    """Estado de partido almacenado en BD, con etiqueta y color para badges."""

    code: str
    label: str
    color_hex: str

    @field_validator("color_hex")
    @classmethod
    def color_hex_format(cls, v: str) -> str:
        if not _HEX_COLOR.match(v):
            raise ValueError("color_hex debe ser un color hexadecimal (#RRGGBB)")
        return v
