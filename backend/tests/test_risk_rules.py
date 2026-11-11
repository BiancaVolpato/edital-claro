"""Unit tests of the deterministic risk rules."""

import datetime as dt
from typing import Any

import pytest

from app.extraction.schemas import EditalExtraction, is_list_field
from app.law.index import LAW_14133_FILE
from app.law.parser import parse_law
from app.risks.rules import (
    RULES,
    RuleFinding,
    bid_guarantee_rule,
    business_days_between,
    challenge_deadline_rule,
    conflicting_opening_dates_rule,
    consortium_ban_rule,
    contract_guarantee_rule,
    find_opening_dates,
    mandatory_site_visit_rule,
    minimum_net_worth_rule,
    proposal_interval_rule,
    run_rules,
)

NOTHING: dict[str, Any] = {"value": None, "citations": [], "confidence": 0.9, "needs_review": False}
NO_PAGES: dict[int, str] = {}


def confirmed(value: Any, page: int = 1, status: str = "valid") -> dict[str, Any]:
    """An extracted field backed by a citation with the given validation status."""
    return {
        "value": value,
        "citations": [
            {
                "page": page,
                "quote": f"trecho do edital que comprova {value}",
                "status": status,
                "cited_page": page,
                "match_score": 100.0 if status == "valid" else 40.0,
            }
        ],
        "confidence": 0.9 if status == "valid" else 0.2,
        "needs_review": status != "valid",
    }


def edital(**fields: Any) -> EditalExtraction:
    data = {name: [] if is_list_field(name) else NOTHING for name in EditalExtraction.model_fields}
    return EditalExtraction.model_validate({**data, **fields})


def dated(
    published: str, opens: str, criterion: str = "menor_preco", **fields: Any
) -> EditalExtraction:
    return edital(
        publication_date=confirmed(published),
        opening=confirmed({"date": opens, "time": "09:00"}),
        judgment_criterion=confirmed(criterion),
        **fields,
    )


def types(findings: list[RuleFinding]) -> list[str]:
    return [finding.type for finding in findings]


# --- Counting business days (Art. 183) ----------------------------------------


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2026-10-02", "2026-10-05", 1),  # Friday -> Monday: the start day is excluded
        ("2026-10-05", "2026-10-09", 4),  # Monday -> Friday
        ("2026-10-01", "2026-10-15", 10),  # Thursday -> Thursday two weeks later
        ("2026-10-03", "2026-10-04", 0),  # Saturday -> Sunday
        ("2026-10-10", "2026-10-10", 0),
    ],
)
def test_business_days_exclude_the_first_day_and_weekends(
    start: str, end: str, expected: int
) -> None:
    assert (
        business_days_between(dt.date.fromisoformat(start), dt.date.fromisoformat(end)) == expected
    )


# --- Minimum interval for proposals (Art. 55) ----------------------------------


def test_interval_below_the_minimum_is_a_high_risk() -> None:
    [finding] = proposal_interval_rule(dated("2026-10-01", "2026-10-09"), NO_PAGES)

    assert finding.type == "prazo_de_propostas_insuficiente"
    assert finding.severity == "alta"
    assert "6 dias úteis" in finding.description
    assert finding.legal_basis == ["Art. 55, II, a", "Art. 183"]
    assert len(finding.citations) == 2  # publication date and opening date


def test_interval_at_the_minimum_is_flagged_because_of_holidays() -> None:
    [finding] = proposal_interval_rule(dated("2026-10-01", "2026-10-15"), NO_PAGES)

    assert (finding.type, finding.severity) == ("prazo_de_propostas_no_limite", "baixa")


def test_interval_enough_only_for_common_works_is_flagged() -> None:
    [finding] = proposal_interval_rule(dated("2026-10-01", "2026-10-22"), NO_PAGES)  # 15 days

    assert finding.type == "prazo_de_propostas_depende_da_classificacao_da_obra"
    assert finding.legal_basis == ["Art. 55, II, a", "Art. 55, II, b"]


def test_interval_long_enough_for_any_work_is_fine() -> None:
    assert proposal_interval_rule(dated("2026-10-01", "2026-11-09"), NO_PAGES) == []  # 27 days


