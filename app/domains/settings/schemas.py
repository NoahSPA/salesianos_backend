"""Esquemas para configuración de marca (logo, color principal)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BrandingOut(BaseModel):
    logo_file_id: str | None = None
    logo_url: str | None = None
    primary_color: str = "#006600"
    app_name: str = "Salesianos FC"


class BrandingUpdate(BaseModel):
    logo_url: str | None = Field(default=None, max_length=2000)
    primary_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    app_name: str | None = Field(default=None, max_length=120)
