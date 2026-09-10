import json
import xml.etree.ElementTree as ET

import pytest
import yaml

from cv_lattex.cli import main
from cv_lattex.lattes import read_lattes
from cv_lattex.models import CVError
from cv_lattex.rendering import export_data
from cv_lattex.selection import Profile, load_profile

SECTION = "publications.articles"
TITLE = "Artigos publicados"


def test_default_articles_preserve_missing_data_and_source(fixtures):
    source = fixtures / "articles.xml"
    cv = read_lattes(source)
    data, report = export_data(cv, Profile(include=[SECTION]))
    complete, url_only, no_authors, no_date = data["cv"]["sections"][TITLE]
    assert complete["authors"] == [
        "**Ana Exemplo Fictícia**",
        "Bruno Exemplo Fictício",
        "Clara Exemplo Fictícia",
    ]
    assert complete["date"] == 2025
    assert complete["doi"] == "10.0000/example.catalogs" and "url" not in complete
    assert complete["journal"] == "Revista Fictícia de Memória"
    assert "summary" not in complete
    assert url_only["authors"] == ["EXEMPLO, D."]
    assert url_only["url"] == "https://example.org/preservacao"
    assert "doi" not in url_only
    assert no_authors["authors"] == []
    assert no_authors["doi"] == "10.0000/example.collections"
    assert "date" not in no_date and "journal" not in no_date
    assert not report["counts"].get("unmapped")
    assert not report["issues"]
    text = json.dumps(data, ensure_ascii=False)
    for omitted in ("Natureza", "0000-0000", "Nota cadastral", "Flag", "ID-FICTICIO"):
        assert omitted not in text
    assert any(f.get("reason") == "presentation" for f in report["fields"])
    assert cv.raw_xml == source.read_bytes()
    full, full_report = export_data(cv, Profile(full=True))
    assert "Nota cadastral fictícia" in json.dumps(full, ensure_ascii=False)
    assert not full_report["counts"].get("unmapped")
    assert not any(f.get("reason") == "presentation" for f in full_report["fields"])


def test_article_options_translation_and_global_hiding(fixtures):
    cv = read_lattes(fixtures / "articles.xml")
    sections = {SECTION: {"title": "Selected articles", "show_details": True}}
    data, _ = export_data(cv, Profile(language="en", sections=sections))
    complete, electronic, *_ = data["cv"]["sections"]["Selected articles"]
    assert complete["title"] == "Open catalogs and community memory"
    assert (
        complete["journal"]
        == "Revista Fictícia de Memória, v. 12, no. 2, series Nova, p. 10-19"
    )
    assert electronic["journal"] == "Revista Fictícia de Patrimônio, v. 7, p. e204"
    assert electronic["title"] == "Preservação digital em bibliotecas comunitárias"
    data, report = export_data(
        cv,
        Profile(
            sections=sections,
            hide_fields=["authors", "links", "VOLUME", "PAGINA-INICIAL"],
        ),
    )
    complete = data["cv"]["sections"]["Selected articles"][0]
    assert complete["authors"] == []
    assert "doi" not in complete and "url" not in complete
    assert (
        complete["journal"]
        == "Revista Fictícia de Memória, n. 2, série Nova, p. final 19"
    )
    assert any(f.get("reason") == "field-filter" for f in report["fields"])
    data, _ = export_data(cv, Profile(sections=sections, hide_fields=["details"]))
    assert (
        data["cv"]["sections"]["Selected articles"][0]["journal"]
        == "Revista Fictícia de Memória"
    )


def test_section_options_hide_authors_and_links_without_filtering_records(
    fixtures, tmp_path
):
    tree = ET.parse(fixtures / "articles.xml")
    tree.find(".//DADOS-BASICOS-DO-ARTIGO").set("DOI", "identificador incompleto")
    tree.find(".//ARTIGO-PUBLICADO/AUTORES").set("ORDEM-DE-AUTORIA", "")
    source = tmp_path / "cv.xml"
    tree.write(source, encoding="utf-8")
    cv = read_lattes(source)
    data, report = export_data(
        cv, Profile(sections={SECTION: {"show_authors": False, "show_links": False}})
    )
    entries = data["cv"]["sections"][TITLE]
    assert len(entries) == 4
    assert all(
        e["authors"] == [] and "doi" not in e and "url" not in e for e in entries
    )
    assert "identificador incompleto" not in json.dumps(data)
    assert not report["issues"]
    paths = {field["path"]: field for field in report["fields"]}
    author = next(f for f in cv.fields if f.name == "NOME-COMPLETO-DO-AUTOR")
    assert paths[author.path]["reason"] == "presentation"


