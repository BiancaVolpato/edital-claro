"""Test doubles for the LLM and the embedding model (no network, no model download)."""

import hashlib
import threading
from collections.abc import Callable
from typing import Any, get_origin

import numpy as np
from pydantic import BaseModel

from app.embeddings.base import Vectors
from app.extraction.prompts import fold
from app.law.index import LAW_14133_FILE
from app.law.parser import parse_law
from app.llm.base import LLMError, LLMResult
from app.risks.schemas import LegalBasis

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

    def __init__(self, dimensions: int = 256) -> None:
        self._dimensions = dimensions
        self.passage_batches: list[int] = []

    def _embed(self, texts: list[str]) -> Vectors:
        vectors = np.zeros((len(texts), self._dimensions), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in fold(text).split():
                bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % self._dimensions
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


class FakeLawRepository:
    """The real text of the Lei 14.133, searched by shared words (no embeddings).

    ``only`` restricts it to some provisions, to test what happens when a
    provision a rule needs is missing from the index. ``search_results`` fixes
    what every search returns, so a test controls the retrieved provisions.
    """

    def __init__(
        self, only: set[str] | None = None, search_results: list[str] | None = None
    ) -> None:
        self._search_results = search_results
        self._texts = {
            p.identifier: p.text
            for p in parse_law(LAW_14133_FILE.read_bytes())
            if p.has_content and (only is None or p.identifier in only)
        }
        self.queries: list[str] = []

    def get(self, identifier: str) -> LegalBasis | None:
        text = self._texts.get(identifier)
        if text is None:
            return None
        return LegalBasis(
            citation=f"Lei 14.133/2021, {identifier}", identifier=identifier, text=text
        )

    def search(self, query: str, k: int) -> list[LegalBasis]:
        self.queries.append(query)
        if self._search_results is not None:
            return [found for i in self._search_results[:k] if (found := self.get(i))]
        words = {word for word in fold(query).split() if len(word) > 3}
        scored = sorted(
            self._texts,
            key=lambda identifier: -len(words & set(fold(self._texts[identifier]).split())),
        )
        return [found for identifier in scored[:k] if (found := self.get(identifier))]
