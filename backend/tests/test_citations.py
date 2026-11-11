import logging

import pytest

from app.extraction.citations import (
    normalize_for_match,
    validate_citation,
    validate_field,
)
from app.extraction.schemas import Citation, RawField

PAGES_RAW = {
    1: "EDITAL DE CONCORRÊNCIA Nº 1/2026\nO Município de Exemplo torna público que fará licitação.",
    2: (
        "1.2. O valor máximo admitido para a contratação é de R$ 22.549.875,04 (vinte e dois\n"
        "milhões), conforme disposto no Anexo I deste Edital.\n"
        "18.1.1. Não será exigida garantia da proposta."
    ),
    3: "5.1. O prazo de execução dos serviços será de 12 (doze) meses, contados da ordem.",
}
PAGES = {number: normalize_for_match(text) for number, text in PAGES_RAW.items()}


def _status(page: int, quote: str) -> tuple[str, int]:
    result = validate_citation(Citation(page=page, quote=quote), PAGES)
    return result.status, result.page


def test_literal_quote_on_the_cited_page_is_valid() -> None:
    assert _status(2, "Não será exigida garantia da proposta.") == ("valid", 2)


def test_match_ignores_line_breaks_spacing_and_letter_case() -> None:
    quote = "é de r$ 22.549.875,04 (vinte e dois   milhões), conforme"

    assert _status(2, quote) == ("valid", 2)


def test_match_ignores_typographic_quotes_and_dashes() -> None:
    pages = {1: normalize_for_match("regime de “empreitada por preço global” – conforme projeto")}
    citation = Citation(page=1, quote='regime de "empreitada por preço global" - conforme projeto')

    assert validate_citation(citation, pages).status == "valid"


def test_a_few_wrong_characters_are_tolerated() -> None:
    # As produced by OCR: "exccução" and a missing accent.
    quote = "O prazo de exccução dos servicos será de 12 (doze) meses"

    result = validate_citation(Citation(page=3, quote=quote), PAGES)

    assert result.status == "valid"
    assert 92 <= result.match_score < 100


def test_invented_quote_is_not_found() -> None:
    quote = "O valor máximo admitido para a contratação é de R$ 1,00 (um real)"

    result = validate_citation(Citation(page=2, quote=quote), PAGES)

    assert result.status == "not_found"
    assert result.match_score < 92


@pytest.mark.parametrize(
    ("page", "quote"),
    [
        # Same sentence as the page, only the number changed.
        (2, "O valor máximo admitido para a contratação é de R$ 22.549.875,40 (vinte e dois"),
        (2, "O valor máximo admitido para a contratação é de R$ 2.549.875,04 (vinte e dois"),
        (3, "O prazo de execução dos serviços será de 18 (doze) meses, contados da ordem"),
    ],
)
def test_a_changed_number_is_never_tolerated(page: int, quote: str) -> None:
    """Fuzzy matching must not turn a near-identical sentence into proof of another value."""
    result = validate_citation(Citation(page=page, quote=quote), PAGES)

    assert result.status == "not_found"
    assert result.match_score <= 50


def test_paraphrase_is_not_found() -> None:
    assert _status(3, "os serviços devem ser executados em até doze meses")[0] == "not_found"


def test_real_quote_on_the_wrong_page_is_corrected() -> None:
    result = validate_citation(
        Citation(page=1, quote="Não será exigida garantia da proposta."), PAGES
    )

    assert (result.status, result.page, result.cited_page) == ("wrong_page", 2, 1)


def test_page_that_does_not_exist_is_handled() -> None:
    assert _status(99, "Não será exigida garantia da proposta.") == ("wrong_page", 2)
    assert _status(99, "texto que não existe em nenhuma página do documento")[0] == "not_found"


@pytest.mark.parametrize("quote", ["5%", "R$ 1,00", "sim", "   "])
def test_quotes_too_short_to_prove_anything_are_rejected(quote: str) -> None:
    assert _status(2, quote)[0] == "too_short"


def test_quote_with_elided_middle_needs_every_fragment_on_the_page() -> None:
    assert _status(2, "O valor máximo admitido [...] conforme disposto no Anexo I")[0] == "valid"
    assert _status(2, "O valor máximo admitido ... conforme disposto no Anexo XIX da Lei")[0] == (
        "not_found"
    )


def _field(value: object, citations: list[tuple[int, str]], confidence: str = "alta"):  # type: ignore[no-untyped-def]
    raw = RawField[str].model_validate(
        {
            "value": value,
            "citations": [{"page": page, "quote": quote} for page, quote in citations],
            "confidence": confidence,
        }
    )
    return validate_field(raw, PAGES, "test_field")


def test_supported_value_keeps_the_model_confidence() -> None:
    field = _field("12 meses", [(3, "O prazo de execução dos serviços será de 12 (doze) meses")])

    assert field.confidence == 0.9
    assert field.needs_review is False
    assert [c.status for c in field.citations] == ["valid"]


def test_invalid_citation_drops_confidence_and_flags_review() -> None:
    field = _field("R$ 1,00", [(2, "O valor máximo admitido para a contratação é de R$ 1,00")])

    assert field.confidence == 0.2
    assert field.needs_review is True
    assert field.value == "R$ 1,00"  # kept, but visibly unverified


def test_value_without_any_citation_is_unsupported() -> None:
    field = _field("R$ 22.549.875,04", [])

    assert field.confidence == 0.2
    assert field.needs_review is True


def test_mixed_valid_and_invalid_citations_cap_the_confidence() -> None:
    field = _field(
        "sem garantia",
        [
            (2, "Não será exigida garantia da proposta."),
            (2, "A garantia de proposta será de 1% do valor estimado"),
        ],
    )

    assert field.confidence == 0.45
    assert field.needs_review is True


def test_wrong_page_is_a_small_penalty_only() -> None:
    field = _field("sem garantia", [(1, "Não será exigida garantia da proposta.")])

    assert field.confidence == pytest.approx(0.81)
    assert field.needs_review is False
    assert field.citations[0].page == 2


def test_not_found_value_needs_no_citation() -> None:
    field = _field(None, [], confidence="alta")

    assert (field.value, field.confidence, field.needs_review) == (None, 0.9, False)


def test_low_model_confidence_alone_flags_review() -> None:
    field = _field(
        "12 meses", [(3, "O prazo de execução dos serviços será de 12 (doze) meses")], "baixa"
    )

    assert field.confidence == 0.3
    assert field.needs_review is True


def test_unconfirmed_citations_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="app.extraction.citations"):
        _field("R$ 1,00", [(2, "O valor máximo admitido para a contratação é de R$ 1,00")])

    [record] = caplog.records
    assert record.message == "citation not confirmed"
    assert record.__dict__["field"] == "test_field"
    assert record.__dict__["status"] == "not_found"
    assert record.__dict__["cited_page"] == 2
