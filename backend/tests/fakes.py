"""Test doubles for the LLM and the embedding model (no network, no model download)."""

import hashlib
import threading
from collections.abc import Callable
from typing import Any, get_origin

import numpy as np
from pydantic import BaseModel

from app.embeddings.base import Vectors
from app.extraction.prompts import fold
from app.llm.base import LLMError, LLMResult

NOT_FOUND: dict[str, Any] = {"value": None, "citations": [], "confidence": "alta"}


def found(value: Any, page: int, quote: str, confidence: str = "alta") -> dict[str, Any]:
    return {
        "value": value,
        "citations": [{"page": page, "quote": quote}],
        "confidence": confidence,
    }


def empty_answer(schema: type[BaseModel]) -> dict[str, Any]:
    """An answer where nothing was found, valid for any group schema."""
    return {
        name: [] if get_origin(info.annotation) is list else dict(NOT_FOUND)
        for name, info in schema.model_fields.items()
    }


class FakeLLM:
    """Answers each group with a scripted payload and records every call it receives.

    ``answers`` maps a group name to field values (missing fields come back as
    "not found"), to an exception to raise, or to a function of the user
    message that returns either of those.
    """

    name = "fake"

    def __init__(self, answers: dict[str, Any] | None = None, model: str = "claude-opus-5-5"):
        self.model = model
        self.answers = answers or {}
        self.calls: list[dict[str, str]] = []
        self._lock = threading.Lock()

    def extract[T: BaseModel](self, *, system: str, user: str, schema: type[T]) -> LLMResult[T]:
        group = schema.__name__.removeprefix("Extraction_")
        with self._lock:
            self.calls.append({"group": group, "system": system, "user": user})

        answer = self.answers.get(group, {})
        if isinstance(answer, Callable):  # type: ignore[arg-type]
            answer = answer(user)
        if isinstance(answer, Exception):
            raise answer
        payload = {**empty_answer(schema), **answer}
        return LLMResult(
            output=schema.model_validate(payload),
            model=self.model,
            input_tokens=1000,
            output_tokens=200,
        )

    def call_for(self, group: str) -> dict[str, str]:
        return next(call for call in self.calls if call["group"] == group)


class FailingLLM(FakeLLM):
    def __init__(self) -> None:
        super().__init__()

    def extract[T: BaseModel](self, *, system: str, user: str, schema: type[T]) -> LLMResult[T]:
        raise LLMError("service unavailable")


class FakeEmbedder:
    """Deterministic bag-of-words embedding: texts sharing words get similar vectors."""

    model_name = "fake-bag-of-words"
    _DIMENSIONS = 256

    def __init__(self) -> None:
        self.passage_batches: list[int] = []

    def _embed(self, texts: list[str]) -> Vectors:
        vectors = np.zeros((len(texts), self._DIMENSIONS), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in fold(text).split():
                bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % self._DIMENSIONS
                vectors[row, bucket] += 1.0
            norm = float(np.linalg.norm(vectors[row]))
            if norm:
                vectors[row] /= norm
        return vectors

    def embed_passages(self, texts: list[str]) -> Vectors:
        self.passage_batches.append(len(texts))
        return self._embed(texts)

    def embed_queries(self, texts: list[str]) -> Vectors:
        return self._embed(texts)
