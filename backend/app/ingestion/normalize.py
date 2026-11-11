"""Text normalization for extracted PDF pages.

The goal is text that is faithful to the document but free of layout noise, so
that later stages can chunk it and match quotations against it reliably.
Line breaks are preserved: clause headings are recognized by line.
"""

import re
from collections import Counter

# Zero-width characters, soft hyphen, BOM and NUL (PostgreSQL rejects NUL in text).
_INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad\x00]")
_HORIZONTAL_SPACE = re.compile(r"[ \t\u00a0\u2000-\u200a\u202f\u3000]+")
_BLANK_LINES = re.compile(r"\n{3,}")
# "habili-\ntação" -> "habilitação". Only joins when the next line starts with a
# lowercase letter, so list markers ("-\nItem") and "Decreto-\nLei" are left alone.
_HYPHEN_BREAK = re.compile(r"(?<=[a-zà-ÿ])-\n(?=[a-zà-ÿ])")
_DIGITS = re.compile(r"\d+")

# How many lines at the top and bottom of each page may hold headers/footers.
_EDGE_LINES = 3
# A line is a header/footer when it repeats on at least this share of the pages.
_REPEAT_RATIO = 0.5
_MIN_PAGES_FOR_REPEAT_DETECTION = 4


def clean_text(text: str) -> str:
    """Remove invisible characters and redundant whitespace, keeping line breaks."""
    text = _INVISIBLE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [_HORIZONTAL_SPACE.sub(" ", line).strip() for line in text.split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def dehyphenate(text: str) -> str:
    """Join words that were split with a hyphen at the end of a line."""
    return _HYPHEN_BREAK.sub("", text)


def _line_key(line: str) -> str:
    """Comparison key that makes "Página 3 de 80" and "Página 4 de 80" equal."""
    return _DIGITS.sub("#", line.lower())


def _edge_indexes(lines: list[str]) -> tuple[list[int], list[int]]:
    """Indexes of the first and last non-empty lines of a page."""
    non_empty = [i for i, line in enumerate(lines) if line]
    top = non_empty[:_EDGE_LINES]
    bottom = [i for i in non_empty[-_EDGE_LINES:] if i not in top]
    return top, bottom


def remove_repeated_headers_and_footers(pages: list[str]) -> list[str]:
    """Drop lines that repeat at the top or bottom of most pages.

    Digits are ignored when comparing, which also catches page numbers.
    Short documents are returned unchanged: there is not enough evidence to
    tell a header from real content.
    """
    if len(pages) < _MIN_PAGES_FOR_REPEAT_DETECTION:
        return pages

    split_pages = [page.split("\n") for page in pages]
    top_counts: Counter[str] = Counter()
    bottom_counts: Counter[str] = Counter()
    for lines in split_pages:
        top, bottom = _edge_indexes(lines)
        top_counts.update({_line_key(lines[i]) for i in top})
        bottom_counts.update({_line_key(lines[i]) for i in bottom})

    threshold = len(pages) * _REPEAT_RATIO
    repeated_top = {key for key, count in top_counts.items() if count >= threshold}
    repeated_bottom = {key for key, count in bottom_counts.items() if count >= threshold}
    if not repeated_top and not repeated_bottom:
        return pages

    result: list[str] = []
    for lines in split_pages:
        top, bottom = _edge_indexes(lines)
        drop = {i for i in top if _line_key(lines[i]) in repeated_top}
        drop |= {i for i in bottom if _line_key(lines[i]) in repeated_bottom}
        kept = "\n".join(line for i, line in enumerate(lines) if i not in drop)
        result.append(_BLANK_LINES.sub("\n\n", kept).strip())
    return result


def normalize_pages(raw_pages: list[str]) -> list[str]:
    """Full normalization pipeline, one string in and one string out per page."""
    cleaned = [clean_text(page) for page in raw_pages]
    without_edges = remove_repeated_headers_and_footers(cleaned)
    return [dehyphenate(page) for page in without_edges]
