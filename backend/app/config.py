from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="STEEL_COMPASS_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = "sqlite:///./steel_compass.db"
    frontend_origin: str = "http://localhost:3000"
    cookie_name: str = "steel_compass_session"
    cookie_secure: bool = False
    session_hours: int = Field(default=12, ge=1, le=168)
    bootstrap_admin_username: str | None = None
    bootstrap_admin_password: str | None = None
    # Worker processes for independent load-combination analyses; 1 = serial.
    analysis_workers: int = Field(default=4, ge=1, le=32)
    # Explicit opt-out for a production deployment served over plain HTTP
    # beyond loopback (e.g. an isolated LAN host).
    allow_insecure_cookie: bool = False

    @model_validator(mode="after")
    def require_secure_cookie_in_production(self) -> "Settings":
        if self.environment.lower() != "production" or self.cookie_secure or self.allow_insecure_cookie:
            return self
        origin = urlsplit(self.frontend_origin)
        # Local Docker serves http://127.0.0.1, where browsers reject Secure cookies.
        if origin.scheme == "http" and origin.hostname in _LOOPBACK_HOSTS:
            return self
        raise ValueError(
            "production requires STEEL_COMPASS_COOKIE_SECURE=true unless "
            "STEEL_COMPASS_FRONTEND_ORIGIN is http on 127.0.0.1/localhost "
            f"(got {self.frontend_origin!r}); set STEEL_COMPASS_ALLOW_INSECURE_COOKIE=true "
            "only for an intentional plain-HTTP deployment"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
