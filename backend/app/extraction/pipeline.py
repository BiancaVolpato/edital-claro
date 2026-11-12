"""Section-based extraction: one focused LLM call per group of fields.

For each group, the relevant chunks are retrieved, the model fills that group's
schema, every citation is validated against the page text, and the groups are
merged into one ``EditalExtraction``. Groups hold disjoint fields, so merging
is deterministic and needs no extra LLM call.
"""

import logging
import time
from collections import Counter
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

from app.embeddings.base import EmbeddingProvider, Vectors
from app.extraction.citations import (
    normalize_for_match,
    unavailable_field,
    validate_field,
)
from app.extraction.context import build_user_message, new_boundary
from app.extraction.prompts import FieldGroup, PromptSet
from app.extraction.retrieval import ChunkData, select_chunks
from app.extraction.schemas import (
    EditalExtraction,
    ExtractedField,
    is_list_field,
    raw_group_model,
)
from app.llm.base import LLMError, LLMProvider
from app.llm.pricing import estimate_cost_usd

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class GroupRun:
    """Audit record of one LLM call."""

    group: str
    model: str
    chunk_indexes: list[int]
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float | None = None
    error: str | None = None


Strategy = Literal["sections", "direct"]
# About 15-20 thousand tokens of Portuguese text: the whole of a short edital.
DIRECT_MAX_CHARS = 60_000


def leading_chunks(chunks: list[ChunkData], max_chars: int) -> list[ChunkData]:
    """The chunks from the start of the document while they fit in ``max_chars``."""
    selected: list[ChunkData] = []
    total = 0
    for chunk in chunks:
        if selected and total + len(chunk.text) > max_chars:
            break
        selected.append(chunk)
        total += len(chunk.text)
    return selected


@dataclass(frozen=True)
class ExtractionOutcome:
    extraction: EditalExtraction
    runs: list[GroupRun]
    citation_counts: dict[str, int] = field(default_factory=dict)

    @property
    def failed_groups(self) -> list[str]:
        return [run.group for run in self.runs if run.error]


def _run_group(
    group: FieldGroup,
    chunks: list[ChunkData],
    prompt: PromptSet,
    llm: LLMProvider,
) -> tuple[GroupRun, BaseModel | None]:
    """Call the model for one group. Failures are captured, not raised."""
    chunk_indexes = [chunk.index for chunk in chunks]
    schema = raw_group_model(f"Extraction_{group.name}", list(group.fields))
    user = build_user_message(group, chunks, new_boundary())

    started = time.perf_counter()
    try:
        result = llm.extract(system=prompt.system, user=user, schema=schema)
    except LLMError as exc:
        logger.warning("extraction call failed", extra={"group": group.name, "error": str(exc)})
        return GroupRun(group.name, llm.model, chunk_indexes, error=str(exc)), None

    run = GroupRun(
        group=group.name,
        model=result.model,
        chunk_indexes=chunk_indexes,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
        cost_usd=estimate_cost_usd(result.model, result.input_tokens, result.output_tokens),
    )
    return run, result.output


def _validated_fields(
    group: FieldGroup, output: BaseModel | None, pages: Mapping[int, str]
) -> dict[str, Any]:
    """Validate the citations of a group's output (or mark its fields unavailable)."""
    fields: dict[str, Any] = {}
    for name in group.fields:
        if output is None:
            fields[name] = [] if is_list_field(name) else unavailable_field()
        elif is_list_field(name):
            fields[name] = [
                validate_field(item, pages, name).model_dump() for item in getattr(output, name)
            ]
        else:
            fields[name] = validate_field(getattr(output, name), pages, name).model_dump()
    return fields


def count_citations(extraction: EditalExtraction) -> dict[str, int]:
    """How many citations ended in each validation status."""
    counts: Counter[str] = Counter()
    for name in EditalExtraction.model_fields:
        value = getattr(extraction, name)
        items: list[ExtractedField[Any]] = value if isinstance(value, list) else [value]
        for item in items:
            counts.update(citation.status for citation in item.citations)
    return {"total": sum(counts.values()), **dict(sorted(counts.items()))}


def run_extraction(
    *,
    pages: Mapping[int, str],
    chunks: list[ChunkData],
    chunk_vectors: Vectors,
    prompt: PromptSet,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
    max_concurrency: int = 3,
    on_progress: ProgressCallback | None = None,
    strategy: Strategy = "sections",
    direct_max_chars: int = DIRECT_MAX_CHARS,
) -> ExtractionOutcome:
    """Extract every field of an edital. ``pages`` maps page number to normalized text.

    ``strategy`` chooses the excerpts each call sees: "sections" retrieves the
    relevant sections per group of fields (the default, see ADR-013); "direct"
    sends the document from the start, up to ``direct_max_chars``, to every
    group. "direct" exists as the baseline of the evaluation (eval/variants.toml).
    """
    # Retrieval is sequential (the embedding model is not thread-safe); only the
    # network-bound LLM calls run concurrently.
    if strategy == "direct":
        opening = leading_chunks(chunks, direct_max_chars)
        selections = {group.name: opening for group in prompt.groups}
    else:
        selections = {
            group.name: select_chunks(group, chunks, chunk_vectors, embedder)
            for group in prompt.groups
        }
    match_pages = {number: normalize_for_match(text) for number, text in pages.items()}

    runs: dict[str, GroupRun] = {}
    fields: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=max(1, max_concurrency)) as executor:
        futures = {
            executor.submit(_run_group, group, selections[group.name], prompt, llm): group
            for group in prompt.groups
        }
        for done, future in enumerate(as_completed(futures), start=1):
            group = futures[future]
            run, output = future.result()
            runs[group.name] = run
            fields.update(_validated_fields(group, output, match_pages))
            if on_progress:
                on_progress(done, len(futures))

    extraction = EditalExtraction.model_validate(fields)
    return ExtractionOutcome(
        extraction=extraction,
        runs=[runs[group.name] for group in prompt.groups],
        citation_counts=count_citations(extraction),
    )