@pytest.mark.parametrize(
    "first,last,expected",
    [("S1", "S9", "p. S1-S9"), ("12", "12", "p. 12"), ("", "12", "p. final 12")],
)
def test_article_page_variants(fixtures, tmp_path, first, last, expected):
    tree = ET.parse(fixtures / "articles.xml")
    details = tree.find(".//DETALHAMENTO-DO-ARTIGO")
    details.set("PAGINA-INICIAL", first)
    details.set("PAGINA-FINAL", last)
    source = tmp_path / "cv.xml"
    tree.write(source, encoding="utf-8")
    data, _ = export_data(
        read_lattes(source), Profile(sections={SECTION: {"show_details": True}})
    )
    assert data["cv"]["sections"][TITLE][0]["journal"].endswith(expected)


def test_incomplete_article_and_unknown_fields_remain_distinct(fixtures, tmp_path):
    tree = ET.parse(fixtures / "articles.xml")
    basic = tree.find(".//DADOS-BASICOS-DO-ARTIGO")
    basic.set("ANO-DO-ARTIGO", "ano-incerto")
    basic.set("CAMPO-FUTURO", "Conteúdo fictício desconhecido")
    source = tmp_path / "cv.xml"
    tree.write(source, encoding="utf-8")
    cv = read_lattes(source)
    data, report = export_data(
        cv, Profile(sort="source", hide_fields=["TITULO-DO-ARTIGO"])
    )
    complete = data["cv"]["sections"][TITLE][0]
    assert complete["title"] == "Artigo publicado"
    assert complete["date"] == "ano-incerto"
    assert any(issue["code"] == "invalid-date" for issue in report["issues"])
    assert any(
        f["path"].endswith("/@CAMPO-FUTURO") and f["status"] == "unknown"
        for f in report["fields"]
    )
    with pytest.raises(CVError, match="Modo completo bloqueado"):
        export_data(cv, Profile(full=True))


@pytest.mark.parametrize(
    "sections",
    [
        {SECTION: {"show_authors": "false"}},
        {SECTION: {"show_links": 0}},
        {SECTION: {"show_details": []}},
        {"publications.accepted": {"show_details": True}},
    ],
)
def test_invalid_article_options_are_rejected(sections):
    with pytest.raises(CVError):
        Profile(sections=sections).validate()


def test_article_reference_profile_and_id_selection(fixtures, tmp_path, capsys):
    assert main(["sections", SECTION]) == 0
    reference = capsys.readouterr().out
    assert reference.startswith("usage: cv-lattex sections")
    assert all(
        option in reference for option in ("show_authors", "show_links", "show_details")
    )
    source = str(fixtures / "articles.xml")
    assert main(["inspect", source, "--section", SECTION, "--json"]) == 0
    records = json.loads(capsys.readouterr().out)["entries"]
    ids = [record["id"] for record in records]
    path = tmp_path / "selecao.profile.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "include_ids": ids[:2],
                "exclude_ids": [ids[1]],
                "sections": {
                    SECTION: {"title": "Artigos selecionados", "show_details": True}
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(CVError, match="--full"):
        load_profile(path, {"full": True})
    output = tmp_path / "cv.yaml"
    assert main(["export", source, "--profile", str(path), "-o", str(output)]) == 0
    document = yaml.safe_load(output.read_text())
    assert len(document["cv"]["sections"]["Artigos selecionados"]) == 1
    report = json.loads(output.with_suffix(".report.json").read_text())
    assert [e["id"] for e in report["entries"] if e["status"] == "selected"] == [ids[0]]
    assert next(e for e in report["entries"] if e["id"] == ids[1])["reason"] == "id"
