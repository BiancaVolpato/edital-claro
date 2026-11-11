"""Deterministic risk rules.

Each rule checks something the law states as a number, a date or a yes/no, so
it is decided by code: the answer is the same every time, costs nothing and
can be unit-tested. A rule only fires on extracted values that are backed by a
confirmed quote from the edital; it never builds on an unverified field.

Every rule names the provisions of the Lei 14.133/2021 it relies on. Their text
is fetched from the indexed law when the report is built, never typed here.
"""

import datetime as dt
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.extraction.citations import normalize_for_match, validate_citation
from app.extraction.schemas import (
    Citation,
    EditalExtraction,
    ExtractedField,
    ValidatedCitation,
)
from app.risks.schemas import Severity

# Limits stated in the law (the provision is cited by each rule that uses one).
BID_GUARANTEE_MAX_PERCENT = 1.0  # Art. 58, § 1º
CONTRACT_GUARANTEE_STANDARD_PERCENT = 5.0  # Art. 98
CONTRACT_GUARANTEE_JUSTIFIED_PERCENT = 10.0  # Art. 98
CONTRACT_GUARANTEE_LARGE_WORKS_PERCENT = 30.0  # Art. 99
LARGE_WORKS_THRESHOLD = 200_000_000.0  # Art. 6º, XXII
MINIMUM_NET_WORTH_MAX_PERCENT = 10.0  # Art. 69, § 4º
CHALLENGE_DEADLINE_BUSINESS_DAYS = 3  # Art. 164
# When the measured interval is this close to the minimum, holidays could tip it over.
_HOLIDAY_MARGIN_DAYS = 2


@dataclass(frozen=True)
class RuleFinding:
    type: str
    severity: Severity
    title: str
    description: str
    bidder_note: str | None
    agency_note: str | None
    citations: list[ValidatedCitation]
    legal_basis: list[str]  # identifiers in the Lei 14.133/2021


Rule = Callable[[EditalExtraction, Mapping[int, str]], list[RuleFinding]]


def _evidence(*fields: ExtractedField[Any]) -> list[ValidatedCitation]:
    """Confirmed citations of the given fields."""
    return [
        citation
        for extracted in fields
        for citation in extracted.citations
        if citation.status in ("valid", "wrong_page")
    ]


def _is_supported(extracted: ExtractedField[Any]) -> bool:
    """A field a rule may rely on: it has a value and at least one confirmed quote."""
    return extracted.value is not None and bool(_evidence(extracted))


def _percent(value: float) -> str:
    return f"{value:g}%".replace(".", ",")


def business_days_between(start: dt.date, end: dt.date) -> int:
    """Weekdays after ``start`` up to and including ``end`` (Art. 183: the first day
    is excluded and the last one included). Holidays are not known and count as
    business days, so the true number can only be equal or smaller.
    """
    days = 0
    current = start
    while current < end:
        current += dt.timedelta(days=1)
        if current.weekday() < 5:
            days += 1
    return days


# --- Minimum interval between publication and opening (Art. 55) ---------------


def _minimum_interval(extraction: EditalExtraction) -> tuple[int, str, bool] | None:
    """(minimum business days, provision, whether a longer minimum may apply)."""
    regime = (
        extraction.execution_regime.value if _is_supported(extraction.execution_regime) else None
    )
    criterion = (
        extraction.judgment_criterion.value
        if _is_supported(extraction.judgment_criterion)
        else None
    )
    if regime == "contratacao_integrada":
        return 60, "Art. 55, II, c", False
    if regime == "contratacao_semi_integrada":
        return 35, "Art. 55, II, d", False
    if criterion in ("tecnica_e_preco", "melhor_tecnica_ou_conteudo_artistico"):
        return 35, "Art. 55, IV", False
    if criterion in ("menor_preco", "maior_desconto"):
        # 10 days for common engineering works; 25 for special ones (Art. 55, II, b).
        # Whether the work is "common" is a judgment the rule cannot make, so it
        # enforces the lower bound and flags the interval in between.
        return 10, "Art. 55, II, a", True
    return None


