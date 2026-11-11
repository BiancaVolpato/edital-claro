"""Law index and hybrid search. These need PostgreSQL (pgvector + full-text search)."""

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.db.models import LAW_EMBEDDING_DIMENSIONS, LawProvision
from app.embeddings.cache import CachedEmbeddings, EmbeddingCacheMissError
from app.law.evaluation import MODES, evaluate, load_questions, query_embedder, recall
from app.law.index import LAW_14133, LAW_14133_FILE, index_law, law_embedder
from app.law.search import search_law
from tests.conftest import USE_POSTGRES
from tests.fakes import FakeEmbedder
from tests.test_law_parser import SAMPLE_HTML

needs_postgres = pytest.mark.skipif(not USE_POSTGRES, reason="needs PostgreSQL (RUN_DB_TESTS=1)")

SAMPLE_LAW = "Lei 99.999/2030"


@pytest.fixture
def sample_index(db_engine: Engine) -> Iterator[Session]:
    """The small synthetic law, indexed with the fake embedder."""
    with Session(db_engine) as session:
        index_law(session, SAMPLE_HTML, FakeEmbedder(LAW_EMBEDDING_DIMENSIONS), law=SAMPLE_LAW)
        yield session
        session.execute(delete(LawProvision).where(LawProvision.law == SAMPLE_LAW))
        session.commit()


@pytest.fixture(scope="module")
def law_index(_postgres_engine: Engine | None) -> Iterator[Session]:
    """The real Lei 14.133, indexed once from the committed embedding cache (no model)."""
    assert _postgres_engine is not None
    with Session(_postgres_engine) as session:
        index_law(session, LAW_14133_FILE.read_bytes(), law_embedder(allow_model=False))
        yield session
        session.execute(delete(LawProvision).where(LawProvision.law == LAW_14133))
        session.commit()


# --- Embedding cache (no database needed) -------------------------------------


def test_cache_computes_once_and_reloads_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "cache.npz"
    inner = FakeEmbedder()
    cache = CachedEmbeddings("fake-bag-of-words", path, lambda: inner)

    first = cache.embed_passages(["garantia de proposta", "prazo de execução"])
    cache.embed_passages(["garantia de proposta"])
    assert inner.passage_batches == [2]  # the second call was served from memory
    assert cache.save() is True
    assert cache.save() is False  # nothing new to write

    reloaded = CachedEmbeddings("fake-bag-of-words", path, None)
    again = reloaded.embed_passages(["garantia de proposta", "prazo de execução"])
    # Stored as float16: equal up to that precision, and still unit vectors.
    assert np.allclose(first, again, atol=1e-3)
    assert np.allclose(np.linalg.norm(again, axis=1), 1.0, atol=1e-5)


def test_cache_distinguishes_passages_from_queries(tmp_path: Path) -> None:
    cache = CachedEmbeddings("fake-bag-of-words", tmp_path / "cache.npz", None)
    cache._vectors.clear()

    with pytest.raises(EmbeddingCacheMissError):
        cache.embed_queries(["texto que nunca foi calculado"])


def test_cache_built_with_another_model_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "cache.npz"
    cache = CachedEmbeddings("model-a", path, lambda: FakeEmbedder())
    cache.embed_passages(["texto"])
    cache.save()

    with pytest.raises(ValueError, match="model-a"):
        CachedEmbeddings("model-b", path, None)


def test_committed_cache_covers_the_whole_law_and_the_eval_questions() -> None:
    """If this fails, the law text or the questions changed: rebuild the caches."""
    from app.law.index import build_embedding_text
    from app.law.parser import parse_law

    provisions = [p for p in parse_law(LAW_14133_FILE.read_bytes()) if p.has_content]
    contexts = [build_embedding_text(provision) for provision in provisions]

    vectors = law_embedder(allow_model=False).embed_passages(contexts)
    queries = query_embedder(allow_model=False).embed_queries(
        [question.question for question in load_questions()]
    )

    assert vectors.shape == (len(contexts), LAW_EMBEDDING_DIMENSIONS)
    assert queries.shape == (10, LAW_EMBEDDING_DIMENSIONS)


# --- Index and search on a small synthetic law --------------------------------


@needs_postgres
def test_index_stores_provisions_without_vetoed_ones(sample_index: Session) -> None:
    rows = sample_index.execute(
        select(
            LawProvision.identifier, LawProvision.kind, LawProvision.article, LawProvision.parent
        )
        .where(LawProvision.law == SAMPLE_LAW)
        .order_by(LawProvision.position)
    ).all()

    assert len(rows) == 12
    assert rows[3] == ("Art. 1º, II, a", "alinea", 1, "Art. 1º, II")


