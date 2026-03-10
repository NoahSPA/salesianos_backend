from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="dev", alias="ENVIRONMENT")

    mongodb_uri: str = Field(alias="MONGODB_URI")
    mongodb_db: str = Field(default="salesianos_fc", alias="MONGODB_DB")

    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_alg: str = Field(default="HS256", alias="JWT_ALG")
    access_token_minutes: int = Field(default=30, alias="ACCESS_TOKEN_MINUTES")
    refresh_token_days: int = Field(default=30, alias="REFRESH_TOKEN_DAYS")

    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    cookie_domain: str = Field(default="", alias="COOKIE_DOMAIN")

    cors_origins: str = Field(default="", alias="CORS_ORIGINS")

    bootstrap_token: str = Field(default="", alias="BOOTSTRAP_TOKEN")

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

