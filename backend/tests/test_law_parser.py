from collections import Counter

import pytest

from app.law.index import LAW_14133_FILE, build_context
from app.law.parser import Provision, parse_law

SAMPLE_HTML = """
<html><head><meta http-equiv="Content-Type" content="text/html; charset=windows-1252"></head>
<body>
<p>LEI Nº 99.999, DE 1º DE JANEIRO DE 2030</p>
<p>O PRESIDENTE DA REPÚBLICA Faço saber que o Congresso Nacional decreta:</p>
<p>TÍTULO I</p><p>DISPOSIÇÕES PRELIMINARES</p>
<p>CAPÍTULO I</p><p>DA HABILITAÇÃO</p>
<p>Art. 1<sup>o</sup> A habilitação exige, no <i>caput</i>, o seguinte:
   <a href="#x">(Regulamento)</a></p>
<p>I - documentos jurídicos;</p>
<p><strike>II - redação antiga, riscada;</strike></p>
<p>II - documentos técnicos: <a href="#y">(Redação dada pela Lei nº 1, de 2031)</a></p>
<p>a) atestado de capacidade;</p>
<p>b) registro profissional;</p>
<p>§ 1º O atestado será limitado a 50% (cinquenta por cento).</p>
<p>I - vedada a limitação de tempo;</p>
<p>§ 2º (VETADO).</p>
<p>§ 2º O texto promulgado depois do veto. (Promulgação partes vetadas)</p>
<p>Seção I</p><p>Da Garantia</p>
<p>Art. 2º A garantia será de até 5% (cinco por cento).</p>
<p>Parágrafo único. Admite-se seguro-garantia.</p>
<p>Art. 3º O Código Penal passa a vigorar acrescido do seguinte artigo:</p>
<p>“Art. 337-E. Admitir contratação direta ilegal:</p>
<p>Pena - reclusão.</p>
<p>§ 1º Incorre na mesma pena quem concorre para o crime.” (NR)</p>
<p>Art. 4º Esta Lei entra em vigor na data de sua publicação.</p>
<p>Brasília, 1º de janeiro de 2030; 209º da Independência.</p>
<p>Art. 99. Texto de uma republicação parcial, depois do fecho da lei.</p>
</body></html>
""".encode("windows-1252")


@pytest.fixture(scope="module")
def sample() -> dict[str, Provision]:
    return {provision.identifier: provision for provision in parse_law(SAMPLE_HTML)}


@pytest.fixture(scope="module")
def law() -> list[Provision]:
    return parse_law(LAW_14133_FILE.read_bytes())


def test_identifiers_follow_the_hierarchy(sample: dict[str, Provision]) -> None:
    assert list(sample) == [
        "Art. 1º",
        "Art. 1º, I",
        "Art. 1º, II",
        "Art. 1º, II, a",
        "Art. 1º, II, b",
        "Art. 1º, § 1º",
        "Art. 1º, § 1º, I",
        "Art. 1º, § 2º",
        "Art. 2º",
        "Art. 2º, parágrafo único",
        "Art. 3º",
        "Art. 4º",
    ]
    assert [p.position for p in sample.values()] == list(range(12))


def test_kind_parent_and_ancestors_are_recorded(sample: dict[str, Provision]) -> None:
    alinea = sample["Art. 1º, II, a"]

    assert (alinea.kind, alinea.parent, alinea.article) == ("alinea", "Art. 1º, II", 1)
    assert alinea.text == "atestado de capacidade;"
    assert alinea.ancestors == [
        "A habilitação exige, no caput, o seguinte:",
        "documentos técnicos:",
    ]
    # An inciso under a paragraph belongs to the paragraph, not to the article head.
    assert sample["Art. 1º, § 1º, I"].parent == "Art. 1º, § 1º"
    assert sample["Art. 2º, parágrafo único"].kind == "paragraph"


