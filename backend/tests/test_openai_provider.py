"""The OpenAI provider, exercised against a stubbed SDK client (no network)."""

from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel

from app.core.config import get_settings
from app.eligibility.schemas import AttestationMatches
from app.extraction.prompts import load_prompt_set
from app.extraction.schemas import raw_group_model
from app.llm.base import LLMError, LLMNotConfiguredError, LLMRefusalError
from app.llm.budget import BudgetedLLM
from app.llm.factory import get_llm_provider
from app.llm.openai_provider import OpenAIProvider
from app.llm.pricing import estimate_cost_usd
from app.risks.schemas import RiskFindings


class Answer(BaseModel):
    value: str


def _provider(monkeypatch: pytest.MonkeyPatch, outcome: Any) -> tuple[OpenAIProvider, list[Any]]:
    """A provider whose ``responses.parse`` returns (or raises) ``outcome``."""
    provider = OpenAIProvider(model="gpt-6.1-sol", api_key="test-key-not-real")
    calls: list[Any] = []

    def parse(**kwargs: Any) -> Any:
        calls.append(kwargs)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(provider._client.responses, "parse", parse)
    return provider, calls


def _response(
    parsed: Any = None,
    status: str = "completed",
    reason: str | None = None,
    refusal: bool = False,
) -> SimpleNamespace:
    part = (
        SimpleNamespace(type="refusal", refusal="não")
        if refusal
        else SimpleNamespace(type="output_text")
    )
    return SimpleNamespace(
        output=[SimpleNamespace(type="reasoning"), SimpleNamespace(type="message", content=[part])],
        output_parsed=parsed,
        status=status,
        incomplete_details=SimpleNamespace(reason=reason) if reason else None,
        model="gpt-6.1-sol-2026-10-01",
        usage=SimpleNamespace(input_tokens=1234, output_tokens=56),
    )


def _status_error(cls: type[openai.APIStatusError], status: int) -> openai.APIStatusError:
    request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


def test_the_factory_builds_the_configured_provider_and_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_model", None)
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")

    provider = get_llm_provider()

    assert isinstance(provider, OpenAIProvider)
    assert (provider.name, provider.model) == ("openai", "gpt-6.1-sol")


def test_missing_credentials_are_detected_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(LLMNotConfiguredError):
        get_llm_provider()


def test_successful_call_returns_parsed_output_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, calls = _provider(monkeypatch, _response(parsed=Answer(value="ok")))

    result = provider.extract(system="regras", user="edital", schema=Answer)

    assert result.output == Answer(value="ok")
    assert (result.model, result.input_tokens, result.output_tokens) == (
        "gpt-6.1-sol-2026-10-01",
        1234,
        56,
    )
    [call] = calls
    assert call["model"] == "gpt-6.1-sol"
    assert (call["instructions"], call["input"]) == ("regras", "edital")
    assert call["text_format"] is Answer
    assert call["store"] is False  # the edital is not kept on OpenAI's side


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (_response(refusal=True), LLMRefusalError),
        (_response(status="incomplete", reason="max_output_tokens"), LLMError),
        (_response(status="incomplete", reason="content_filter"), LLMError),
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
        (_status_error(openai.AuthenticationError, 401), LLMNotConfiguredError),
        (_status_error(openai.RateLimitError, 429), LLMError),
        (_status_error(openai.InternalServerError, 500), LLMError),
    ],
)
def test_sdk_errors_are_translated(
    monkeypatch: pytest.MonkeyPatch, sdk_error: Exception, error: type[Exception]
) -> None:
    provider, _ = _provider(monkeypatch, sdk_error)

    with pytest.raises(error) as raised:
        provider.extract(system="s", user="u", schema=Answer)
    if error is LLMNotConfiguredError:
        assert "OPENAI_API_KEY" in str(raised.value)  # shown in the interface


def test_an_account_without_credits_gets_a_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    body = {"error": {"code": "credit_balance_exhausted", "message": "no credits"}}
    no_credits = openai.RateLimitError(
        "no credits", response=httpx2.Response(429, request=request), body=body["error"]
    )
    provider, _ = _provider(monkeypatch, no_credits)

    with pytest.raises(LLMError, match="sem créditos"):
        provider.extract(system="s", user="u", schema=Answer)


def test_every_schema_the_app_sends_is_accepted_in_strict_mode() -> None:
    """Structured Outputs needs every field required and no extra properties."""
    groups = load_prompt_set("extraction/v1").groups
    models: list[type[BaseModel]] = [
        raw_group_model(f"Extraction_{g.name}", list(g.fields)) for g in groups
    ]
    models += [RiskFindings, AttestationMatches]

    for model in models:
        schema = to_strict_json_schema(model)
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])


def test_dated_snapshots_are_priced_as_their_model() -> None:
    assert estimate_cost_usd("gpt-6.1-sol-2026-10-01", 1_000_000, 0) == 2.00
    assert estimate_cost_usd("gpt-5.5-pro-2026-01-01", 0, 1_000_000) == 180.00
    assert estimate_cost_usd("gpt-6.1", 1, 1) is None


def test_the_spending_limit_applies_to_openai_models(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, calls = _provider(monkeypatch, _response(parsed=Answer(value="ok")))
    # Worst case of one call: 16 000 output tokens at US$ 10 per million = US$ 0,16.
    budget = BudgetedLLM(provider, limit_usd=0.10, max_output_tokens=16000)

    with pytest.raises(LLMError, match="limite de gasto"):
        budget.extract(system="s", user="u", schema=Answer)
    assert calls == []