def test_integrated_contracting_requires_sixty_business_days() -> None:
    extraction = dated(
        "2026-10-01", "2026-11-09", execution_regime=confirmed("contratacao_integrada")
    )

    [finding] = proposal_interval_rule(extraction, NO_PAGES)

    assert finding.type == "prazo_de_propostas_insuficiente"
    assert "60 dias úteis" in finding.description
    assert finding.legal_basis[0] == "Art. 55, II, c"


def test_technique_and_price_requires_thirty_five_business_days() -> None:
    [finding] = proposal_interval_rule(
        dated("2026-10-01", "2026-11-09", "tecnica_e_preco"), NO_PAGES
    )

    assert finding.legal_basis[0] == "Art. 55, IV"


def test_opening_before_the_edital_date_is_reported_as_inconsistent() -> None:
    [finding] = proposal_interval_rule(dated("2026-10-20", "2026-10-19"), NO_PAGES)

    assert (finding.type, finding.severity) == ("datas_inconsistentes", "alta")


def test_interval_rule_ignores_dates_without_a_confirmed_quote() -> None:
    extraction = edital(
        publication_date=confirmed("2026-10-01", status="not_found"),
        opening=confirmed({"date": "2026-10-05", "time": None}),
        judgment_criterion=confirmed("menor_preco"),
    )

    assert proposal_interval_rule(extraction, NO_PAGES) == []


def test_interval_rule_needs_to_know_the_criterion_or_regime() -> None:
    extraction = edital(
        publication_date=confirmed("2026-10-01"),
        opening=confirmed({"date": "2026-10-05", "time": None}),
    )

    assert proposal_interval_rule(extraction, NO_PAGES) == []


# --- Guarantees (Art. 58, 98 and 99) ------------------------------------------


@pytest.mark.parametrize(
    ("guarantee", "expected"),
    [
        ({"required": True, "percent": 2.0}, ["garantia_de_proposta_acima_do_limite"]),
        ({"required": True, "percent": 1.0}, []),
        ({"required": True, "percent": None}, []),
        ({"required": False, "percent": None}, []),
    ],
)
def test_bid_guarantee_limit(guarantee: dict[str, Any], expected: list[str]) -> None:
    assert (
        types(bid_guarantee_rule(edital(bid_guarantee=confirmed(guarantee)), NO_PAGES)) == expected
    )


@pytest.mark.parametrize(
    ("percent", "estimated_value", "expected"),
    [
        (5.0, 500_000.0, []),
        (8.0, 500_000.0, ["garantia_contratual_acima_de_5"]),
        (12.0, 500_000.0, ["garantia_contratual_acima_do_limite"]),
        (20.0, 300_000_000.0, []),  # large works: up to 30% (Art. 99)
        (40.0, 300_000_000.0, ["garantia_contratual_acima_do_limite"]),
        (12.0, None, ["garantia_contratual_acima_do_limite"]),  # unknown value: not large works
    ],
)
def test_contract_guarantee_limits(
    percent: float, estimated_value: float | None, expected: list[str]
) -> None:
    extraction = edital(
        contract_guarantee=confirmed({"required": True, "percent": percent}),
        estimated_value=confirmed(estimated_value) if estimated_value else NOTHING,
    )

    findings = contract_guarantee_rule(extraction, NO_PAGES)

    assert types(findings) == expected
    if findings:
        assert {"media": "Art. 98", "alta": "Art. 99"}[findings[0].severity] in findings[
            0
        ].legal_basis


def test_unverified_guarantee_is_not_used_by_the_rules() -> None:
    extraction = edital(
        bid_guarantee=confirmed({"required": True, "percent": 5.0}, status="not_found")
    )

    assert bid_guarantee_rule(extraction, NO_PAGES) == []


# --- Site visit, consortium, net worth, deadlines ------------------------------


@pytest.mark.parametrize(
    ("visit", "expected"),
    [
        ("obrigatoria", ["visita_tecnica_obrigatoria_sem_alternativa"]),
        ("facultativa", []),
        ("nao_exigida", []),
    ],
)
def test_mandatory_site_visit(visit: str, expected: list[str]) -> None:
    assert (
        types(mandatory_site_visit_rule(edital(site_visit=confirmed(visit)), NO_PAGES)) == expected
    )


