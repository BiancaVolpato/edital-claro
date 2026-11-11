from app.db.models import ChunkKind
from app.ingestion.chunking import chunk_pages

EDITAL = [
    # page 1
    "EDITAL DE CONCORRÊNCIA Nº 1/2026\nO Município torna público que fará licitação.\n"
    "1. DO OBJETO\n1.1. Execução de pavimentação da Rua A.",
    # page 2
    "1.2. O valor estimado é de R$ 100.000,00.\n"
    "2. DA HABILITAÇÃO\n2.1. Habilitação jurídica.\n2.2. Qualificação técnica.",
    # page 3
    "ANEXO I - MINUTA DO CONTRATO\nCONTRATO Nº XX/2026\n"
    "CLÁUSULA PRIMEIRA – DO OBJETO\n1.1. O objeto é a pavimentação.",
    # page 4
    "CLÁUSULA SEGUNDA – DA GARANTIA (Art. 96 da Lei n.º 14.133/2021)\n2.1. Garantia de 5%.\n"
    "ANEXO II\nCONCORRÊNCIA Nº 1/2026\nMODELO DE PROPOSTA\nÀ Comissão de Contratação.",
]


def _summary(pages: list[str], max_chars: int = 2000) -> list[tuple[str, str | None, int, int]]:
    return [
        (chunk.kind.value, chunk.heading, chunk.page_start, chunk.page_end)
        for chunk in chunk_pages(pages, max_chars=max_chars)
    ]


def test_chunks_follow_clauses_and_annexes_with_page_ranges() -> None:
    assert _summary(EDITAL) == [
        ("preamble", None, 1, 1),
        ("clause", "1. DO OBJETO", 1, 2),
        ("clause", "2. DA HABILITAÇÃO", 2, 2),
        ("annex", "ANEXO I - MINUTA DO CONTRATO", 3, 3),
        ("annex", "ANEXO I - MINUTA DO CONTRATO › CLÁUSULA PRIMEIRA – DO OBJETO", 3, 3),
        (
            "annex",
            "ANEXO I - MINUTA DO CONTRATO › CLÁUSULA SEGUNDA – DA GARANTIA "
            "(Art. 96 da Lei n.º 14.133/2021)",
            4,
            4,
        ),
        ("annex", "ANEXO II - MODELO DE PROPOSTA", 4, 4),
    ]


def test_chunk_text_starts_with_its_heading_and_keeps_every_line() -> None:
    chunks = chunk_pages(EDITAL)

    assert chunks[1].text == (
        "1. DO OBJETO\n1.1. Execução de pavimentação da Rua A.\n"
        "1.2. O valor estimado é de R$ 100.000,00."
    )
    original_lines = [line for page in EDITAL for line in page.split("\n")]
    chunked_lines = [line for chunk in chunks for line in chunk.text.split("\n")]
    assert chunked_lines == original_lines
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))


def test_long_sections_are_split_at_sub_item_boundaries() -> None:
    items = [f"5.{n}. " + "exigência de habilitação " * 8 for n in range(1, 9)]
    pages = ["5. DA HABILITAÇÃO\n" + "\n".join(items[:4]), "\n".join(items[4:])]

    chunks = chunk_pages(pages, max_chars=600)

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 600 for chunk in chunks)
    assert all(chunk.heading == "5. DA HABILITAÇÃO" for chunk in chunks)
    # Every chunk after the first starts at a sub-item, never in the middle of one.
    assert all(chunk.text.startswith("5.") for chunk in chunks[1:])
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 2


def test_a_single_oversized_line_is_split_to_respect_the_limit() -> None:
    chunks = chunk_pages(["x" * 2500], max_chars=1000)

    assert [len(chunk.text) for chunk in chunks] == [1000, 1000, 500]


def test_documents_without_headings_are_chunked_by_size_only() -> None:
    pages = ["linha de texto comum sem título\n" * 30, "outra linha qualquer\n" * 30]

    chunks = chunk_pages(pages, max_chars=500)

    assert len(chunks) > 2
    assert {chunk.kind for chunk in chunks} == {ChunkKind.PREAMBLE}
    assert all(len(chunk.text) <= 500 for chunk in chunks)
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 2


def test_heading_split_across_two_lines_is_merged() -> None:
    pages = [
        "10 - DO JULGAMENTO\n10.1. Menor preço.",
        "11\n- DAS IMPUGNAÇÕES\n11.1. Até 3 dias úteis.",
    ]

    assert _summary(pages) == [
        ("clause", "10 - DO JULGAMENTO", 1, 1),
        ("clause", "11 - DAS IMPUGNAÇÕES", 2, 2),
    ]


def test_list_of_annexes_is_not_mistaken_for_annex_headings() -> None:
    pages = [
        "1. DO OBJETO\n1.1. Integram este edital:\n"
        "ANEXO I - TERMO DE REFERÊNCIA\nANEXO II - MINUTA DO CONTRATO\n"
        "2. DA ABERTURA\n2.1. A sessão será pública."
    ]

    assert _summary(pages) == [
        ("clause", "1. DO OBJETO", 1, 1),
        ("clause", "2. DA ABERTURA", 1, 1),
    ]


def test_table_rows_and_sentences_are_not_headings() -> None:
    pages = [
        "1. DO OBJETO\n"
        "01 - BSTC D=0,40M H=1,00M\n"  # table row with digits
        "3 CAMINHÃO BASCULANTE\n"  # number without separator, out of sequence
        "2. CONTRATADA: empresa com sede no Município\n"  # sentence, not all caps
        "Anexo I - Termo de Referência\n"  # reference in running text
        "1.1. Texto do item."
    ]

    assert _summary(pages) == [("clause", "1. DO OBJETO", 1, 1)]


def test_numbered_heading_without_separator_counts_only_in_sequence() -> None:
    pages = [
        "ANEXO I – TERMO DE REFERÊNCIA\n1. APRESENTAÇÃO\ntexto\n2 OBJETO\ntexto\n3 JUSTIFICATIVA"
    ]

    headings = [chunk.heading for chunk in chunk_pages(pages)]

    assert headings == [
        "ANEXO I – TERMO DE REFERÊNCIA",
        "ANEXO I – TERMO DE REFERÊNCIA › 1. APRESENTAÇÃO",
        "ANEXO I – TERMO DE REFERÊNCIA › 2 OBJETO",
        "ANEXO I – TERMO DE REFERÊNCIA › 3 JUSTIFICATIVA",
    ]


def test_empty_document_yields_no_chunks() -> None:
    assert chunk_pages(["", ""]) == []
