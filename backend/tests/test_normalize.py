from app.ingestion.normalize import (
    clean_text,
    dehyphenate,
    normalize_pages,
    remove_repeated_headers_and_footers,
)

ZERO_WIDTH_SPACE = chr(0x200B)
NO_BREAK_SPACE = chr(0xA0)
NUL = chr(0)

BODIES = [
    "Do objeto da licitação.\nPavimentação da Rua das Flores.",
    "Da habilitação jurídica.\nAto constitutivo registrado.",
    "Da qualificação técnica.\nAtestado de capacidade emitido pelo CREA.",
    "Do julgamento das propostas.\nMenor preço global.",
    "Dos recursos administrativos.\nPrazo de três dias úteis.",
    "Das sanções.\nMulta de até dez por cento.",
]


def _page(number: int, body: str) -> str:
    return f"PREFEITURA DE EXEMPLO\nSecretaria de Obras\n{body}\nPágina {number} de 6"


def test_clean_text_removes_invisible_characters_and_extra_spaces() -> None:
    raw = (
        f"1{ZERO_WIDTH_SPACE}- DA   LICITAÇÃO{NO_BREAK_SPACE} \r\n"
        f"{ZERO_WIDTH_SPACE}1.1. Do\tObjeto{NUL}\n\n\n\n  fim  "
    )

    assert clean_text(raw) == "1- DA LICITAÇÃO\n1.1. Do Objeto\n\nfim"


def test_dehyphenate_joins_words_split_at_line_end() -> None:
    assert dehyphenate("exigências de habili-\ntação") == "exigências de habilitação"


def test_dehyphenate_keeps_hyphens_that_are_not_line_break_splits() -> None:
    # Next line starts with an uppercase letter: a compound name, not a split word.
    assert dehyphenate("conforme o Decreto-\nLei nº 200") == "conforme o Decreto-\nLei nº 200"
    # A dash used as a bullet or separator.
    assert dehyphenate("itens:\n- areia\n- brita") == "itens:\n- areia\n- brita"
    # A hyphen in the middle of a line is untouched.
    assert dehyphenate("técnico-profissional") == "técnico-profissional"


def test_repeated_headers_and_page_numbers_are_removed() -> None:
    pages = [_page(number, body) for number, body in enumerate(BODIES, start=1)]

    assert remove_repeated_headers_and_footers(pages) == BODIES


def test_header_missing_on_some_pages_is_still_removed_where_present() -> None:
    pages = [_page(number, body) for number, body in enumerate(BODIES[:5], start=1)]
    pages.append("ANEXO I\nPlanilha orçamentária\nItem único\nTotal geral")  # no letterhead

    result = remove_repeated_headers_and_footers(pages)

    assert result[:5] == BODIES[:5]
    assert result[5] == pages[5]


def test_lines_repeated_in_the_middle_of_pages_are_kept() -> None:
    repeated = "CLÁUSULA REPETIDA NO MEIO"
    pages = [
        "\n".join([*body.split("\n"), "linha extra", repeated, "outra linha", *body.split("\n")])
        for body in BODIES
    ]

    result = remove_repeated_headers_and_footers(pages)

    assert all(repeated in page for page in result)


def test_short_documents_are_left_untouched() -> None:
    pages = [_page(number, body) for number, body in enumerate(BODIES[:3], start=1)]

    assert remove_repeated_headers_and_footers(pages) == pages


def test_normalize_pages_keeps_one_output_per_input_page() -> None:
    raw = ["   ", f"Texto{ZERO_WIDTH_SPACE} com habili-\ntação", ""]

    assert normalize_pages(raw) == ["", "Texto com habilitação", ""]
