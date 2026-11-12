"""Builds the configured LLM provider."""

from app.core.config import get_settings
from app.llm.base import LLMNotConfiguredError, LLMProvider

# Model used when LLM_MODEL is not set (see ADR-016 and ADR-044).
DEFAULT_MODELS = {
    "anthropic": "claude-opus-5-5",
    "openai": "gpt-6.1-sol",
}


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    model = settings.llm_model or DEFAULT_MODELS[settings.llm_provider]
    # SDKs are imported here so only the selected provider's is loaded.
    if settings.llm_provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        key = settings.anthropic_api_key
        return AnthropicProvider(model=model, api_key=key.get_secret_value() if key else None)
    if settings.llm_provider == "openai":
        from app.llm.openai_provider import OpenAIProvider

        key = settings.openai_api_key
        return OpenAIProvider(model=model, api_key=key.get_secret_value() if key else None)
    raise LLMNotConfiguredError(f"unknown LLM provider: {settings.llm_provider}")
