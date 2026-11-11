"""Recall evaluation of the law search against a set of known questions."""

import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.embeddings.base import EmbeddingProvider, get_embedding_provider
from app.embeddings.cache import CachedEmbeddings
from app.law.search import LawHit, SearchMode, search_law

EVAL_DIR = Path(__file__).resolve().parents[3] / "eval" / "law_search"
QUESTIONS_FILE = EVAL_DIR / "questions.json"
# Embeddings of the evaluation questions, so the evaluation runs without the model.
QUERY_EMBEDDINGS_FILE = EVAL_DIR / "query_embeddings.npz"
MODES: tuple[SearchMode, ...] = ("hybrid", "vector", "lexical")


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    expected_articles: list[int]


@dataclass(frozen=True)
class QuestionResult:
    question: Question
    hits: list[LawHit]

    @property
    def rank(self) -> int | None:
        """1-based position of the first hit from an expected article, if any."""
        for position, hit in enumerate(self.hits, start=1):
            if hit.article in self.question.expected_articles:
                return position
        return None


def load_questions() -> list[Question]:
    data = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    return [
        Question(item["id"], item["question"], item["expected_articles"])
        for item in data["questions"]
    ]


def query_embedder(allow_model: bool = True) -> CachedEmbeddings:
    return CachedEmbeddings(
        get_settings().embedding_model,
        QUERY_EMBEDDINGS_FILE,
        get_embedding_provider if allow_model else None,
    )


def evaluate(
    session: Session, embedder: EmbeddingProvider, mode: SearchMode, k: int = 5
) -> list[QuestionResult]:
    return [
        QuestionResult(
            question, search_law(session, question.question, k, mode=mode, embedder=embedder)
        )
        for question in load_questions()
    ]


def recall(results: list[QuestionResult]) -> float:
    """Share of questions whose expected article appears among the returned hits."""
    return sum(1 for result in results if result.rank is not None) / len(results)


def mean_reciprocal_rank(results: list[QuestionResult]) -> float:
    return sum(1 / result.rank for result in results if result.rank) / len(results)
