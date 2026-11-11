"""Provider-neutral interface for structured LLM calls.

The rest of the application depends only on ``LLMProvider``, so switching
vendors (or using a fake in tests) does not touch the extraction code.
"""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


class LLMError(RuntimeError):
    """The call failed or returned something unusable."""


class LLMNotConfiguredError(LLMError):
    """No credentials are available for the configured provider."""


class LLMRefusalError(LLMError):
    """The model declined to answer."""


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    output: T
    model: str  # model that actually served the request
    input_tokens: int
    output_tokens: int


class LLMProvider(Protocol):
    name: str
    model: str

    def extract[T: BaseModel](self, *, system: str, user: str, schema: type[T]) -> LLMResult[T]:
        """Run one call whose answer must validate against ``schema``."""
        ...
