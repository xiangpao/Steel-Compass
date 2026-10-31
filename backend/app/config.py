from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
