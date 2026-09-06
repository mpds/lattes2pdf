import json
import xml.etree.ElementTree as ET

import pytest

from cv_lattex.lattes import read_lattes
from cv_lattex.models import CVError
from cv_lattex.rendering import export_data
from cv_lattex.selection import Profile


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
def test_full_export_accounts_for_known_fields(fixtures, filename):
    cv = read_lattes(fixtures / filename)
    data, report = export_data(cv, Profile(full=True))
    assert not report["counts"].get("unknown")
    assert not report["counts"].get("unmapped")
    assert len(report["fields"]) == len(cv.fields)
    assert data["cv"]["name"] == "Ana Exemplo Fictícia"
    assert cv.raw_xml == (fixtures / filename).read_bytes()


def test_publication_authors_dates_and_selected_details(fixtures):
    cv = read_lattes(fixtures / "bibliography.xml")
    data, _ = export_data(cv, Profile(include=["publications.articles"]))
    article = data["cv"]["sections"]["Artigos publicados"][0]
    assert article["authors"] == ["Ana Exemplo Fictícia", "Bruno Exemplo Fictício"]
    assert article["date"] == "2024"
    assert article["doi"] == "10.0000/example.article"
    assert "Volume: 12" in article["summary"]
    assert "Pagina inicial: 10" in article["summary"]
    assert "Natureza: COMPLETO" in article["summary"]


def test_dates_do_not_invent_precision_or_ongoing_status(fixtures, tmp_path):
    tree = ET.parse(fixtures / "general.xml")
    tree.find(".//MESTRADO").set("ANO-DE-CONCLUSAO", "")
    tree.find(".//VINCULOS").set("MES-FIM", "99")
    path = tmp_path / "cv.xml"
    tree.write(path, encoding="utf-8")
    data, report = export_data(
        read_lattes(path), Profile(include=["education", "experience"])
    )
    education = data["cv"]["sections"]["Formação acadêmica"]
    masters = next(e for e in education if e["name"].startswith("Mestrado —"))
    doctorate = next(e for e in education if e["name"].startswith("Doutorado —"))
    assert masters["date"] == "Início: 2022"
    assert "end_date" not in masters
    assert doctorate["start_date"] == "2022"
    assert doctorate["end_date"] == "present"
    assert "start_date" not in next(
        e for e in education if e["name"] == "Pos doutorado"
    )
    appointment = data["cv"]["sections"]["Experiência profissional"][0]
    assert appointment["end_date"] == "2022"
    assert any("Mes fim: 99" in line for line in appointment["highlights"])
    assert any(issue["code"] == "invalid-date" for issue in report["issues"])


def test_visibility_and_language_do_not_leak_through_generic_details(fixtures):
    cv = read_lattes(fixtures / "general.xml")
    data, report = export_data(
        cv, Profile(language="en", hide_fields=["contact", "advisors", "thesis"])
    )
    text = json.dumps(data, ensure_ascii=False)
    assert "Fictional profile for demonstrating" in text
    assert "Perfil fictício para demonstrar" not in text
    assert "ana@example.org" not in text
    assert "Pessoa Orientadora" not in text
    assert "Fictional work:" not in json.dumps(data["cv"]["sections"]["Education"])
    assert "00000000000" not in text
    assert "Rua Fictícia" not in text
    assert report["counts"]["private"] > 0


def test_hidden_publication_authors_use_a_homogeneous_generic_section(fixtures):
    cv = read_lattes(fixtures / "bibliography.xml")
    data, _ = export_data(
        cv,
        Profile(
            include=["publications.articles"],
            hide_fields=["authors", "date", "links", "details"],
        ),
    )
    article = data["cv"]["sections"]["Artigos publicados"][0]
    assert set(article) == {"name"}
    assert "Catálogos abertos" in article["name"]