@pytest.mark.parametrize(("allowed", "expected"), [(False, ["vedacao_a_consorcio"]), (True, [])])
def test_consortium_ban(allowed: bool, expected: list[str]) -> None:
    findings = consortium_ban_rule(edital(consortium_allowed=confirmed(allowed)), NO_PAGES)

    assert types(findings) == expected
    assert consortium_ban_rule(edital(), NO_PAGES) == []  # not stated: nothing to say


@pytest.mark.parametrize(
    ("requirement", "expected"),
    [
        ("Patrimônio líquido mínimo de 15% (quinze por cento) do valor estimado", 1),
        ("Capital social mínimo correspondente a 12,5% do valor estimado da contratação", 1),
        ("Patrimônio líquido mínimo de 10% do valor estimado", 0),
        ("Capital social mínimo de R$ 50.000,00", 0),
        ("Índice de Liquidez Geral (LG) igual ou superior a 1,5", 0),
    ],
)
def test_minimum_net_worth_limit(requirement: str, expected: int) -> None:
    extraction = edital(qualification_economic=[confirmed(requirement)])

    findings = minimum_net_worth_rule(extraction, NO_PAGES)

    assert len(findings) == expected
    if findings:
        assert findings[0].legal_basis == ["Art. 69, § 4º"]


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        (
            "até 5 (cinco) dias úteis antes da data de abertura",
            ["prazo_de_impugnacao_mais_restritivo_que_a_lei"],
        ),
        ("até 3 (três) dias úteis anteriores à data fixada para abertura", []),
        ("até 2 dias úteis antes da abertura", []),
        ("conforme o art. 164 da Lei 14.133/2021", []),
    ],
)
def test_challenge_deadline(rule: str, expected: list[str]) -> None:
    extraction = edital(impugnation_deadline=confirmed({"date": None, "rule": rule}))

    assert types(challenge_deadline_rule(extraction, NO_PAGES)) == expected


def test_clarification_deadline_is_checked_too() -> None:
    extraction = edital(
        clarification_deadline=confirmed(
            {"date": None, "rule": "até 5 dias úteis antes da abertura"}
        )
    )

    assert types(challenge_deadline_rule(extraction, NO_PAGES)) == [
        "prazo_de_esclarecimentos_mais_restritivo_que_a_lei"
    ]


# --- Conflicting opening dates across the document -----------------------------

PAGES_WITH_TWO_DATES = {
    1: "CONCORRÊNCIA Nº 1/2026\nDATA DA ABERTURA: 19/10/2026 ÀS 09H00MIN",
    3: "2.1. A abertura da sessão pública ocorrerá às 9h do dia 20 de outubro de 2026.",
    9: "Lauro Muller, 1º de outubro de 2026.",  # a date, but not an opening date
}


def test_opening_dates_are_read_from_lines_that_mention_the_opening() -> None:
    dates = find_opening_dates(PAGES_WITH_TWO_DATES)

    assert sorted(dates) == [dt.date(2026, 10, 19), dt.date(2026, 10, 20)]
    assert dates[dt.date(2026, 10, 20)].page == 3


def test_different_opening_dates_are_reported_with_both_quotes() -> None:
    [finding] = conflicting_opening_dates_rule(edital(), PAGES_WITH_TWO_DATES)

    assert (finding.type, finding.severity) == ("datas_de_abertura_divergentes", "media")
    assert "19/10/2026, 20/10/2026" in finding.description
    assert [c.page for c in finding.citations] == [1, 3]
    assert all(c.status == "valid" for c in finding.citations)


def test_the_same_opening_date_written_twice_is_fine() -> None:
    pages = {
        1: "DATA DA ABERTURA: 19/10/2026",
        2: "ABERTURA: ÀS 09H00MIN DO DIA 19 DE OUTUBRO DE 2026.",
    }

    assert conflicting_opening_dates_rule(edital(), pages) == []


def test_invalid_calendar_dates_are_ignored() -> None:
    assert (
        find_opening_dates({1: "Abertura em 31/02/2026", 2: "abertura: 30 de fevereiro de 2026"})
        == {}
    )


