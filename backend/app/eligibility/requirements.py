"""Reading the extracted requirements: what each one asks for, and its numbers.

Requirements come from the extraction as free text, one item per requirement.
Classifying them and reading their numbers (money, percentages, quantities)
is done here with plain rules, so every number the eligibility check compares
can be traced to a pattern and unit-tested. Patterns run on folded text
(lowercase, no accents).
"""

import re
from dataclasses import dataclass
from typing import Any

from app.eligibility.profile import CertificateKind, QuantityUnit
from app.eligibility.schemas import RequirementKind, Section
from app.extraction.prompts import fold
from app.extraction.schemas import EditalExtraction, ExtractedField

SECTION_FIELDS: dict[Section, str] = {
    "juridica": "qualification_legal",
    "fiscal": "qualification_fiscal",
    "tecnica": "qualification_technical",
    "economica": "qualification_economic",
}


@dataclass(frozen=True)
class Requirement:
    code: str  # "R1", "R2", ... in reading order
    section: Section
    text: str
    field: ExtractedField[Any]
    kind: RequirementKind


def collect_requirements(extraction: EditalExtraction) -> list[Requirement]:
    """Every extracted qualification requirement, classified, in a stable order."""
    requirements: list[Requirement] = []
    for section, name in SECTION_FIELDS.items():
        for item in getattr(extraction, name):
            text = (item.value or "").strip()
            if not text:
                continue
            requirements.append(
                Requirement(
                    code=f"R{len(requirements) + 1}",
                    section=section,
                    text=text,
                    field=item,
                    kind=classify(text),
                )
            )
    return requirements


# --- Classification -----------------------------------------------------------

_DECLARATION = re.compile(r"^(?:[a-z0-9]{1,3}[.)]\s*)?(?:apresentar\s+)?(?:as\s+)?declarac")
_SITE_VISIT = re.compile(r"visita tecnica|vistoria")
_ATTESTATION = re.compile(r"atestado|acervo tecnico|capacidade tecnic|\bcat\b")
_REGISTRATION_ACT = re.compile(r"registro|inscricao|quitacao")
_COUNCIL = re.compile(r"\bcrea\b|\bcau\b|conselho|entidade profissional")
_CAPITAL = re.compile(r"capital social")
_NET_WORTH = re.compile(r"patrimonio liquido")
# "insolvência" (bankruptcy certificate) must not count as the solvency index.
_INDICES = re.compile(r"indice|liquidez|\bsolvencia|\bi?(?:lg|lc|sg)\b")
_BALANCE = re.compile(r"balanco|demonstrac\w* contab")
_REGULARITY = re.compile(r"regularidade|certid|\bcnd|negativa|\bcrf\b")
_CNPJ = re.compile(r"\bcnpj\b|cadastro nacional d[ae] pessoa")
_COMPANY_PURPOSE = re.compile(r"objeto social|ramo de atividade|\bcnae|compativel com o objeto")

_CERTIFICATE_PATTERNS: dict[CertificateKind, re.Pattern[str]] = {
    "federal": re.compile(r"federa|uniao"),
    "estadual": re.compile(r"estadua"),
    "municipal": re.compile(r"municip"),
    "fgts": re.compile(r"fgts|fundo de garantia"),
    "trabalhista": re.compile(r"trabalhist|\bcndt\b"),
    "falencia": re.compile(r"falencia|recuperacao judicial|insolvencia|concordata"),
}


def certificate_kinds(text: str) -> list[CertificateKind]:
    folded = fold(text)
    return [kind for kind, pattern in _CERTIFICATE_PATTERNS.items() if pattern.search(folded)]


