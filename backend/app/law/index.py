"""Builds the searchable index of a law: parse, embed and store its provisions."""

import logging
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import LAW_EMBEDDING_DIMENSIONS, LawProvision
from app.embeddings.base import EmbeddingProvider, get_embedding_provider
from app.embeddings.cache import CachedEmbeddings
from app.law.parser import Provision, parse_law

logger = logging.getLogger(__name__)

LAW_14133 = "Lei 14.133/2021"
_LAW_DIR = Path(__file__).resolve().parents[3] / "data" / "law"
LAW_14133_FILE = _LAW_DIR / "L14133.html"
# Embeddings of the law's provisions, precomputed with the default embedding model.
LAW_14133_EMBEDDINGS_FILE = _LAW_DIR / "L14133.embeddings.npz"

# Enclosing provisions are quoted in the context only up to this many characters each.
_MAX_ANCESTOR_CHARS = 300
_EMBEDDING_BATCH = 64


def _ancestors(provision: Provision) -> list[str]:
    return [
        text if len(text) <= _MAX_ANCESTOR_CHARS else f"{text[:_MAX_ANCESTOR_CHARS]}..."
        for text in provision.ancestors
    ]


def build_context(provision: Provision) -> str:
    """Text indexed for term matching: titles, enclosing provisions, own text.

    An inciso such as "IV - prova do atendimento de requisitos previstos em lei
    especial" means little alone; preceded by its chapter ("Da habilitação") and
    its article head it becomes findable by subject.
    """
    parts = [provision.heading, provision.identifier, *_ancestors(provision), provision.text]
    return "\n".join(part for part in parts if part)


def build_embedding_text(provision: Provision) -> str:
    """Text that is embedded: enclosing provisions and own text, without titles.

    Chapter titles and the identifier help term matching but dilute the
    embedding: every provision of a chapter starts with the same words. Leaving
    them out raised vector-only recall@5 from 7 to 9 of the 10 evaluation
    questions (see eval/law_search/README.md).
    """
    return "\n".join([*_ancestors(provision), provision.text])


def law_embedder(allow_model: bool = True) -> CachedEmbeddings:
    """Embedding provider for indexing the law, backed by the committed cache file.

    With ``allow_model=False`` a text missing from the cache is an error instead
    of a reason to load the model (used where the model must not be downloaded).
    """
    return CachedEmbeddings(
        get_settings().embedding_model,
        LAW_14133_EMBEDDINGS_FILE,
        get_embedding_provider if allow_model else None,
    )


def index_law(
    session: Session, html: bytes, embedder: EmbeddingProvider, law: str = LAW_14133
) -> int:
    """(Re)build the index of ``law`` from its HTML. Returns the number of provisions stored."""
    provisions = [provision for provision in parse_law(html) if provision.has_content]
    contexts = [build_context(provision) for provision in provisions]
    embedding_texts = [build_embedding_text(provision) for provision in provisions]

    vectors: list[list[float]] = []
    for start in range(0, len(embedding_texts), _EMBEDDING_BATCH):
        batch = embedder.embed_passages(embedding_texts[start : start + _EMBEDDING_BATCH])
        if batch.shape[1] != LAW_EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"embedding model '{embedder.model_name}' produces {batch.shape[1]} dimensions; "
                f"the law index is built for {LAW_EMBEDDING_DIMENSIONS}"
            )
        vectors.extend(batch.tolist())

    # Replace the whole law in one transaction, so readers never see a partial index.
    session.execute(delete(LawProvision).where(LawProvision.law == law))
    session.add_all(
        LawProvision(
            law=law,
            identifier=provision.identifier,
            kind=provision.kind,
            article=provision.article,
            parent=provision.parent,
            position=provision.position,
            heading=provision.heading,
            text=provision.text,
            context=context,
            embedding=vector,
        )
        for provision, context, vector in zip(provisions, contexts, vectors, strict=True)
    )
    session.commit()
    logger.info(
        "law indexed",
        extra={"law": law, "provisions": len(provisions), "embedding_model": embedder.model_name},
    )
    return len(provisions)