# --- All rules together ---------------------------------------------------------

WORST_EDITAL = dict(
    publication_date=confirmed("2026-10-01"),
    opening=confirmed({"date": "2026-10-05", "time": "09:00"}),
    judgment_criterion=confirmed("menor_preco"),
    impugnation_deadline=confirmed({"date": None, "rule": "até 5 dias úteis antes da abertura"}),
    bid_guarantee=confirmed({"required": True, "percent": 3.0}),
    contract_guarantee=confirmed({"required": True, "percent": 15.0}),
    estimated_value=confirmed(500_000.0),
    site_visit=confirmed("obrigatoria"),
    consortium_allowed=confirmed(False),
    qualification_economic=[confirmed("Patrimônio líquido mínimo de 20% do valor estimado")],
)


def test_every_rule_fires_on_an_edital_that_breaks_them_all() -> None:
    findings = run_rules(edital(**WORST_EDITAL), PAGES_WITH_TWO_DATES)

    assert sorted(types(findings)) == sorted(
        [
            "prazo_de_propostas_insuficiente",
            "datas_de_abertura_divergentes",
            "prazo_de_impugnacao_mais_restritivo_que_a_lei",
            "garantia_de_proposta_acima_do_limite",
            "garantia_contratual_acima_do_limite",
            "capital_ou_patrimonio_minimo_acima_do_limite",
            "visita_tecnica_obrigatoria_sem_alternativa",
            "vedacao_a_consorcio",
        ]
    )
    assert len({rule.__name__ for rule in RULES}) == len(RULES) == 8
    assert all(finding.citations and finding.legal_basis for finding in findings)


def test_every_provision_cited_by_the_rules_exists_in_the_law() -> None:
    """The rules name provisions by identifier; each one must be in the official text."""
    identifiers = {p.identifier for p in parse_law(LAW_14133_FILE.read_bytes()) if p.has_content}
    extractions = [
        edital(**WORST_EDITAL),
        dated("2026-10-01", "2026-10-15"),
        dated("2026-10-01", "2026-10-22"),
        dated("2026-10-01", "2026-10-09", execution_regime=confirmed("contratacao_integrada")),
        dated("2026-10-01", "2026-10-09", execution_regime=confirmed("contratacao_semi_integrada")),
        dated("2026-10-01", "2026-10-09", "tecnica_e_preco"),
        dated("2026-10-20", "2026-10-19"),
        edital(contract_guarantee=confirmed({"required": True, "percent": 8.0})),
    ]
    cited = {
        identifier
        for extraction in extractions
        for finding in run_rules(extraction, PAGES_WITH_TWO_DATES)
        for identifier in finding.legal_basis
    }

    assert len(cited) >= 12
    assert cited <= identifiers, sorted(cited - identifiers)


def test_a_clean_edital_has_no_rule_findings() -> None:
    extraction = edital(
        publication_date=confirmed("2026-10-01"),
        opening=confirmed({"date": "2026-11-16", "time": "09:00"}),
        judgment_criterion=confirmed("menor_preco"),
        bid_guarantee=confirmed({"required": False, "percent": None}),
        contract_guarantee=confirmed({"required": True, "percent": 5.0}),
        site_visit=confirmed("facultativa"),
        consortium_allowed=confirmed(True),
    )

    assert run_rules(extraction, {1: "DATA DA ABERTURA: 16/11/2026"}) == []


def test_the_extracted_opening_date_is_compared_with_the_dates_in_the_text() -> None:
    """In table layouts only the extraction finds the date; it still takes part."""
    extraction = edital(opening=confirmed({"date": "2026-10-21", "time": "09:00"}))

    [finding] = conflicting_opening_dates_rule(extraction, {1: "DATA DA ABERTURA: 19/10/2026"})

    assert "19/10/2026, 21/10/2026" in finding.description
    assert len(finding.citations) == 2


def test_the_extracted_date_agreeing_with_the_text_is_fine() -> None:
    extraction = edital(opening=confirmed({"date": "2026-10-19", "time": "09:00"}))

    assert conflicting_opening_dates_rule(extraction, {1: "DATA DA ABERTURA: 19/10/2026"}) == []
