"""OpenAI (Responses API) implementation of ``LLMProvider``.

Uses Structured Outputs through the SDK's ``responses.parse``: the Pydantic
schema becomes a strict JSON schema, the API constrains the answer to it and
the SDK validates it back into the model. ``store=False`` keeps the edital text
out of OpenAI's stored responses.
"""

import openai
import pydantic
from pydantic import BaseModel

from app.llm.base import (
    MAX_OUTPUT_TOKENS,
    LLMError,
    LLMNotConfiguredError,
    LLMProvider,
    LLMRefusalError,
    LLMResult,
)

# Shown in the interface, so in Portuguese.
REJECTED_KEY_MESSAGE = (
    "A OpenAI recusou a chave da API. Confira OPENAI_API_KEY no .env: as chaves são "
    "criadas em platform.openai.com e a conta precisa ter créditos."
)
NO_CREDITS_MESSAGE = (
    "A conta da OpenAI está sem créditos. Adicione créditos em "
    "platform.openai.com/settings/organization/billing e tente de novo."
)
# Error codes of a 429 that mean the account has no credits, not a passing rate limit.
_NO_CREDIT_CODES = {"insufficient_quota", "credit_balance_exhausted"}


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        try:
            # Without an explicit key the SDK reads OPENAI_API_KEY from the environment.
            self._client = openai.OpenAI(api_key=api_key) if api_key else openai.OpenAI()
        except openai.OpenAIError as exc:
            raise LLMNotConfiguredError("no OpenAI credentials found") from exc

    def extract[T: BaseModel](self, *, system: str, user: str, schema: type[T]) -> LLMResult[T]:
        try:
            response = self._client.responses.parse(
                model=self.model,
                instructions=system,
                input=user,
                text_format=schema,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                store=False,
            )
        except openai.AuthenticationError as exc:
            raise LLMNotConfiguredError(REJECTED_KEY_MESSAGE) from exc
        except openai.RateLimitError as exc:
            if exc.code in _NO_CREDIT_CODES:
                raise LLMError(NO_CREDITS_MESSAGE) from exc
            raise LLMError("rate limited by the OpenAI API") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"OpenAI API error {exc.status_code}: {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise LLMError("could not reach the OpenAI API") from exc
        except pydantic.ValidationError as exc:
            raise LLMError("the model's answer did not match the expected schema") from exc

        for item in response.output:
            if item.type != "message":
                continue
            for part in item.content:
                if part.type == "refusal":
                    raise LLMRefusalError("the model declined to process this content")
        if response.status == "incomplete":
            reason = response.incomplete_details.reason if response.incomplete_details else None
            if reason == "max_output_tokens":
                raise LLMError("the answer was cut off at the output token limit")
            raise LLMError(f"the answer is incomplete ({reason})")
        if response.output_parsed is None:
            raise LLMError("the model returned no structured output")
        if response.usage is None:
            raise LLMError("the API returned no token usage")

        return LLMResult(
            output=response.output_parsed,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
