"""Parses the HTML of a Brazilian federal law (as published by Planalto) into provisions.

Brazilian statutes are hierarchical: an article ("Art. 67") has a head (caput)
and may hold paragraphs ("§ 1º", "Parágrafo único"), items ("incisos": I, II),
sub-items ("alíneas": a, b) and numbered items (1, 2). Each provision gets a
citable identifier such as "Art. 67, § 1º, II", plus the titles of the
chapter/section it sits in.

Text that Planalto shows struck through (superseded wording) is discarded.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from bs4 import BeautifulSoup

ProvisionKind = Literal["article", "paragraph", "inciso", "alinea", "item"]

_WHITESPACE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,;.:)])")
# Editorial notes added by Planalto, not part of the legal text.
_EDITORIAL_NOTE = re.compile(
    r"\(\s*(?:Reda[cç][aã]o dada|Inclu[ií]d[oa]|Vide|Regulamento|Vig[eê]ncia|"
    r"Promulga[cç][aã]o|Revogad[oa] pel[oa]|Produ[cç][aã]o de efeitos?)[^)]*\)",
    re.IGNORECASE,
)
_TRAILING_LINK_LABEL = re.compile(
    r"(?:\s+(?:Regulamento|Vig[eê]ncia|Produ[cç][aã]o de efeitos?))+$", re.IGNORECASE
)
_WITHOUT_CONTENT = re.compile(r"^\(?\s*(?:VETADO|Revogad[oa])\s*\)?[.;]?$", re.IGNORECASE)

_ARTICLE = re.compile(r"^Art\.\s*(\d+)(-[A-Z])?\s*[ºo°]?\s*\.?\s*(?:[-–]\s*)?(.*)$", re.DOTALL)
_PARAGRAPH = re.compile(r"^§\s*(\d+)\s*[ºo°]?(-[A-Z])?\s*\.?\s*(?:[-–]\s*)?(.*)$", re.DOTALL)
_SOLE_PARAGRAPH = re.compile(r"^Par[aá]grafo [uú]nico\s*\.?\s*(?:[-–]\s*)?(.*)$", re.DOTALL)
_INCISO = re.compile(r"^([IVXLCDM]+)\s*[-–—]\s*(.*)$", re.DOTALL)
_ALINEA = re.compile(r"^([a-z])\)\s*(.*)$", re.DOTALL)
_ITEM = re.compile(r"^(\d{1,2})\.\s+(.*)$", re.DOTALL)
_DIVISION = re.compile(
    r"^(T[IÍ]TULO|CAP[IÍ]TULO|Se[cç][aã]o|Subse[cç][aã]o)\s+([IVXLCDM]+|[UÚ]NIC[OA])$", re.I
)
_DIVISION_LEVELS = {"TITULO": 0, "CAPITULO": 1, "SECAO": 2, "SUBSECAO": 3}
_DIVISION_NAMES = {0: "Título", 1: "Capítulo", 2: "Seção", 3: "Subseção"}
# The enacting formula that closes the law ("Brasília, 1º de abril de 2021; ...").
_CLOSING = re.compile(r"^Bras[ií]lia,\s*\d")
_OPENING_QUOTES = ("“", '"', "‘")


@dataclass
class Provision:
    identifier: str  # e.g. "Art. 67, § 1º, II"
    kind: ProvisionKind
    article: int
    text: str
    parent: str | None  # identifier of the enclosing provision
    position: int  # reading order within the law
    heading: str  # e.g. "Título II - Das Licitações > Capítulo VI - Da Habilitação"
    # Text of the enclosing provisions, outermost first (the article head comes first).
    ancestors: list[str] = field(default_factory=list)

    @property
    def has_content(self) -> bool:
        """False for vetoed or revoked provisions, which carry no rule."""
        return bool(self.text) and not _WITHOUT_CONTENT.match(self.text)


def _clean(text: str) -> str:
    text = _WHITESPACE.sub(" ", text.replace("\xa0", " ")).strip()
    text = _EDITORIAL_NOTE.sub("", text)
    text = _TRAILING_LINK_LABEL.sub("", text)
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    return _WHITESPACE.sub(" ", text).strip()


def _ordinal(number: int) -> str:
    """Brazilian legal style: ordinals up to nine ("Art. 9º"), cardinals after ("Art. 10")."""
    return f"{number}º" if number < 10 else str(number)


def _fold(text: str) -> str:
    table = str.maketrans("ÍíÇçÃãÚú", "IiCcAaUu")
    return text.translate(table).upper()


def extract_paragraphs(html: bytes) -> list[str]:
    """Visible paragraphs of the page, in order, without struck-through text."""
    soup = BeautifulSoup(html, "html.parser")
    for struck in soup.find_all(["strike", "s", "del"]):
        struck.decompose()
    paragraphs = (_clean(tag.get_text("")) for tag in soup.find_all("p"))
    return [paragraph for paragraph in paragraphs if paragraph]


def parse_law(html: bytes) -> list[Provision]:
    """Parse a law page into its provisions, in reading order."""
    provisions: list[Provision] = []
    divisions: dict[int, str] = {}
    pending_division: int | None = None
    # Innermost open provision at each level of the hierarchy.
    article: Provision | None = None
    paragraph: Provision | None = None
    inciso: Provision | None = None
    alinea: Provision | None = None
    last: Provision | None = None
    quoting = False  # inside the quoted text of another law

    def add(kind: ProvisionKind, label: str, text: str, parent: Provision | None) -> Provision:
        nonlocal last
        assert article is not None or kind == "article"
        provision = Provision(
            identifier=f"{parent.identifier}, {label}" if parent else label,
            kind=kind,
            article=int(re.search(r"\d+", label if parent is None else parent.identifier).group()),  # type: ignore[union-attr]
            text=text,
            parent=parent.identifier if parent else None,
            position=len(provisions),
            heading=" > ".join(divisions[level] for level in sorted(divisions)),
            ancestors=[*parent.ancestors, parent.text] if parent else [],
        )
        provisions.append(provision)
        last = provision
        return provision

    for text in extract_paragraphs(html):
        if article is not None and _CLOSING.match(text):
            break

        if division := _DIVISION.match(text):
            level = _DIVISION_LEVELS[_fold(division.group(1))]
            divisions = {known: name for known, name in divisions.items() if known < level}
            divisions[level] = f"{_DIVISION_NAMES[level]} {division.group(2).upper()}"
            pending_division = level
            continue
        if pending_division is not None:
            # The line right after "CAPÍTULO VI" is its name ("DA HABILITAÇÃO").
            level, pending_division = pending_division, None
            if not _ARTICLE.match(text):
                divisions[level] = f"{divisions[level]} - {text.capitalize()}"
                continue

        match = _ARTICLE.match(text)
        if match and _continues_numbering(int(match.group(1)), article):
            number = int(match.group(1))
            label = f"Art. {_ordinal(number)}{match.group(2) or ''}"
            paragraph = inciso = alinea = None
            quoting = False
            article = add("article", label, match.group(3), None)
        elif article is None:
            continue  # preamble before Art. 1º
        elif quoting or match or text.startswith(_OPENING_QUOTES):
            # Text of another law being amended (e.g. the Penal Code articles added by
            # Art. 178). It belongs to the article that quotes it, as plain text.
            quoting = True
            article.text = f"{article.text} {text}".strip()
        elif match := _PARAGRAPH.match(text):
            inciso = alinea = None
            label = f"§ {_ordinal(int(match.group(1)))}{match.group(2) or ''}"
            paragraph = add("paragraph", label, match.group(3), article)
        elif match := _SOLE_PARAGRAPH.match(text):
            inciso = alinea = None
            paragraph = add("paragraph", "parágrafo único", match.group(1), article)
        elif match := _INCISO.match(text):
            alinea = None
            inciso = add("inciso", match.group(1), match.group(2), paragraph or article)
        elif match := _ALINEA.match(text):
            alinea = add("alinea", match.group(1), match.group(2), inciso or paragraph or article)
        elif (match := _ITEM.match(text)) and alinea is not None:
            add("item", match.group(1), match.group(2), alinea)
        elif last is not None:
            # Continuation of the previous provision (e.g. quoted text of an amended law).
            last.text = f"{last.text} {text}".strip()

    return _latest_wording(provisions)


def _continues_numbering(number: int, current: Provision | None) -> bool:
    """Articles are numbered in sequence; a jump means a quoted article of another law."""
    return current is None or number in (current.article, current.article + 1)


def _latest_wording(provisions: list[Provision]) -> list[Provision]:
    """Keep only the last wording of provisions that appear more than once.

    Planalto keeps earlier wordings on the page ("(VETADO)" followed by the text
    promulgated later, or an amended item followed by its new wording). The last
    occurrence is the one in force; earlier ones are dropped with their children.
    """
    last_position = {provision.identifier: provision.position for provision in provisions}
    dropped: set[str] = set()
    kept: list[Provision] = []
    for provision in provisions:
        superseded = last_position[provision.identifier] != provision.position
        if superseded:
            dropped.add(provision.identifier)
        elif provision.parent in dropped and provision.position < last_position[provision.parent]:
            # Child of a superseded wording (it sits before the new wording).
            dropped.add(provision.identifier)
        else:
            dropped.discard(provision.identifier)
            kept.append(provision)
    for position, provision in enumerate(kept):
        provision.position = position
    return kept