def proposal_interval_rule(
    extraction: EditalExtraction, pages: Mapping[int, str]
) -> list[RuleFinding]:
    publication, opening = extraction.publication_date, extraction.opening
    minimum = _minimum_interval(extraction)
    if not (_is_supported(publication) and _is_supported(opening)) or minimum is None:
        return []
    assert publication.value is not None and opening.value is not None
    days_required, provision, longer_may_apply = minimum
    published, opens = publication.value, opening.value.date
    evidence = _evidence(publication, opening)
    basis = [provision, "Art. 183"]

    if opens < published:
        return [
            RuleFinding(
                type="datas_inconsistentes",
                severity="alta",
                title="Abertura anterior à data do edital",
                description=(
                    f"O edital é datado de {published:%d/%m/%Y}, mas a sessão de abertura está "
                    f"marcada para {opens:%d/%m/%Y}, que é anterior. Uma das datas está errada, "
                    "e o prazo para apresentação de propostas é contado a partir da divulgação."
                ),
                bidder_note=(
                    "Peça esclarecimento sobre a data correta antes de preparar a proposta."
                ),
                agency_note="Corrija a data e republique o edital, reabrindo o prazo de propostas.",
                citations=evidence,
                legal_basis=[provision, "Art. 55, § 1º"],
            )
        ]

    days = business_days_between(published, opens)
    interval = (
        f"Entre a data do edital ({published:%d/%m/%Y}) e a abertura ({opens:%d/%m/%Y}) há "
        f"{days} dias úteis, sem descontar feriados."
    )
    if days < days_required:
        return [
            RuleFinding(
                type="prazo_de_propostas_insuficiente",
                severity="alta",
                title="Prazo para propostas menor que o mínimo legal",
                description=f"{interval} O mínimo para este caso é de {days_required} dias úteis.",
                bidder_note=(
                    "O prazo é menor que o exigido por lei. Cabe impugnação para que o edital "
                    "seja republicado com o prazo correto."
                ),
                agency_note=(
                    "O prazo entre a divulgação e a abertura não atende ao mínimo legal, o que "
                    "pode levar à anulação do certame. Republique com o prazo completo."
                ),
                citations=evidence,
                legal_basis=basis,
            )
        ]
    if days < days_required + _HOLIDAY_MARGIN_DAYS:
        return [
            RuleFinding(
                type="prazo_de_propostas_no_limite",
                severity="baixa",
                title="Prazo para propostas no limite do mínimo legal",
                description=(
                    f"{interval} O mínimo é de {days_required} dias úteis. Feriados no período "
                    "ou a data real de divulgação podem deixar o prazo abaixo do mínimo."
                ),
                bidder_note=(
                    "Confira os feriados locais no período; se houver, o prazo pode ser ilegal."
                ),
                agency_note=(
                    "Confirme a contagem com os feriados e com a data efetiva de divulgação."
                ),
                citations=evidence,
                legal_basis=basis,
            )
        ]
    if longer_may_apply and days < 25:
        return [
            RuleFinding(
                type="prazo_de_propostas_depende_da_classificacao_da_obra",
                severity="baixa",
                title="Prazo para propostas só é suficiente para obra comum",
                description=(
                    f"{interval} Esse prazo atende ao mínimo de 10 dias úteis das obras e serviços "
                    "comuns de engenharia, mas não ao de 25 dias úteis exigido para obras e "
                    "serviços especiais de engenharia."
                ),
                bidder_note=(
                    "Se a obra tiver complexidade que a caracterize como especial, o prazo é "
                    "insuficiente e pode ser questionado."
                ),
                agency_note=(
                    "Garanta que o processo registre a classificação do objeto como obra comum "
                    "de engenharia; do contrário, o prazo mínimo é de 25 dias úteis."
                ),
                citations=evidence,
                legal_basis=["Art. 55, II, a", "Art. 55, II, b"],
            )
        ]
    return []


# --- Guarantees (Art. 58, 98 and 99) -----------------------------------------


