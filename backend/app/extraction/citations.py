"""Citation validation: the main guard against hallucinated extractions.

Every value the model returns must come with a literal quote and a page number.
Here each quote is searched in the text of the page it points to. A quote that
cannot be found lowers the confidence of its field, flags it for human review
and is logged. The comparison ignores differences in whitespace, letter case
and typographic variants of quotes and dashes, and tolerates a few wrong
characters (OCR noise), but nothing more.
"""

import logging
import re
from collections import Counter
from collections.abc import Mapping

from rapidfuzz import fuzz

from app.extraction.schemas import (
    Citation,
    CitationStatus,
    ConfidenceLevel,
    ExtractedField,
    RawField,
    ValidatedCitation,
)

logger = logging.getLogger(__name__)

# Shorter quotes ("5%", "sim") match almost any page and prove nothing.
MIN_QUOTE_CHARS = 15
# Minimum similarity (0-100) between the quote and the best-matching stretch of the page.
FUZZY_THRESHOLD = 92.0
REVIEW_THRESHOLD = 0.5

BASE_CONFIDENCE: dict[ConfidenceLevel, float] = {"alta": 0.9, "media": 0.6, "baixa": 0.3}
# A value without any usable evidence can never be more than a low-confidence guess.
UNSUPPORTED_CAP = 0.2
# Some quotes check out and some do not.
PARTIALLY_SUPPORTED_CAP = 0.45
WRONG_PAGE_FACTOR = 0.9

_NUMBER = re.compile(r"\d+(?:[.,/]\d+)*")
# Characters around the aligned stretch that are also searched for the quote's numbers.
_NUMBER_WINDOW_MARGIN = 5
# Score given to a fuzzy match whose numbers differ: always below the threshold.
_NUMBER_MISMATCH_SCORE = 50.0
_WHITESPACE = re.compile(r"\s+")
_ELLIPSIS = re.compile(r"\s*(?:\[\s*\.\.\.\s*\]|\(\s*\.\.\.\s*\)|\.\.\.|…)\s*")
_TYPOGRAPHIC = str.maketrans(
    {"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "–": "-", "—": "-", "‐": "-"}
)


def normalize_for_match(text: str) -> str:
    return _WHITESPACE.sub(" ", text.translate(_TYPOGRAPHIC)).strip().casefold()


def _score(quote: str, page_text: str) -> float:
    """Similarity (0-100) between a normalized quote and the best stretch of a page."""
    if not quote or not page_text:
        return 0.0
    if quote in page_text:
        return 100.0

    alignment = fuzz.partial_ratio_alignment(quote, page_text)
    if alignment is None:
        return 0.0
    # Fuzzy matching forgives a few wrong letters, but a different number is a
    # different fact: "R$ 1,00" must never pass for "R$ 22.549.875,04". Every
    # number in the quote has to appear in the stretch of the page it matched.
    start = max(0, alignment.dest_start - _NUMBER_WINDOW_MARGIN)
    matched = page_text[start : alignment.dest_end + _NUMBER_WINDOW_MARGIN]
    missing = Counter(_NUMBER.findall(quote)) - Counter(_NUMBER.findall(matched))
    if missing:
        return min(float(alignment.score), _NUMBER_MISMATCH_SCORE)
    return float(alignment.score)


def _quote_score(quote: str, page_text: str) -> float:
    """Score a quote, accepting quotes where the model elided the middle with '...'."""
    parts = [part for part in _ELLIPSIS.split(quote) if part]
    if len(parts) <= 1:
        return _score(quote, page_text)
    # Every fragment must be on the page; the weakest one decides.
    return min(_score(part, page_text) for part in parts)


def validate_citation(citation: Citation, pages: Mapping[int, str]) -> ValidatedCitation:
    """Check one citation against the document. ``pages`` maps page number to normalized text."""
    quote = normalize_for_match(citation.quote)

    def result(page: int, status: CitationStatus, score: float) -> ValidatedCitation:
        return ValidatedCitation(
            page=page,
            quote=citation.quote,
            status=status,
            cited_page=citation.page,
            match_score=round(score, 1),
        )

    if len(quote) < MIN_QUOTE_CHARS:
        return result(citation.page, "too_short", 0.0)

    cited_score = _quote_score(quote, pages.get(citation.page, ""))
    if cited_score >= FUZZY_THRESHOLD:
        return result(citation.page, "valid", cited_score)

    # The quote may be real but attributed to the wrong page: look elsewhere,
    # nearest pages first.
    for page in sorted(pages, key=lambda number: abs(number - citation.page)):
        if page == citation.page:
            continue
        score = _quote_score(quote, pages[page])
        if score >= FUZZY_THRESHOLD:
            return result(page, "wrong_page", score)

    return result(citation.page, "not_found", cited_score)


def _confidence(
    level: ConfidenceLevel, has_value: bool, citations: list[ValidatedCitation]
) -> float:
    confidence = BASE_CONFIDENCE[level]
    supported = [c for c in citations if c.status in ("valid", "wrong_page")]
    unsupported = len(citations) - len(supported)

    if not has_value:
        # "Not found" needs no quote; the model's own confidence stands.
        return confidence
    if not supported:
        return min(confidence, UNSUPPORTED_CAP)
    if unsupported:
        confidence = min(confidence, PARTIALLY_SUPPORTED_CAP)
    if any(c.status == "wrong_page" for c in supported):
        confidence *= WRONG_PAGE_FACTOR
    return round(confidence, 2)


def validate_field[T](
    raw: RawField[T], pages: Mapping[int, str], field_name: str
) -> ExtractedField[T]:
    """Validate the citations of one field and derive its final confidence."""
    citations = [validate_citation(citation, pages) for citation in raw.citations]
    for citation in citations:
        if citation.status != "valid":
            logger.warning(
                "citation not confirmed",
                extra={
                    "field": field_name,
                    "status": citation.status,
                    "cited_page": citation.cited_page,
                    "found_page": citation.page if citation.status == "wrong_page" else None,
                    "match_score": citation.match_score,
                    "quote": citation.quote[:200],
                },
            )

    confidence = _confidence(raw.confidence, raw.value is not None, citations)
    return ExtractedField[T](
        value=raw.value,
        citations=citations,
        confidence=confidence,
        needs_review=confidence < REVIEW_THRESHOLD,
    )


def unavailable_field() -> dict[str, object]:
    """Placeholder (as plain data) for a field whose extraction call failed."""
    return {"value": None, "citations": [], "confidence": 0.0, "needs_review": True}
