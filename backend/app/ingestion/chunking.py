"""Structure-aware chunking of an edital.

The text is split at clause and annex headings ("5. DA HABILITAÇÃO",
"CLÁUSULA NONA - DA GARANTIA", "ANEXO II - MINUTA DO CONTRATO"). Sections
longer than the size limit are split again, preferably at sub-item boundaries
("5.1.", "5.2."). Every chunk records the pages where it starts and ends.

When no heading is recognized the document still gets chunked, by size only.
"""

import re
from dataclasses import dataclass, field

from app.db.models import ChunkKind

DEFAULT_MAX_CHARS = 2000
_MAX_HEADING_CHARS = 150
_HEADING_SEPARATOR = " › "

_ANNEX = re.compile(r"^ANEXO\b")
_ANNEX_NUMBERED = re.compile(r"^ANEXO\s+(?:[IVXLCDM]+|\d+|[A-Z])\s*[-–—:.]")
_ANNEX_BARE = re.compile(r"^ANEXO(?:\s+(?:[IVXLCDM]+|\d+|[A-Z]))?\s*[-–—:.]?$")
# "CLÁUSULA NONA - DA GARANTIA (Art. 92, XII, da Lei n.º 14.133/2021)", "7.CLÁUSULA SÉTIMA - ..."
# The word itself is distinctive enough, so the rest of the line may hold anything.
_NAMED_CLAUSE = re.compile(r"^(?:(?P<number>\d{1,2})\s*[.)\-–—]?\s*)?CL[ÁA]USULA\s+[A-ZÀ-Ú]{3,}")
_DIVISION = re.compile(r"^(?:SEÇÃO|CAPÍTULO|TÍTULO)\s+[IVXLCDM\d]+\b")
# "5. DA HABILITAÇÃO", "5 - DA HABILITAÇÃO", "5) HABILITAÇÃO"
_NUMBERED_CLAUSE = re.compile(r"^(?P<number>\d{1,2})\s*(?:[.)]|[-–—])\s*(?P<title>\S.*)$")
# "5 DA HABILITAÇÃO": without a separator the line could just as well be a table
# row ("3 CAMINHÃO BASCULANTE"), so it only counts when it continues the numbering.
_NUMBERED_CLAUSE_NO_SEPARATOR = re.compile(r"^(?P<number>\d{1,2})\s+(?P<title>\S.*)$")
_SUB_ITEM = re.compile(r"^\d{1,2}\.\d{1,2}(?:\.\d{1,2})*\.?(?:\s|$)")
# PDF extraction sometimes splits "11 - DAS IMPUGNAÇÕES" into "11" and "- DAS IMPUGNAÇÕES".
_LONE_NUMBER = re.compile(r"^\d{1,2}$")
_HEADING_CONTINUATION = re.compile(r"^[-–—.]\s*[A-ZÀ-Ú]{2}")
_TITLE_CHARS = re.compile(r"^[A-ZÀ-Ú\s,/()\-–—.:&ºª]+$")


@dataclass(frozen=True)
class ChunkDraft:
    index: int
    kind: ChunkKind
    heading: str | None
    text: str
    page_start: int
    page_end: int


@dataclass(frozen=True)
class _Line:
    page: int
    text: str


@dataclass
class _Section:
    kind: ChunkKind
    heading: str | None
    lines: list[_Line] = field(default_factory=list)


def _is_upper_title(text: str) -> bool:
    """True for an all-caps title without digits, e.g. "DA HABILITAÇÃO"."""
    letters = sum(1 for char in text if char.isalpha())
    return letters >= 3 and bool(_TITLE_CHARS.match(text))


def _is_annex_heading(text: str) -> bool:
    if len(text) > _MAX_HEADING_CHARS or not _ANNEX.match(text):
        return False
    has_lowercase = any(char.islower() for char in text)
    return not has_lowercase or bool(_ANNEX_NUMBERED.match(text))


def _clause_number(text: str, last_number: int) -> int | None:
    """Return the clause number when ``text`` is a clause heading, else None.

    Headings without a number ("CLÁUSULA NONA", "SEÇÃO II") keep ``last_number``.
    """
    if len(text) > _MAX_HEADING_CHARS:
        return None
    if named := _NAMED_CLAUSE.match(text):
        return int(named.group("number")) if named.group("number") else last_number
    if _DIVISION.match(text) and not any(char.islower() for char in text):
        return last_number
    if (numbered := _NUMBERED_CLAUSE.match(text)) and _is_upper_title(numbered.group("title")):
        return int(numbered.group("number"))
    if (
        (bare := _NUMBERED_CLAUSE_NO_SEPARATOR.match(text))
        and _is_upper_title(bare.group("title"))
        and int(bare.group("number")) == last_number + 1
    ):
        return last_number + 1
    return None


