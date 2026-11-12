"""The Anthropic provider, exercised against a stubbed SDK client (no network)."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import BaseModel

from app.core.config import get_settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMError, LLMNotConfiguredError, LLMRefusalError
from app.llm.factory import get_llm_provider


class Answer(BaseModel):
    value: str


def _provider(monkeypatch: pytest.MonkeyPatch, outcome: Any) -> tuple[AnthropicProvider, list[Any]]:
    """A provider whose ``messages.parse`` returns (or raises) ``outcome``."""
    provider = AnthropicProvider(model="claude-opus-5-5", api_key="test-key-not-real")
    calls: list[Any] = []

    def parse(**kwargs: Any) -> Any:
        calls.append(kwargs)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(provider._client.messages, "parse", parse)
    return provider, calls


def _response(stop_reason: str = "end_turn", parsed: Any = None) -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason,
        parsed_output=parsed,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=1234, output_tokens=56),
    )


def _status_error(cls: type[anthropic.APIStatusError], status: int) -> anthropic.APIStatusError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


def test_missing_credentials_are_detected_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for variable in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(variable, raising=False)
    # The local .env may select another provider.
    monkeypatch.setattr(get_settings(), "llm_provider", "anthropic")
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)

    with pytest.raises(LLMNotConfiguredError):
        get_llm_provider()


def test_successful_call_returns_parsed_output_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, calls = _provider(monkeypatch, _response(parsed=Answer(value="ok")))

    result = provider.extract(system="regras", user="edital", schema=Answer)

    assert result.output == Answer(value="ok")
    assert (result.model, result.input_tokens, result.output_tokens) == (
        "claude-opus-5-5",
        1234,
        56,
    )
    [call] = calls
    assert call["model"] == "claude-opus-5-5"
    assert call["system"] == "regras"
    assert call["messages"] == [{"role": "user", "content": "edital"}]
    assert call["output_format"] is Answer


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (_response(stop_reason="refusal"), LLMRefusalError),
        (_response(stop_reason="max_tokens", parsed=Answer(value="cut")), LLMError),
        (_response(parsed=None), LLMError),
    ],
)
def test_unusable_answers_become_errors(
    monkeypatch: pytest.MonkeyPatch, response: SimpleNamespace, error: type[Exception]
) -> None:
    provider, _ = _provider(monkeypatch, response)

    with pytest.raises(error):
        provider.extract(system="s", user="u", schema=Answer)


@pytest.mark.parametrize(
    ("sdk_error", "error"),
    [
        (_status_error(anthropic.AuthenticationError, 401), LLMNotConfiguredError),
        (_status_error(anthropic.RateLimitError, 429), LLMError),
        (_status_error(anthropic.InternalServerError, 500), LLMError),
    ],
)
def test_sdk_errors_are_translated(
    monkeypatch: pytest.MonkeyPatch, sdk_error: Exception, error: type[Exception]
) -> None:
    provider, _ = _provider(monkeypatch, sdk_error)

    with pytest.raises(error):
        provider.extract(system="s", user="u", schema=Answer)
