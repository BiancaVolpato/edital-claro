"""Builds the configured LLM provider."""

from app.core.config import get_settings
from app.llm.base import LLMNotConfiguredError, LLMProvider


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        # Imported here so the SDK is only loaded when this provider is selected.
        from app.llm.anthropic_provider import AnthropicProvider

        api_key = (
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        )
        return AnthropicProvider(model=settings.llm_model, api_key=api_key)
    raise LLMNotConfiguredError(f"unknown LLM provider: {settings.llm_provider}")