def bid_guarantee_rule(extraction: EditalExtraction, pages: Mapping[int, str]) -> list[RuleFinding]:
    guarantee = extraction.bid_guarantee
    if not _is_supported(guarantee):
        return []
    assert guarantee.value is not None
    percent = guarantee.value.percent
    if not guarantee.value.required or percent is None or percent <= BID_GUARANTEE_MAX_PERCENT:
        return []
    return [
        RuleFinding(
            type="garantia_de_proposta_acima_do_limite",
            severity="alta",
            title="Garantia de proposta acima de 1%",
            description=(
                f"O edital exige garantia de proposta de {_percent(percent)} do valor estimado. "
                "A lei limita essa garantia a 1%."
            ),
            bidder_note=(
                "A exigência excede o teto legal e encarece a participação. Cabe impugnação."
            ),
            agency_note="Reduza a garantia de proposta a no máximo 1% do valor estimado.",
            citations=_evidence(guarantee),
            legal_basis=["Art. 58, § 1º"],
        )
    ]


def contract_guarantee_rule(
    extraction: EditalExtraction, pages: Mapping[int, str]
) -> list[RuleFinding]:
    guarantee = extraction.contract_guarantee
    if not _is_supported(guarantee):
        return []
    assert guarantee.value is not None
    percent = guarantee.value.percent
    if not guarantee.value.required or percent is None:
        return []
    if percent <= CONTRACT_GUARANTEE_STANDARD_PERCENT:
        return []

    value = extraction.estimated_value
    is_large = _is_supported(value) and (value.value or 0) > LARGE_WORKS_THRESHOLD
    evidence = _evidence(guarantee)

    if percent <= CONTRACT_GUARANTEE_JUSTIFIED_PERCENT:
        return [
            RuleFinding(
                type="garantia_contratual_acima_de_5",
                severity="media",
                title="Garantia contratual acima de 5% exige justificativa",
                description=(
                    f"O edital exige garantia de execução de {_percent(percent)} do valor do "
                    "contrato. Acima de 5%, a lei só admite até 10% e com justificativa baseada "
                    "na complexidade técnica e nos riscos envolvidos."
                ),
                bidder_note=(
                    "Considere o custo dessa garantia na proposta. Se o processo não trouxer a "
                    "justificativa, o percentual pode ser questionado."
                ),
                agency_note=(
                    "Inclua no processo a análise de complexidade e de riscos que justifica o "
                    "percentual acima de 5%."
                ),
                citations=evidence,
                legal_basis=["Art. 98"],
            )
        ]
    if is_large and percent <= CONTRACT_GUARANTEE_LARGE_WORKS_PERCENT:
        return []  # allowed for large works, as seguro-garantia with step-in clause (Art. 99)
    return [
        RuleFinding(
            type="garantia_contratual_acima_do_limite",
            severity="alta",
            title="Garantia contratual acima do limite legal",
            description=(
                f"O edital exige garantia de execução de {_percent(percent)} do valor do contrato. "
                "O limite é de 10%, com justificativa. Percentuais de até 30% só são admitidos "
                "em obras e serviços de engenharia de grande vulto (acima de R$ 200 milhões), "
                "na modalidade seguro-garantia com cláusula de retomada."
            ),
            bidder_note=(
                "A exigência excede o teto legal e restringe a participação. Cabe impugnação."
            ),
            agency_note="Reduza o percentual ao limite legal aplicável ao porte da contratação.",
            citations=evidence,
            legal_basis=["Art. 98", "Art. 99", "Art. 6º, XXII"],
        )
    ]


# --- Site visit and consortium (Art. 63 and 15) ------------------------------


def mandatory_site_visit_rule(
    extraction: EditalExtraction, pages: Mapping[int, str]
) -> list[RuleFinding]:
    visit = extraction.site_visit
    if not _is_supported(visit) or visit.value != "obrigatoria":
        return []
    return [
        RuleFinding(
            type="visita_tecnica_obrigatoria_sem_alternativa",
            severity="alta",
            title="Visita técnica obrigatória sem declaração substitutiva",
            description=(
                "O edital trata a visita ao local como obrigatória. A lei determina que o edital "
                "sempre preveja a possibilidade de substituir a vistoria por declaração formal do "
                "responsável técnico de que conhece as condições da contratação."
            ),
            bidder_note=(
                "Você pode apresentar a declaração do responsável técnico no lugar da visita. "
                "Se o edital não admitir, cabe impugnação."
            ),
            agency_note=(
                "Preveja a declaração substitutiva. Exigir a visita presencial restringe a "
                "participação de empresas de outras localidades."
            ),
            citations=_evidence(visit),
            legal_basis=["Art. 63, § 2º", "Art. 63, § 3º"],
        )
    ]


