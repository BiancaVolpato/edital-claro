"""Application settings, loaded from environment variables (and the repo-root .env)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root is three levels above this file's directory.
# Inside the container the file does not exist and settings come from the environment only.
_ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Edital Claro"
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Local development default; real deployments must override it via DATABASE_URL.
    database_url: str = "postgresql+psycopg://edital:edital@localhost:5432/edital_claro"
    database_connect_timeout_seconds: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