def test_unknown_content_blocks_full_export_and_is_reported_without_values(fixtures):
    cv = read_lattes(fixtures / "extensions.xml")
    with pytest.raises(CVError, match="Modo completo bloqueado"):
        export_data(cv, Profile(full=True))
    data, report = export_data(cv, Profile(full=True, allow_unmapped=True))
    assert report["counts"]["unknown"] > 0
    assert any("CAMPO-FUTURO" in record["path"] for record in report["fields"])
    assert "Informação relevante fictícia" not in json.dumps(
        (data, report), ensure_ascii=False
    )
    assert any(f.value == "Informação relevante fictícia" for f in cv.fields)


def test_missing_translation_falls_back_to_original_without_dropping_the_title(
    fixtures,
):
    cv = read_lattes(fixtures / "bibliography.xml")
    data, _ = export_data(cv, Profile(language="en", include=["publications.accepted"]))
    article = data["cv"]["sections"]["Accepted articles"][0]
    assert article["title"].startswith("Trabalho fictício")
    assert "date" not in article


def test_invalid_links_and_author_order_preserve_original_information(
    fixtures, tmp_path
):
    tree = ET.parse(fixtures / "bibliography.xml")
    basic = tree.find(".//DADOS-BASICOS-DO-ARTIGO")
    basic.set("DOI", "identificador incompleto")
    basic.set("HOME-PAGE-DO-TRABALHO", "javascript:invalid")
    tree.find(".//ARTIGO-PUBLICADO/AUTORES").set("ORDEM-DE-AUTORIA", "")
    path = tmp_path / "cv.xml"
    tree.write(path, encoding="utf-8")
    data, report = export_data(
        read_lattes(path), Profile(include=["publications.articles"])
    )
    article = data["cv"]["sections"]["Artigos publicados"][0]
    assert article["authors"][0] == "Bruno Exemplo Fictício"
    assert "doi" not in article and "url" not in article
    assert "identificador incompleto" in article["summary"]
    assert "javascript:invalid" in article["summary"]
    assert {"invalid-doi", "invalid-url", "author-order"} <= {
        i["code"] for i in report["issues"]
    }


def test_hiding_required_fields_changes_layout_without_reintroducing_values(fixtures):
    cv = read_lattes(fixtures / "general.xml")
    graduation = next(e for e in cv.entries if e.tag == "GRADUACAO")
    data, _ = export_data(cv, Profile(include_ids=[graduation.id]))
    assert (
        data["cv"]["sections"]["Formação acadêmica"][0]["area"] == "Curso demonstrativo"
    )
    data, _ = export_data(
        cv, Profile(include_ids=[graduation.id], hide_fields=["NOME-INSTITUICAO"])
    )
    degree = data["cv"]["sections"]["Formação acadêmica"][0]
    assert "name" in degree
    assert "Universidade Fictícia" not in json.dumps(degree, ensure_ascii=False)


def test_source_markup_is_exported_as_literal_text(fixtures, tmp_path):
    tree = ET.parse(fixtures / "bibliography.xml")
    source_text = 'Estudo #read("arquivo.txt") **literal** _ % # { } \\ $ [ ] < > & `'
    tree.find(".//DADOS-BASICOS-DO-ARTIGO").set("TITULO-DO-ARTIGO", source_text)
    path = tmp_path / "cv.xml"
    tree.write(path, encoding="utf-8")
    cv = read_lattes(path)
    data, _ = export_data(cv, Profile(include=["publications.articles"]))
    title = data["cv"]["sections"]["Artigos publicados"][0]["title"]
    assert "#read(" not in title
    assert "**literal**" not in title
    assert title.count("#text(") == 1
    assert (
        next(e for e in cv.entries if e.section == "publications.articles").title()
        == source_text
    )


def test_career_breaks_require_explicit_selection(fixtures):
    cv = read_lattes(fixtures / "general.xml")
    full, _ = export_data(cv, Profile(full=True))
    assert "Afastamentos" not in full["cv"]["sections"]
    data, report = export_data(cv, Profile(include=["leave"]))
    assert data["cv"]["sections"]["Afastamentos"][0]["name"] == "MATERNIDADE"
    assert "CPF" not in json.dumps(data)
    assert any(
        f.get("reason") == "explicit-selection" and f["status"] == "exported"
        for f in report["fields"]
    )
    assert all(f.disposition == "private" for f in cv.fields if f.tag == "LICENCA")
