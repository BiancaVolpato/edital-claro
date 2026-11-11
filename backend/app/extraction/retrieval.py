"""Selects the chunks of an edital that are relevant to a group of fields.

Two signals are combined: semantic similarity between each of the group's
queries and the chunks (embeddings), and keyword hits. Each signal produces a
ranking and the selection takes turns between them, which needs no tuning of
weights between scores on different scales.
"""

from dataclasses import dataclass

from app.embeddings.base import EmbeddingProvider, Vectors
from app.extraction.prompts import FieldGroup, fold
from app.ingestion.chunking import HEADING_SEPARATOR

# Upper bound on chunks included because of their section title, per group.
_MAX_TITLED_CHUNKS = 8


@dataclass(frozen=True)
class ChunkData:
    """A chunk as the extraction needs it (decoupled from the ORM)."""

    index: int
    kind: str
    heading: str | None
    text: str
    page_spans: list[tuple[int, int]]

    @property
    def searchable_text(self) -> str:
        return f"{self.heading}\n{self.text}" if self.heading else self.text


def embed_chunks(chunks: list[ChunkData], embedder: EmbeddingProvider) -> Vectors:
    return embedder.embed_passages([chunk.searchable_text for chunk in chunks])


def _ranking(scores: list[float]) -> list[int]:
    """Positions with a positive score, best first."""
    return sorted((i for i, score in enumerate(scores) if score > 0), key=lambda i: -scores[i])


def _annex_openings(chunks: list[ChunkData]) -> set[int]:
    """Position of the first chunk of each annex (its title page)."""
    seen: set[str] = set()
    openings: set[int] = set()
    for position, chunk in enumerate(chunks):
        if chunk.kind != "annex" or not chunk.heading:
            continue
        annex = chunk.heading.split(HEADING_SEPARATOR)[0]
        if annex not in seen:
            seen.add(annex)
            openings.add(position)
    return openings


def _titled_body_sections(group: FieldGroup, chunks: list[ChunkData]) -> set[int]:
    """Chunks of the edital body whose section title matches a keyword of the group.

    A title such as "16 - GARANTIA DO CONTRATO" is the strongest evidence that a
    section is about the topic, and the body of the edital outranks its annexes,
    so these chunks are not left to compete with the (longer) contract draft.
    """
    matches = [
        position
        for position, chunk in enumerate(chunks)
        if chunk.kind == "clause"
        and chunk.heading
        and any(pattern.search(fold(chunk.heading)) for pattern in group.keywords)
    ]
    return set(matches[:_MAX_TITLED_CHUNKS])


def select_chunks(
    group: FieldGroup,
    chunks: list[ChunkData],
    chunk_vectors: Vectors,
    embedder: EmbeddingProvider,
) -> list[ChunkData]:
    """Return the chunks to show the model for ``group``, in reading order."""
    if not chunks:
        return []

    always = set(range(min(group.lead_chunks, len(chunks))))
    if group.annex_openings:
        always |= _annex_openings(chunks)
    always |= _titled_body_sections(group, chunks)

    # One ranking per query (semantic; vectors are L2-normalized, so the dot
    # product is the cosine similarity) plus one ranking by keyword hits.
    similarities = chunk_vectors @ embedder.embed_queries(list(group.queries)).T
    rankings = [_ranking(similarities[:, query].tolist()) for query in range(similarities.shape[1])]
    folded = [fold(chunk.searchable_text) for chunk in chunks]
    rankings.append(
        _ranking([float(sum(1 for p in group.keywords if p.search(text))) for text in folded])
    )

    # Picks alternate between the rankings. A group covers several topics (e.g.
    # guarantees, consortium, ME/EPP); merging everything into a single score
    # would let one topic with many matching chunks crowd the others out.
    picked: list[int] = []
    for depth in range(len(chunks)):
        for ranking in rankings:
            if depth < len(ranking) and len(picked) < group.top_k:
                position = ranking[depth]
                if position not in always and position not in picked:
                    picked.append(position)
        if len(picked) >= group.top_k:
            break

    return [chunks[position] for position in sorted(always | set(picked))]
