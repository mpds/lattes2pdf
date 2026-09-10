import json
import xml.etree.ElementTree as ET

import pytest
import yaml

from cv_lattex.lattes import read_lattes
from cv_lattex.models import CVError
from cv_lattex.rendering import export_data
from cv_lattex.selection import Profile, load_profile

SELF_ID = "0000000000000001"
OTHER_ID = "0000000000000002"


@pytest.mark.parametrize(
    "name_case,expected",
    [
        ("original", ["BRUNO d'ÁVILA", "**SILVA, ANA**", "Clara de Souza"]),
        ("upper", ["BRUNO D'ÁVILA", "**SILVA, ANA**", "CLARA DE SOUZA"]),
        ("title", ["Bruno D'Ávila", "**Silva, Ana**", "Clara De Souza"]),
    ],
)
def test_author_formatting_preserves_source_order_and_header(
    fixtures, name_case, expected
):
    source = fixtures / "authors.xml"
    cv = read_lattes(source)
    data, report = export_data(cv, Profile(authors={"name_case": name_case}))
    first, second = data["cv"]["sections"]["Artigos publicados"]
    assert first["authors"] == expected
    assert second["authors"][0].count("**") == 2
    assert data["cv"]["name"] == "Ana da Silva"
    assert first["title"] == "Memória digital e acervos abertos"
    assert cv.raw_xml == source.read_bytes()
    assert (
        next(f for f in cv.fields if f.name == "NOME-COMPLETO-DO-AUTOR").text
        == "SILVA, ANA"
    )
    assert SELF_ID not in json.dumps(data) and OTHER_ID not in json.dumps(data)
    identity_fields = [
        f
        for f in report["fields"]
        if f["path"].endswith(("/@NUMERO-IDENTIFICADOR", "/@NRO-ID-CNPQ"))
    ]
    assert identity_fields and all(
        f["status"] == "administrative" for f in identity_fields
    )


@pytest.mark.parametrize(
    "authors,bold_index",
    [
        ([("Silva, A.", SELF_ID), ("Ana da Silva", "")], 0),
        ([("Ana da Silva", "")], 0),
        ([("Ana da Silva", OTHER_ID)], None),
        ([("ANA DA SILVA", "")], None),
        ([("Ana da Sílva", "")], None),
        ([("Ana  da Silva", "")], None),
        ([("Silva, A.", "")], None),
        ([("Ana da Silva", ""), ("Ana da Silva", "")], None),
        ([("Ana da Silva", SELF_ID), ("Silva, A.", SELF_ID)], None),
        ([("Ana da Silva", OTHER_ID), ("Ana da Silva", "")], 1),
    ],
)
def test_self_matching_uses_original_identity_and_rejects_ambiguity(
    fixtures, tmp_path, authors, bold_index
):
    tree = ET.parse(fixtures / "authors.xml")
    article = tree.find(".//ARTIGO-PUBLICADO")
    for author in article.findall("AUTORES"):
        article.remove(author)
    for index, (name, identifier) in enumerate(authors):
        ET.SubElement(
            article,
            "AUTORES",
            {
                "NOME-COMPLETO-DO-AUTOR": name,
                "NRO-ID-CNPQ": identifier,
                "ORDEM-DE-AUTORIA": str(index + 1),
            },
        )
    source = tmp_path / "cv.xml"
    tree.write(source, encoding="utf-8")
    # Formatting makes different spellings look alike; it must not affect identity.
    data, report = export_data(
        read_lattes(source), Profile(authors={"name_case": "upper"})
    )
    rendered_authors = data["cv"]["sections"]["Artigos publicados"][0]["authors"]
    expected = [
        f"**{name.upper()}**" if index == bold_index else name.upper()
        for index, (name, _) in enumerate(authors)
    ]
    assert rendered_authors == expected
    assert not report["issues"]


def test_citation_name_alone_is_not_an_exact_full_name_match(fixtures, tmp_path):
    tree = ET.parse(fixtures / "authors.xml")
    author = tree.find(".//ARTIGO-PUBLICADO/AUTORES")
    author.set("NOME-COMPLETO-DO-AUTOR", "")
    author.set("NRO-ID-CNPQ", "")
    author.set("NOME-PARA-CITACAO", "Ana da Silva")
    source = tmp_path / "cv.xml"
    tree.write(source, encoding="utf-8")
    data, _ = export_data(read_lattes(source), Profile())
    assert all(
        "**" not in name
        for name in data["cv"]["sections"]["Artigos publicados"][0]["authors"]
    )


@pytest.mark.parametrize("full", [False, True])
def test_global_author_options_cover_publications_and_generic_entries(fixtures, full):
    cv = read_lattes(fixtures / "authors.xml")
    data, _ = export_data(cv, Profile(full=full, authors={"name_case": "title"}))
    assert data["cv"]["sections"]["Artigos publicados"][0]["authors"] == [
        "Bruno D'Ávila",
        "**Silva, Ana**",
        "Clara De Souza",
    ]
    software = next(
        entries
        for entries in data["cv"]["sections"].values()
        if isinstance(entries[0], dict) and entries[0].get("name") == "Acervo Aberto"
    )[0]
    assert software["summary"] == "Autores: Bruno D'Ávila, **Ana Da Silva**"
    plain, _ = export_data(cv, Profile(full=full, authors={"highlight_self": False}))
    assert "**" not in json.dumps(plain["cv"], ensure_ascii=False)


def test_identity_survives_hidden_metadata_without_reintroducing_names(fixtures):
    cv = read_lattes(fixtures / "authors.xml")
    data, report = export_data(cv, Profile(hide_fields=["NOME-COMPLETO-DO-AUTOR"]))
    assert data["cv"]["sections"]["Artigos publicados"][0]["authors"] == [
        "**SILVA, A.**"
    ]
    assert all(
        f["status"] == "excluded"
        for f in report["fields"]
        if f["path"].endswith("/@NOME-COMPLETO-DO-AUTOR")
    )
    hidden, _ = export_data(cv, Profile(hide_fields=["authors"]))
    assert all(
        e["authors"] == [] for e in hidden["cv"]["sections"]["Artigos publicados"]
    )
    assert "BRUNO" not in json.dumps(hidden)


@pytest.mark.parametrize(
    "authors",
    [
        None,
        [],
        "upper",
        {"case": "upper"},
        {"name_case": "camelcase"},
        {"name_case": []},
        {"highlight_self": "false"},
        {"highlight_self": 1},
    ],
)
def test_author_profile_rejects_invalid_options(tmp_path, authors):
    profile = tmp_path / "profile.yaml"
    profile.write_text(yaml.safe_dump({"authors": authors}), encoding="utf-8")
    with pytest.raises(CVError, match="authors"):
        load_profile(profile)


def test_profile_loads_global_author_options(tmp_path):
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "authors:\n  name_case: title\n  highlight_self: false\nfull: true\n",
        encoding="utf-8",
    )
    loaded = load_profile(profile)
    assert loaded.authors == {"name_case": "title", "highlight_self": False}
    assert loaded.full