def classify(text: str) -> RequirementKind:
    """The kind of a requirement. Order matters: the first match wins.

    A site visit certificate ("atestado de visita técnica") is not a technical
    attestation, and an attestation requirement often also mentions the CREA.
    """
    folded = fold(text).strip()
    if _SITE_VISIT.search(folded):
        return "visita_tecnica"
    if _DECLARATION.search(folded):
        return "declaracao"
    if _ATTESTATION.search(folded):
        return "atestado"
    if _REGISTRATION_ACT.search(folded) and _COUNCIL.search(folded):
        return "registro_profissional"
    if _CAPITAL.search(folded) or _NET_WORTH.search(folded):
        return "capital_ou_patrimonio"
    if _INDICES.search(folded):
        return "indices_contabeis"
    if _BALANCE.search(folded):
        return "balanco"
    if _REGULARITY.search(folded) and certificate_kinds(text):
        return "certidao"
    if _CNPJ.search(folded):
        return "cnpj"
    if _COMPANY_PURPOSE.search(folded):
        return "objeto_social"
    return "outro"


def mentions_capital(text: str) -> bool:
    return bool(_CAPITAL.search(fold(text)))


def mentions_net_worth(text: str) -> bool:
    return bool(_NET_WORTH.search(fold(text)))


def is_conditional_on_indices(text: str) -> bool:
    """Net worth asked only from bidders whose accounting indices fall below a limit."""
    folded = fold(text)
    return bool(_INDICES.search(folded)) and bool(
        re.search(r"\bse\b|\bcaso\b|menor|inferior|abaixo", folded)
    )


def councils(text: str) -> set[str]:
    folded = fold(text)
    return {council.upper() for council in ("crea", "cau") if re.search(rf"\b{council}\b", folded)}


# --- Numbers --------------------------------------------------------------------

# Brazilian notation: "3.404", "1.500,50", "2,5", "10".
_NUMBER = r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)"
_MONEY = re.compile(r"r\$\s*" + _NUMBER)
_PERCENT = re.compile(_NUMBER + r"\s*(?:%|por cento)")

# (pattern, unit, factor to that unit). Longer spellings first.
_UNITS: list[tuple[str, QuantityUnit, float]] = [
    (r"m²|m2|metros? quadrados?", "m2", 1.0),
    (r"m³|m3|metros? cubicos?", "m3", 1.0),
    (r"km|quilometros?", "m", 1000.0),
    (r"toneladas?|ton|t", "t", 1.0),
    (r"kg|quilos?|quilogramas?", "t", 0.001),
    (r"unidades?|und|un", "un", 1.0),
    (r"metros? lineares?|metros?|ml|m", "m", 1.0),
]
_QUANTITY = re.compile(
    _NUMBER
    + r"\s*(?P<unit>"
    + "|".join(f"(?:{pattern})" for pattern, _, _ in _UNITS)
    + r")(?![a-z0-9²³])"
)


def parse_number(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def parse_money(text: str) -> list[float]:
    """Amounts written as "R$ 1.234,56"."""
    return [parse_number(match.group(1)) for match in _MONEY.finditer(fold(text))]


def parse_percent(text: str) -> list[float]:
    return [parse_number(match.group(1)) for match in _PERCENT.finditer(fold(text))]


@dataclass(frozen=True)
class Quantity:
    amount: float
    unit: QuantityUnit
    text: str  # as written in the requirement, e.g. "3.404 M2"


def _unit_of(spelling: str) -> tuple[QuantityUnit, float]:
    for pattern, unit, factor in _UNITS:
        if re.fullmatch(pattern, spelling):
            return unit, factor
    raise ValueError(f"unknown unit: {spelling}")  # unreachable: the regex only matches these


def parse_quantities(text: str) -> list[Quantity]:
    """Quantities with a unit ("3.404 m²", "1,5 km"), converted to the profile's units."""
    folded = fold(text)
    quantities: list[Quantity] = []
    for match in _QUANTITY.finditer(folded):
        if folded[max(0, match.start() - 4) : match.start()].rstrip().endswith("r$"):
            continue
        unit, factor = _unit_of(match.group("unit"))
        quantity = Quantity(parse_number(match.group(1)) * factor, unit, match.group(0))
        if quantity not in quantities:
            quantities.append(quantity)
    return quantities