def _flatten(pages: list[str]) -> list[_Line]:
    """Turn pages into non-empty lines tagged with their 1-based page number."""
    lines = [
        _Line(page=number, text=text)
        for number, page in enumerate(pages, start=1)
        for text in page.split("\n")
        if text
    ]
    if not lines:
        return []
    merged: list[_Line] = []
    skip_next = False
    for current, following in zip(lines, [*lines[1:], None], strict=True):
        if skip_next:
            skip_next = False
            continue
        if (
            following is not None
            and _LONE_NUMBER.match(current.text)
            and _HEADING_CONTINUATION.match(following.text)
        ):
            merged.append(_Line(page=current.page, text=f"{current.text} {following.text}"))
            skip_next = True
        else:
            merged.append(current)
    return merged


def _annex_title(lines: list[_Line], position: int) -> str:
    """Complete a bare "ANEXO IV" heading with the title found just below it."""
    heading = lines[position].text
    if not _ANNEX_BARE.match(heading):
        return heading
    for candidate in lines[position + 1 : position + 4]:
        if _is_annex_heading(candidate.text) or _clause_number(candidate.text, 0) is not None:
            break
        if _is_upper_title(candidate.text):
            return f"{heading.rstrip(' -–—:.')} - {candidate.text}"
    return heading


def _split_into_sections(lines: list[_Line]) -> list[_Section]:
    sections = [_Section(kind=ChunkKind.PREAMBLE, heading=None)]
    current_annex: str | None = None
    last_number = 0  # number of the latest clause heading; restarts inside each annex

    for position, line in enumerate(lines):
        if _is_annex_heading(line.text):
            # Adjacent annex lines are a list of annexes ("ANEXO I - ...", "ANEXO II - ..."),
            # not the start of an annex.
            previous = lines[position - 1].text if position > 0 else ""
            following = lines[position + 1].text if position + 1 < len(lines) else ""
            if not (_is_annex_heading(previous) or _is_annex_heading(following)):
                current_annex = _annex_title(lines, position)
                last_number = 0
                sections.append(_Section(kind=ChunkKind.ANNEX, heading=current_annex))
        elif (number := _clause_number(line.text, last_number)) is not None:
            last_number = number
            if current_annex is None:
                sections.append(_Section(kind=ChunkKind.CLAUSE, heading=line.text))
            else:
                heading = f"{current_annex}{_HEADING_SEPARATOR}{line.text}"
                sections.append(_Section(kind=ChunkKind.ANNEX, heading=heading))
        sections[-1].lines.append(line)

    return [section for section in sections if section.lines]


def _hard_split(line: _Line, max_chars: int) -> list[_Line]:
    """Break a single over-long line (e.g. a table flattened into one line)."""
    return [
        _Line(page=line.page, text=line.text[start : start + max_chars])
        for start in range(0, len(line.text), max_chars)
    ]


def _units(lines: list[_Line], max_chars: int) -> list[list[_Line]]:
    """Group lines into sub-items: the smallest pieces we try not to split."""
    units: list[list[_Line]] = []
    for line in lines:
        pieces = _hard_split(line, max_chars) if len(line.text) > max_chars else [line]
        if not units or _SUB_ITEM.match(line.text):
            units.append([])
        units[-1].extend(pieces)
    return units


def _size(lines: list[_Line]) -> int:
    return sum(len(line.text) + 1 for line in lines)


def _pack(lines: list[_Line], max_chars: int) -> list[list[_Line]]:
    """Greedily pack sub-items into groups of at most ``max_chars`` characters."""
    groups: list[list[_Line]] = [[]]
    for unit in _units(lines, max_chars):
        if _size(unit) > max_chars:
            # A sub-item larger than the limit is packed line by line.
            for line in unit:
                if groups[-1] and _size(groups[-1]) + len(line.text) + 1 > max_chars:
                    groups.append([])
                groups[-1].append(line)
        else:
            if groups[-1] and _size(groups[-1]) + _size(unit) > max_chars:
                groups.append([])
            groups[-1].extend(unit)
    return [group for group in groups if group]


def chunk_pages(pages: list[str], max_chars: int = DEFAULT_MAX_CHARS) -> list[ChunkDraft]:
    """Split normalized page texts into chunks that follow the edital structure."""
    chunks: list[ChunkDraft] = []
    for section in _split_into_sections(_flatten(pages)):
        for group in _pack(section.lines, max_chars):
            chunks.append(
                ChunkDraft(
                    index=len(chunks),
                    kind=section.kind,
                    heading=section.heading,
                    text="\n".join(line.text for line in group),
                    page_start=group[0].page,
                    page_end=group[-1].page,
                )
            )
    return chunks