@needs_postgres
def test_reindexing_replaces_the_previous_index(sample_index: Session) -> None:
    index_law(sample_index, SAMPLE_HTML, FakeEmbedder(LAW_EMBEDDING_DIMENSIONS), law=SAMPLE_LAW)

    count = sample_index.scalar(
        select(func.count()).select_from(LawProvision).where(LawProvision.law == SAMPLE_LAW)
    )
    assert count == 12


@needs_postgres
def test_index_rejects_an_embedding_model_of_another_size(db_engine: Engine) -> None:
    with Session(db_engine) as session, pytest.raises(ValueError, match="768"):
        index_law(session, SAMPLE_HTML, FakeEmbedder(64), law=SAMPLE_LAW)


@needs_postgres
@pytest.mark.parametrize("mode", MODES)
def test_search_finds_the_matching_provision_in_every_mode(
    sample_index: Session, mode: str
) -> None:
    hits = search_law(
        sample_index,
        "Admite-se seguro-garantia.",
        3,
        mode=mode,  # type: ignore[arg-type]
        law=SAMPLE_LAW,
        embedder=FakeEmbedder(LAW_EMBEDDING_DIMENSIONS),
    )

    assert hits[0].identifier == "Art. 2º, parágrafo único"
    assert hits[0].citation == "Lei 99.999/2030, Art. 2º, parágrafo único"
    assert hits[0].heading.endswith("Seção I - Da garantia")


@needs_postgres
def test_lexical_search_stems_and_ignores_accents_of_inflected_words(sample_index: Session) -> None:
    # "garantias" (plural) must match "garantia" through Portuguese stemming.
    hits = search_law(sample_index, "garantias", 5, mode="lexical", law=SAMPLE_LAW)

    # Article 2 holds the word; the later articles only inherit it from the section title.
    assert {hit.article for hit in hits[:2]} == {2}
    assert all(hit.semantic_rank is None and hit.lexical_rank for hit in hits)


@needs_postgres
def test_rare_terms_outweigh_common_ones(sample_index: Session) -> None:
    """IDF weighting: "atestado" (rare) decides, not "documentos" (common)."""
    hits = search_law(sample_index, "documentos atestado", 2, mode="lexical", law=SAMPLE_LAW)

    assert hits[0].identifier in ("Art. 1º, II, a", "Art. 1º, § 1º")


@needs_postgres
def test_results_are_capped_per_article(sample_index: Session) -> None:
    hits = search_law(
        sample_index,
        "habilitação documentos",
        5,
        law=SAMPLE_LAW,
        embedder=FakeEmbedder(LAW_EMBEDDING_DIMENSIONS),
    )

    per_article = [sum(1 for hit in hits if hit.article == article) for article in {1, 2, 3, 4}]
    assert max(per_article) <= 2


@needs_postgres
def test_empty_or_stopword_only_queries_return_nothing(sample_index: Session) -> None:
    assert search_law(sample_index, "   ", 5, law=SAMPLE_LAW) == []
    assert search_law(sample_index, "de a o que", 5, mode="lexical", law=SAMPLE_LAW) == []
    assert search_law(sample_index, "garantia", 0, mode="lexical", law=SAMPLE_LAW) == []


@needs_postgres
def test_other_laws_are_not_mixed_into_the_results(sample_index: Session) -> None:
    assert search_law(sample_index, "garantia", 5, mode="lexical", law="Lei inexistente") == []


@needs_postgres
def test_search_endpoint(client: TestClient, sample_index: Session) -> None:
    assert client.get("/law/search", params={"q": "ab"}).status_code == 422

    response = client.get("/law/search", params={"q": "garantia", "mode": "lexical", "k": 3})
    assert response.status_code == 200
    # The endpoint searches the Lei 14.133 only, never the sample law indexed here.
    assert all(hit["citation"].startswith("Lei 14.133/2021, ") for hit in response.json())


# --- The real law: recall on the known questions ------------------------------


@needs_postgres
def test_law_14133_index_size(law_index: Session) -> None:
    count = law_index.scalar(
        select(func.count()).select_from(LawProvision).where(LawProvision.law == LAW_14133)
    )

    assert count == 1410


@needs_postgres
def test_recall_at_5_meets_the_target_on_the_known_questions(law_index: Session) -> None:
    """Acceptance criterion: the expected article is in the top 5 for at least 8 of 10 questions.

    Uses the real embeddings (precomputed with multilingual-e5-base and committed),
    so the ranking is the same one produced with the model loaded.
    """
    results = evaluate(law_index, query_embedder(allow_model=False), "hybrid", k=5)

    missed = [result.question.id for result in results if result.rank is None]
    assert len(results) == 10
    assert recall(results) >= 0.8, f"missed: {missed}"


@needs_postgres
def test_hybrid_search_is_not_worse_than_either_signal_alone(law_index: Session) -> None:
    embedder = query_embedder(allow_model=False)
    scores = {mode: recall(evaluate(law_index, embedder, mode, k=5)) for mode in MODES}

    assert scores["hybrid"] >= max(scores["vector"], scores["lexical"])
