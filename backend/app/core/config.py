"""Application settings, loaded from environment variables (and the repo-root .env)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repo root is three levels above this file's directory.
# Inside the container the file does not exist and settings come from the environment only.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ROOT_ENV_FILE = _REPO_ROOT / ".env"


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

    # Where uploaded PDFs are kept (named by their sha256, never by the client's filename).
    storage_dir: Path = _REPO_ROOT / "data" / "uploads"
    max_upload_mb: int = 50

    # Tesseract language pack used by the OCR fallback.
    ocr_language: str = "por"
    ocr_timeout_seconds: int = 600
    # Upper bound for a chunk, sized to fit the embedding model's input window.
    chunk_max_chars: int = 2000

    # LLM used for extraction. The key is read from ANTHROPIC_API_KEY and never logged.
    llm_provider: Literal["anthropic"] = "anthropic"
    llm_model: str = "claude-opus-5-5"
    anthropic_api_key: SecretStr | None = None
    # How many extraction calls of one analysis may run at the same time.
    llm_max_concurrency: int = 3
    # Local embedding model used to locate the relevant sections of an edital.
    embedding_model: str = "intfloat/multilingual-e5-base"
    # Versioned prompt set (a folder under backend/prompts/).
    extraction_prompt_version: str = "extraction/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