def test_editorial_notes_and_struck_text_are_removed(sample: dict[str, Provision]) -> None:
    assert sample["Art. 1º"].text == "A habilitação exige, no caput, o seguinte:"
    assert sample["Art. 1º, II"].text == "documentos técnicos:"
    assert not any("riscada" in provision.text for provision in sample.values())


def test_last_wording_replaces_a_vetoed_or_older_one(sample: dict[str, Provision]) -> None:
    assert sample["Art. 1º, § 2º"].text == "O texto promulgado depois do veto."
    assert sample["Art. 1º, § 2º"].has_content is True


def test_chapter_and_section_titles_are_attached(sample: dict[str, Provision]) -> None:
    chapter = "Título I - Disposições preliminares > Capítulo I - Da habilitação"

    assert sample["Art. 1º, II, a"].heading == chapter
    assert sample["Art. 2º"].heading == f"{chapter} > Seção I - Da garantia"


def test_quoted_articles_of_another_law_stay_inside_the_quoting_article(
    sample: dict[str, Provision],
) -> None:
    amending = sample["Art. 3º"]

    assert "“Art. 337-E. Admitir contratação direta ilegal:" in amending.text
    assert "Incorre na mesma pena" in amending.text
    assert "Art. 3º, § 1º" not in sample  # the quoted paragraph is not a paragraph of Art. 3º
    assert sample["Art. 4º"].text == "Esta Lei entra em vigor na data de sua publicação."


def test_parsing_stops_at_the_closing_formula(sample: dict[str, Provision]) -> None:
    assert "Art. 99" not in sample


def test_context_combines_titles_ancestors_and_own_text(sample: dict[str, Provision]) -> None:
    assert build_context(sample["Art. 1º, II, a"]) == (
        "Título I - Disposições preliminares > Capítulo I - Da habilitação\n"
        "Art. 1º, II, a\n"
        "A habilitação exige, no caput, o seguinte:\n"
        "documentos técnicos:\n"
        "atestado de capacidade;"
    )


# --- The real Lei 14.133/2021 -----------------------------------------------------


def test_law_14133_has_every_article_once(law: list[Provision]) -> None:
    articles = [p.identifier for p in law if p.kind == "article"]
    expected = [f"Art. {n}º" if n < 10 else f"Art. {n}" for n in range(1, 195)]

    # 194 articles plus the two inserted later (44-A and 184-A).
    assert sorted(articles) == sorted([*expected, "Art. 44-A", "Art. 184-A"])
    assert Counter(p.identifier for p in law).most_common(1)[0][1] == 1


def test_law_14133_known_provisions(law: list[Provision]) -> None:
    by_id = {p.identifier: p for p in law}

    assert by_id["Art. 58, § 1º"].text == (
        "A garantia de proposta não poderá ser superior a 1% (um por cento) "
        "do valor estimado para a contratação."
    )
    assert by_id["Art. 98"].text.startswith(
        "Nas contratações de obras, serviços e fornecimentos, a garantia poderá ser de até 5%"
    )
    assert (
        by_id["Art. 67, § 2º"].heading
        == "Título II - Das licitações > Capítulo VI - Da habilitação"
    )
    assert by_id["Art. 6º, XXI, a"].parent == "Art. 6º, XXI"
    assert "impugnar edital" in by_id["Art. 164"].text
    assert by_id["Art. 174, § 3º-A"].kind == "paragraph"
    assert by_id["Art. 194"].text == "Esta Lei entra em vigor na data de sua publicação."
    # The Penal Code articles added by Art. 178 are not provisions of this law.
    assert not any(p.article == 337 for p in law)


def test_law_14133_vetoed_provisions_are_flagged(law: list[Provision]) -> None:
    without_content = [p for p in law if not p.has_content]

    assert 15 < len(without_content) < 40
    assert all("VETADO" in p.text.upper() or "REVOGAD" in p.text.upper() for p in without_content)
