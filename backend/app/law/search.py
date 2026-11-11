"""Hybrid search over the indexed law: vector similarity plus PostgreSQL full-text.

The two signals fail in different ways. Embeddings find provisions that say the
same thing in other words ("vistoria" for "visita técnica") but blur exact
terms; term matching nails legal terms and numbers but misses paraphrases.
Each produces a ranking and the two are merged with reciprocal rank fusion
(RRF), which only uses positions and so needs no calibration between a cosine
distance and a text-rank score.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.db.models import LAW_EMBEDDING_DIMENSIONS
from app.embeddings.base import EmbeddingProvider, get_embedding_provider
from app.law.index import LAW_14133

SearchMode = Literal["hybrid", "vector", "lexical"]

# Standard RRF constant: dampens the difference between neighbouring ranks.
_RRF_K = 60
# How many candidates each ranking contributes before fusion.
_CANDIDATE_POOL = 50

# How many provisions of the same article may appear in one result list. Without
# a cap, the incisos of a single long article can fill every position.
_MAX_PER_ARTICLE = 2

# Lexical ranking: PostgreSQL's own ts_rank has no notion of how rare a term
# is, so questions were dominated by words such as "contrato" and "obra", and by
# long provisions. Here each stemmed term of the question is weighted by its
# inverse document frequency (the IDF of BM25) and a provision scores the sum of
# the weights of the terms it contains. Term frequency is ignored: provisions
# are short, so a term appearing twice says little.
_SEARCH_SQL = text(
    """
    WITH terms AS (
        SELECT unnest(tsvector_to_array(to_tsvector('portuguese', :query))) AS lexeme
    ),
    corpus AS (
        SELECT count(*)::float AS size FROM law_provisions WHERE law = :law
    ),
    weights AS (
        SELECT t.lexeme,
               ln(1 + (c.size - s.ndoc + 0.5) / (s.ndoc + 0.5)) AS idf
        FROM terms t
        JOIN ts_stat(format('SELECT search FROM law_provisions WHERE law = %L', :law)) s
          ON s.word = t.lexeme
        CROSS JOIN corpus c
    ),
    lexical_scores AS (
        SELECT p.id, sum(w.idf) AS score
        FROM law_provisions p
        JOIN weights w ON p.search @@ to_tsquery('simple', quote_literal(w.lexeme))
        WHERE p.law = :law AND :use_lexical
        GROUP BY p.id
    ),
    lexical AS (
        SELECT id, row_number() OVER (ORDER BY score DESC, id) AS rank
        FROM lexical_scores
        ORDER BY score DESC, id
        LIMIT :pool
    ),
    semantic AS (
        SELECT id, row_number() OVER (ORDER BY embedding <=> :vector) AS rank
        FROM law_provisions
        WHERE law = :law AND :use_vector
        ORDER BY embedding <=> :vector
        LIMIT :pool
    )
    SELECT p.identifier, p.kind, p.article, p.heading, p.text,
           COALESCE(1.0 / (:rrf_k + s.rank), 0) + COALESCE(1.0 / (:rrf_k + l.rank), 0) AS score,
           s.rank AS semantic_rank, l.rank AS lexical_rank
    FROM law_provisions p
    LEFT JOIN semantic s ON s.id = p.id
    LEFT JOIN lexical l ON l.id = p.id
    WHERE s.id IS NOT NULL OR l.id IS NOT NULL
    ORDER BY score DESC, p.position
    """
).bindparams(bindparam("vector", type_=Vector(LAW_EMBEDDING_DIMENSIONS)))


@dataclass(frozen=True)
class LawHit:
    law: str
    identifier: str  # e.g. "Art. 67, § 1º"
    kind: str
    article: int
    heading: str
    text: str
    score: float
    semantic_rank: int | None  # position in the vector ranking, if it appeared there
    lexical_rank: int | None  # position in the full-text ranking, if it appeared there

    @property
    def citation(self) -> str:
        return f"{self.law}, {self.identifier}"


def search_law(
    session: Session,
    query: str,
    k: int = 5,
    *,
    mode: SearchMode = "hybrid",
    law: str = LAW_14133,
    embedder: EmbeddingProvider | None = None,
) -> list[LawHit]:
    """Return the ``k`` provisions of the law that best match ``query``."""
    if not query.strip() or k <= 0:
        return []

    use_vector = mode in ("hybrid", "vector")
    if use_vector:
        embedder = embedder or get_embedding_provider()
        vector = embedder.embed_queries([query])[0].tolist()
    else:
        vector = [0.0] * LAW_EMBEDDING_DIMENSIONS

    rows = session.execute(
        _SEARCH_SQL,
        {
            "query": query,
            "vector": vector,
            "law": law,
            "use_vector": use_vector,
            "use_lexical": mode in ("hybrid", "lexical"),
            "pool": _CANDIDATE_POOL,
            "rrf_k": _RRF_K,
        },
    ).all()

    # Take the best rows, at most _MAX_PER_ARTICLE from each article.
    per_article: Counter[int] = Counter()
    selected = []
    for row in rows:
        if per_article[row.article] < _MAX_PER_ARTICLE:
            per_article[row.article] += 1
            selected.append(row)
        if len(selected) == k:
            break

    return [
        LawHit(
            law=law,
            identifier=row.identifier,
            kind=row.kind,
            article=row.article,
            heading=row.heading,
            text=row.text,
            score=float(row.score),
            semantic_rank=row.semantic_rank,
            lexical_rank=row.lexical_rank,
        )
        for row in selected
    ]
