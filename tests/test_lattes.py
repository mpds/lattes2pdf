import xml.etree.ElementTree as ET
import zipfile

import pytest

from lattes2pdf.lattes import read_lattes
from lattes2pdf.models import CVError


@pytest.mark.parametrize(
    "filename",
    [
        "minimal.xml",
        "general.xml",
        "bibliography.xml",
        "technical.xml",
        "other.xml",
        "complementary.xml",
        "latin1.xml",
    ],
)
def test_known_corpus_has_no_unclassified_fields(fixtures, filename):
    cv = read_lattes(fixtures / filename)
    assert not [f.path for f in cv.fields if f.disposition == "unknown"]
    assert len({entry.id for entry in cv.entries}) == len(cv.entries)


def test_encoding_entities_and_raw_source_are_preserved(fixtures):
    path = fixtures / "latin1.xml"
    cv = read_lattes(path)
    summary = cv.entries[0].find("TEXTO-RESUMO-CV-RH")
    assert cv.name == "Ana Exemplo Fictícia"
    assert "Formação, extensão e ação." in summary.text
    assert '"exemplo"' in summary.text
    assert "&quot;" in summary.value
    assert cv.raw_xml == path.read_bytes()


def test_new_fields_are_preserved_and_distinguished_from_known_extensions(fixtures):
    cv = read_lattes(fixtures / "extensions.xml")
    unknown = {f.name: f.value for f in cv.fields if f.disposition == "unknown"}
    assert unknown["CAMPO-FUTURO"] == "Informação relevante fictícia"
    assert unknown["OBSERVACAO"].startswith("Preservar este valor")
    assert "PCD" not in unknown
    assert "NRO-CERTIFICADO" not in unknown
    assert any(issue.code == "unknown-element" for issue in cv.issues)


@pytest.mark.parametrize(
    ("filename", "message"),
    [
        ("malformed.xml", "malformado"),
        ("external-entity.xml", "DTD"),
        ("unknown-namespace.xml", "Namespace"),
    ],
)
def test_invalid_or_unsafe_xml_is_rejected(fixtures, filename, message):
    with pytest.raises(CVError, match=message):
        read_lattes(fixtures / filename)


def test_zip_selection_does_not_extract_files(fixtures, tmp_path):
    path = tmp_path / "cv.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(fixtures / "minimal.xml", "nested/first.xml")
        archive.write(fixtures / "latin1.xml", "second.XML")
    with pytest.raises(CVError, match="--member"):
        read_lattes(path)
    cv = read_lattes(path, member="second.XML")
    assert cv.entries[0].find("TEXTO-RESUMO-CV-RH")
    assert list(tmp_path.iterdir()) == [path]


def test_zip_traversal_and_expansion_are_rejected(fixtures, tmp_path):
    path = tmp_path / "cv.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("cv.xml", b" " * 10_000)
    with pytest.raises(CVError, match="descompactado"):
        read_lattes(path, max_bytes=1000)
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(fixtures / "minimal.xml", "../cv.xml")
    with pytest.raises(CVError, match="inseguro"):
        read_lattes(path)


def test_source_limits_and_unknown_context(tmp_path):
    path = tmp_path / "cv.xml"
    path.write_text(
        '<CURRICULO-VITAE><DADOS-GERAIS NOME-COMPLETO="Exemplo"/>'
        '<FUTURO><DADOS-GERAIS NOME-COMPLETO="Não é o perfil"/>'
        "</FUTURO></CURRICULO-VITAE>"
    )
    cv = read_lattes(path)
    assert cv.name == "Exemplo"
    assert len(cv.entries) == 1
    assert any(
        f.value == "Não é o perfil" and f.disposition == "unknown" for f in cv.fields
    )
    with pytest.raises(CVError, match="limite"):
        read_lattes(path, max_bytes=20)


def test_ids_ignore_sequence_and_xml_order_without_merging_duplicates(
    fixtures, tmp_path
):
    original = read_lattes(fixtures / "bibliography.xml")
    tree = ET.parse(fixtures / "bibliography.xml")
    for element in tree.iter():
        for name in element.attrib:
            if name.startswith("SEQUENCIA-"):
                element.set(name, "999")
        element[:] = list(reversed(element[:]))
    path = tmp_path / "reordered.xml"
    tree.write(path, encoding="utf-8")
    reordered = read_lattes(path)
    assert {e.id for e in original.entries} == {e.id for e in reordered.entries}
    articles = tree.find(".//ARTIGOS-PUBLICADOS")
    articles.append(ET.fromstring(ET.tostring(articles[0])))
    tree.write(path, encoding="utf-8")
    duplicate = read_lattes(path)
    entries = [e for e in duplicate.entries if e.section == "publications.articles"]
    assert len(entries) == 2
    assert entries[0].id != entries[1].id
    assert any(issue.code == "duplicate-identity" for issue in duplicate.issues)


def test_appointments_keep_institution_and_private_fields_are_classified(fixtures):
    cv = read_lattes(fixtures / "general.xml")
    appointments = [e for e in cv.entries if e.section == "experience"]
    assert (
        appointments[0].find("NOME-INSTITUICAO").text
        == "Universidade Fictícia do Exemplo"
    )
    assert appointments[0].find("MES-INICIO") is None
    for field in cv.fields:
        if (
            field.name in {"CPF", "NOME-DA-MAE", "DATA-NASCIMENTO", "PCD"}
            or "ENDERECO-RESIDENCIAL" in field.path
        ):
            assert field.disposition == "private"