def consortium_ban_rule(
    extraction: EditalExtraction, pages: Mapping[int, str]
) -> list[RuleFinding]:
    consortium = extraction.consortium_allowed
    if not _is_supported(consortium) or consortium.value is not False:
        return []
    return [
        RuleFinding(
            type="vedacao_a_consorcio",
            severity="baixa",
            title="Participação em consórcio vedada",
            description=(
                "O edital veda a participação de empresas em consórcio. A regra da lei é admitir "
                "o consórcio, e a vedação precisa estar justificada no processo licitatório."
            ),
            bidder_note=(
                "Se a sua participação depende de consórcio, verifique se o processo traz a "
                "justificativa da vedação; sem ela, cabe questionamento."
            ),
            agency_note="Registre no processo a justificativa para vedar consórcios.",
            citations=_evidence(consortium),
            legal_basis=["Art. 15"],
        )
    ]


# --- Minimum net worth or capital (Art. 69, § 4º) -----------------------------

_NET_WORTH_PERCENT = re.compile(
    r"(?:capital(?:\s+social)?|patrim[oô]nio\s+l[ií]quido)[^.;]{0,160}?(\d{1,3}(?:[.,]\d+)?)\s*%",
    re.IGNORECASE,
)


def minimum_net_worth_rule(
    extraction: EditalExtraction, pages: Mapping[int, str]
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    for requirement in extraction.qualification_economic:
        if not _is_supported(requirement):
            continue
        match = _NET_WORTH_PERCENT.search(requirement.value or "")
        if not match:
            continue
        percent = float(match.group(1).replace(",", "."))
        if percent <= MINIMUM_NET_WORTH_MAX_PERCENT:
            continue
        findings.append(
            RuleFinding(
                type="capital_ou_patrimonio_minimo_acima_do_limite",
                severity="alta",
                title="Capital ou patrimônio líquido mínimo acima de 10%",
                description=(
                    f"O edital exige capital ou patrimônio líquido mínimo de {_percent(percent)} "
                    "do valor estimado. A lei limita essa exigência a 10%."
                ),
                bidder_note="A exigência excede o teto legal. Cabe impugnação.",
                agency_note="Reduza a exigência a no máximo 10% do valor estimado da contratação.",
                citations=_evidence(requirement),
                legal_basis=["Art. 69, § 4º"],
            )
        )
    return findings


# --- Deadline to challenge the edital (Art. 164) ------------------------------

_BUSINESS_DAYS = re.compile(r"(\d{1,2})\s*(?:\([^)]*\)\s*)?dias?\s+[uú]te(?:is|l)", re.IGNORECASE)


def challenge_deadline_rule(
    extraction: EditalExtraction, pages: Mapping[int, str]
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    subjects = (
        ("impugnar o edital", "impugnacao", extraction.impugnation_deadline),
        ("pedir esclarecimentos", "esclarecimentos", extraction.clarification_deadline),
    )
    for action, code, deadline in subjects:
        if not _is_supported(deadline):
            continue
        assert deadline.value is not None
        match = _BUSINESS_DAYS.search(deadline.value.rule or "")
        if not match or int(match.group(1)) <= CHALLENGE_DEADLINE_BUSINESS_DAYS:
            continue
        days = int(match.group(1))
        findings.append(
            RuleFinding(
                type=f"prazo_de_{code}_mais_restritivo_que_a_lei",
                severity="media",
                title=f"Prazo para {action} mais curto que o da lei",
                description=(
                    f"O edital exige que o pedido seja apresentado até {days} dias úteis antes da "
                    "abertura. A lei garante o prazo de até 3 dias úteis antes da abertura; exigir "
                    "antecedência maior reduz o prazo do interessado."
                ),
                bidder_note=(
                    "A lei garante o protocolo até 3 dias úteis antes da abertura. Na dúvida, "
                    "protocole dentro do prazo do edital e questione a cláusula."
                ),
                agency_note=(
                    "Ajuste a cláusula ao prazo legal de até 3 dias úteis antes da abertura."
                ),
                citations=_evidence(deadline),
                legal_basis=["Art. 164"],
            )
        )
    return findings


# --- Conflicting opening dates across the document ----------------------------

_OPENING_WORDS = re.compile(r"abertura|sess[aã]o\s+p[uú]blica", re.IGNORECASE)
_MONTHS = {
    name: number
    for number, name in enumerate(
        [
            "janeiro",
            "fevereiro",
            "março",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        ],
        start=1,
    )
}
_DATE = re.compile(
    r"(?P<d1>\d{1,2})/(?P<m1>\d{1,2})/(?P<y1>\d{4})"
    r"|(?P<d2>\d{1,2})º?\s+de\s+(?P<m2>[a-zç]+)\s+de\s+(?P<y2>\d{4})",
    re.IGNORECASE,
)
_MAX_QUOTE_CHARS = 200


def _date_from(match: re.Match[str]) -> dt.date | None:
    try:
        if match.group("d1"):
            return dt.date(int(match.group("y1")), int(match.group("m1")), int(match.group("d1")))
        month = _MONTHS.get(match.group("m2").lower().replace("marco", "março"))
        if month is None:
            return None
        return dt.date(int(match.group("y2")), month, int(match.group("d2")))
    except ValueError:
        return None  # e.g. 31/02/2026


def find_opening_dates(pages: Mapping[int, str]) -> dict[dt.date, Citation]:
    """Dates stated next to "abertura"/"sessão pública", with the first line that states each."""
    found: dict[dt.date, Citation] = {}
    for number in sorted(pages):
        for line in pages[number].split("\n"):
            keyword = _OPENING_WORDS.search(line)
            if not keyword:
                continue
            # Only the first date after the keyword: "abertura em 19/10/2026".
            match = _DATE.search(line, keyword.end())
            date = _date_from(match) if match else None
            if date and date not in found:
                found[date] = Citation(page=number, quote=line.strip()[:_MAX_QUOTE_CHARS])
    return found


def conflicting_opening_dates_rule(
    extraction: EditalExtraction, pages: Mapping[int, str]
) -> list[RuleFinding]:
    match_pages = {number: normalize_for_match(text) for number, text in pages.items()}
    evidence: dict[dt.date, ValidatedCitation] = {}
    # The extracted opening date counts as one of the stated dates: in table layouts
    # the date often sits away from its label and the text scan does not see it.
    opening = extraction.opening
    if _is_supported(opening):
        assert opening.value is not None
        evidence[opening.value.date] = _evidence(opening)[0]
    for date, citation in find_opening_dates(pages).items():
        if date not in evidence:
            validated = validate_citation(citation, match_pages)
            if validated.status in ("valid", "wrong_page"):
                evidence[date] = validated
    if len(evidence) < 2:
        return []
    listed = ", ".join(f"{date:%d/%m/%Y}" for date in sorted(evidence))
    citations = [evidence[date] for date in sorted(evidence)]
    return [
        RuleFinding(
            type="datas_de_abertura_divergentes",
            severity="media",
            title="O edital indica datas de abertura diferentes",
            description=(
                f"Trechos diferentes do edital indicam datas distintas para a abertura: {listed}. "
                "Modificações no edital exigem nova divulgação e a reabertura do prazo, e a "
                "divergência deixa incerto qual data vale."
            ),
            bidder_note=(
                "Peça esclarecimento sobre a data que vale e acompanhe eventuais retificações."
            ),
            agency_note=(
                "Unifique a data em todo o edital e republique, se a correção afetar o prazo."
            ),
            citations=citations,
            legal_basis=["Art. 55, § 1º"],
        )
    ]


RULES: tuple[Rule, ...] = (
    proposal_interval_rule,
    conflicting_opening_dates_rule,
    challenge_deadline_rule,
    bid_guarantee_rule,
    contract_guarantee_rule,
    minimum_net_worth_rule,
    mandatory_site_visit_rule,
    consortium_ban_rule,
)


def run_rules(extraction: EditalExtraction, pages: Mapping[int, str]) -> list[RuleFinding]:
    """Apply every rule. ``pages`` maps page number to the page's normalized text."""
    return [finding for rule in RULES for finding in rule(extraction, pages)]
