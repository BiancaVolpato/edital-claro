"""Classifying requirements and reading their numbers (pure functions)."""

import pytest

from app.eligibility.requirements import (
    Quantity,
    certificate_kinds,
    classify,
    councils,
    is_conditional_on_indices,
    parse_money,
    parse_number,
    parse_percent,
    parse_quantities,
)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (
            "a) Apresentar Atestado de Visita Técnica, nos termos do item 6.14 (opcional).",
            "visita_tecnica",
        ),
        ("Declaração de cumprimento das normas trabalhistas relativas a menores", "declaracao"),
        (
            "f.6) A licitante deverá apresentar atestado de capacidade técnica de PAVIMENTAÇÃO",
            "atestado",
        ),
        (
            "Profissional detentor de Certificado de Acervo Técnico, emitido pelo CREA",
            "atestado",
        ),
        (
            "b) Certidão de Registro e Quitação de Pessoa Jurídica na entidade "
            "profissional competente",
            "registro_profissional",
        ),
        ("Registro da empresa no CREA ou no CAU", "registro_profissional"),
        ("Capital social mínimo de R$ 300.000,00", "capital_ou_patrimonio"),
        (
            "c.5) A empresa que apresentar resultado menor que 1.00 em qualquer dos índices deverá "
            "comprovar patrimônio líquido de 10% (dez por cento) do valor estimado da contratação.",
            "capital_ou_patrimonio",
        ),
        ("c.1) Índice de Liquidez Geral (ILG) maior ou igual a 1.00", "indices_contabeis"),
        (
            "a) Balanço Patrimonial e demonstração de resultado dos dois últimos exercícios",
            "balanco",
        ),
        (
            "a) Certidões negativas ou positivas com efeito de negativas das Fazendas Federal, "
            "Estadual e Municipal;",
            "certidao",
        ),
        ("Certidão de regularidade do FGTS", "certidao"),
        ("Certidão Negativa de Débitos Trabalhistas (CNDT)", "certidao"),
        ("Certidão negativa de falência ou insolvência civil", "certidao"),
        ("a) Prova de inscrição no Cadastro Nacional de Pessoa Jurídica (CNPJ);", "cnpj"),
        ("Contrato social com objeto social compatível com o objeto da licitação", "objeto_social"),
        ("d) prova de inscrição no cadastro de contribuintes estadual (se houver)", "outro"),
        ("b) Ato constitutivo, estatuto ou contrato social em vigor", "outro"),
    ],
)
def test_requirements_are_classified(text: str, kind: str) -> None:
    assert classify(text) == kind


def test_one_requirement_can_name_several_certificates() -> None:
    text = "Certidões negativas das Fazendas Federal, Estadual e Municipal"

    assert certificate_kinds(text) == ["federal", "estadual", "municipal"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [("3.404", 3404.0), ("1.500,50", 1500.5), ("2,5", 2.5), ("10", 10.0), ("1.000.000", 1e6)],
)
def test_brazilian_numbers_are_parsed(text: str, expected: float) -> None:
    assert parse_number(text) == expected


def test_money_and_percentages_are_read() -> None:
    assert parse_money("Capital social mínimo de R$ 381.000,00 (trezentos...)") == [381000.0]
    assert parse_percent("patrimônio líquido de 10% (dez por cento) do valor estimado") == [10.0]
    assert parse_percent("no mínimo 5 por cento") == [5.0]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "PAVIMENTAÇÃO EM ASFALTICO COM METRAGEM MINIMA DE 3.404 M2 (tres mil...)",
            [Quantity(3404.0, "m2", "3.404 m2")],
        ),
        (
            "execução de 1.200 m² de pavimento e 300 m de meio-fio",
            [
                Quantity(1200.0, "m2", "1.200 m²"),
                Quantity(300.0, "m", "300 m"),
            ],
        ),
        ("rede de 1,5 km", [Quantity(1500.0, "m", "1,5 km")]),
        ("500 metros quadrados", [Quantity(500.0, "m2", "500 metros quadrados")]),
        ("80 m³ de concreto", [Quantity(80.0, "m3", "80 m³")]),
        ("2.000 kg de aço", [Quantity(2.0, "t", "2.000 kg")]),
        ("instalação de 12 unidades", [Quantity(12.0, "un", "12 unidades")]),
    ],
)
def test_quantities_are_read_and_converted(text: str, expected: list[Quantity]) -> None:
    assert parse_quantities(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "prazo de 5 meses",
        "conforme o item 3.5 do edital e o art. 67 da Lei 14.133",
        "índice maior ou igual a 1.00 (um.zero.zero)",
        "50% do quantitativo",
        "valor de R$ 3.809.907,22 m",  # money is never a quantity
    ],
)
def test_text_without_quantities_yields_none(text: str) -> None:
    assert parse_quantities(text) == []


def test_conditional_net_worth_and_councils_are_detected() -> None:
    assert is_conditional_on_indices("Se ILG < 1, deverá ser comprovado patrimônio líquido")
    assert not is_conditional_on_indices("Patrimônio líquido mínimo de 10% do valor estimado")
    assert councils("registro no CREA/CAU") == {"CREA", "CAU"}
    assert councils("registro no Conselho competente") == set()
