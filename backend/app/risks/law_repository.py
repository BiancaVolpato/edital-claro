"""Access to the indexed law for the risk analysis.

Two implementations share one interface: the database one (hybrid search, used
by the API) and an in-memory one built from the law file and its cached
embeddings (used by the command-line script, which runs without a database).
"""

from collections import Counter
from functools import lru_cache
from typing import Protocol

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import LawProvision
from app.embeddings.base import EmbeddingProvider, Vectors
from app.law.index import LAW_14133, LAW_14133_FILE, build_embedding_text, law_embedder
from app.law.parser import Provision, parse_law
from app.law.search import search_law
from app.risks.schemas import LegalBasis

_MAX_PER_ARTICLE = 2


class LawRepository(Protocol):
    def get(self, identifier: str) -> LegalBasis | None:
        """The provision with this exact identifier (e.g. "Art. 58, § 1º"), if indexed."""
        ...

    def search(self, query: str, k: int) -> list[LegalBasis]:
        """The provisions that best match ``query``."""
        ...


def _basis(identifier: str, text: str, law: str = LAW_14133) -> LegalBasis:
    return LegalBasis(citation=f"{law}, {identifier}", identifier=identifier, text=text)


class DatabaseLawRepository:
    """Backed by the ``law_provisions`` table (PostgreSQL)."""

    def __init__(self, session: Session, embedder: EmbeddingProvider) -> None:
        self._session = session
        self._embedder = embedder

    def is_indexed(self) -> bool:
        count = self._session.scalar(
            select(func.count()).select_from(LawProvision).where(LawProvision.law == LAW_14133)
        )
        return bool(count)

    def get(self, identifier: str) -> LegalBasis | None:
        text = self._session.scalar(
            select(LawProvision.text).where(
                LawProvision.law == LAW_14133, LawProvision.identifier == identifier
            )
        )
        return _basis(identifier, text) if text is not None else None

    def search(self, query: str, k: int) -> list[LegalBasis]:
        hits = search_law(self._session, query, k, embedder=self._embedder)
        return [_basis(hit.identifier, hit.text) for hit in hits]


@lru_cache
def _parsed_law() -> tuple[list[Provision], Vectors]:
    """Provisions of the law file with their cached embeddings (no model needed)."""
    provisions = [p for p in parse_law(LAW_14133_FILE.read_bytes()) if p.has_content]
    vectors = law_embedder(allow_model=False).embed_passages(
        [build_embedding_text(provision) for provision in provisions]
    )
    return provisions, vectors


class InMemoryLawRepository:
    """Built from the law file; searches by vector similarity only."""

    def __init__(self, embedder: EmbeddingProvider) -> None:
        self._embedder = embedder
        self._provisions, self._vectors = _parsed_law()
        self._by_identifier = {p.identifier: p for p in self._provisions}

    def get(self, identifier: str) -> LegalBasis | None:
        provision = self._by_identifier.get(identifier)
        return _basis(identifier, provision.text) if provision else None

    def search(self, query: str, k: int) -> list[LegalBasis]:
        scores = self._vectors @ self._embedder.embed_queries([query])[0]
        per_article: Counter[int] = Counter()
        hits: list[LegalBasis] = []
        for position in np.argsort(-scores):
            provision = self._provisions[int(position)]
            if per_article[provision.article] < _MAX_PER_ARTICLE:
                per_article[provision.article] += 1
                hits.append(_basis(provision.identifier, provision.text))
            if len(hits) == k:
                break
        return hits
