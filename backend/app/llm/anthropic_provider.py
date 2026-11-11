"""Claude (Anthropic API) implementation of ``LLMProvider``."""

import anthropic
from pydantic import BaseModel

from app.llm.base import LLMError, LLMNotConfiguredError, LLMProvider, LLMRefusalError, LLMResult

# Non-streaming requests: large enough for the longest group (qualification lists)
# while staying well inside the SDK's HTTP timeout.
_MAX_TOKENS = 16000


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        try:
            # Without an explicit key the SDK resolves credentials from the environment.
            self._client = (
                anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
            )
        except anthropic.AnthropicError as exc:
            raise LLMNotConfiguredError("no Anthropic credentials found") from exc
        # The SDK only complains about missing credentials when a request is sent.
        # Checking now lets the API refuse the analysis up front instead of
        # accepting it and failing later.
        client = self._client
        if not (client.api_key or client.auth_token or client.credentials):
            raise LLMNotConfiguredError("no Anthropic credentials found")

    def extract[T: BaseModel](self, *, system: str, user: str, schema: type[T]) -> LLMResult[T]:
        try:
            # Structured outputs: the API constrains the answer to the schema and
            # the SDK validates it into the Pydantic model.
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
            )
        except anthropic.AuthenticationError as exc:
            raise LLMNotConfiguredError("Anthropic API key was rejected") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("rate limited by the Anthropic API") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("could not reach the Anthropic API") from exc

        if response.stop_reason == "refusal":
            raise LLMRefusalError("the model declined to process this content")
        if response.stop_reason == "max_tokens":
            raise LLMError("the answer was cut off at the output token limit")
        if response.parsed_output is None:
            raise LLMError("the model returned no structured output")

        return LLMResult(
            output=response.parsed_output,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
