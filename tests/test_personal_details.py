import json
import xml.etree.ElementTree as ET
from importlib.resources import files

import pytest

from lattes2pdf.cli import PRESETS, main
from lattes2pdf.lattes import read_lattes
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import Profile, load_profile


@pytest.mark.parametrize("preset", PRESETS)
def test_presets_include_scholarship_and_award_institution_but_not_birth(
    fixtures, preset
):
    cv = read_lattes(fixtures / "personal-details.xml")
    profile = load_profile(files("lattes2pdf").joinpath("presets", preset + ".yaml"))
    data, report = export_data(cv, profile)
    sections = data["cv"]["sections"]
    education = sections["Formação acadêmica/titulação"]
    assert (
        "Bolsista: Fundação Exemplo de Pesquisa, FEP, Brasil" in education[0]["summary"]
    )
    assert "Bolsista" not in json.dumps(education[1], ensure_ascii=False)
    if preset == "resumido":
        assert "Prêmios e títulos" not in sections
    else:
        award, missing_institution = sections["Prêmios e títulos"]
        assert award == {
            "name": "Prêmio de destaque científico",
            "date": 2024,
            "summary": "Associação Exemplo de Ciência",
        }
        assert "summary" not in missing_institution
    assert "custom_connections" not in data["cv"]
    fields = {f["path"]: f for f in report["fields"]}
    for source in cv.fields:
        if source.name == "DATA-NASCIMENTO":
            assert fields[source.path]["status"] == "private"
        if source.text == "FEP":
            assert fields[source.path]["status"] == "exported"
    assert "NAO-EXIBIR" not in json.dumps(data)
    assert not report["counts"].get("unknown") and not report["counts"].get("unmapped")
    assert cv.raw_xml == (fixtures / "personal-details.xml").read_bytes()


def test_scholarship_and_award_toggles_hide_only_the_requested_context(fixtures):
    cv = read_lattes(fixtures / "personal-details.xml")
    data, report = export_data(
        cv,
        Profile(
            sections={
                "education": {"show_scholarship": False, "show_thesis": True},
                "awards": {"show_institution": False},
            }
        ),
    )
    text = json.dumps(data, ensure_ascii=False)
    assert "Bolsista" not in text and "Fundação Exemplo" not in text
    assert "Associação Exemplo" not in text
    assert "Título do trabalho: Memória comunitária" in text
    assert "Prêmio de destaque científico" in text and "2024" in text
    fields = {f["path"]: f for f in report["fields"]}
    for source in cv.fields:
        if source.name in {"NOME-AGENCIA", "NOME-DA-ENTIDADE-PROMOTORA"}:
            assert fields[source.path]["reason"] == "presentation"
        if source.text == "FEP":
            assert fields[source.path]["status"] == "administrative"


@pytest.mark.parametrize(
    "change,expected",
    [
        ("no_metadata", "Bolsista: Fundação Exemplo de Pesquisa"),
        ("acronym_in_name", "Bolsista: Fundação Exemplo de Pesquisa (FEP), Brasil"),
        ("no_agency", "Bolsista"),
        ("no_scholarship", None),
    ],
)
def test_scholarship_handles_incomplete_data_and_existing_acronyms(
    fixtures, tmp_path, change, expected
):
    tree = ET.parse(fixtures / "personal-details.xml")
    degree = tree.find(".//MESTRADO")
    if change == "no_metadata":
        degree.set("CODIGO-AGENCIA-FINANCIADORA", "SEM-METADADOS")
    elif change == "acronym_in_name":
        degree.set("NOME-AGENCIA", "Fundação Exemplo de Pesquisa (FEP)")
    elif change == "no_agency":
        degree.set("NOME-AGENCIA", "")
    else:
        degree.set("FLAG-BOLSA", "NAO")
    source = tmp_path / "cv.xml"
    tree.write(source, encoding="utf-8")
    data, _ = export_data(read_lattes(source), Profile(include=["education"]))
    degree = data["cv"]["sections"]["Formação acadêmica/titulação"][0]
    assert degree.get("summary") == expected


@pytest.mark.parametrize(
    "date,place,language,expected",
    [
        (True, True, "pt", "Nascimento: 15/04/1990 — Cidade Exemplo/PR, Brasil"),
        (True, False, "pt", "Nascimento: 15/04/1990"),
        (False, True, "pt", "Naturalidade: Cidade Exemplo/PR, Brasil"),
        (True, True, "en", "Born: 1990-04-15 — Cidade Exemplo/PR, Brasil"),
        (False, True, "en", "Place of birth: Cidade Exemplo/PR, Brasil"),
    ],
)
def test_birth_is_opt_in_independent_and_only_appears_once_in_the_header(
    fixtures, date, place, language, expected
):
    cv = read_lattes(fixtures / "personal-details.xml")
    data, report = export_data(
        cv,
        Profile(
            include=["profile"],
            language=language,
            sections={"profile": {"show_birth_date": date, "show_birth_place": place}},
        ),
    )
    assert data["cv"]["custom_connections"] == [
        {
            "placeholder": expected,
            "fontawesome_icon": "calendar-days" if date else "location-dot",
            "url": None,
        }
    ]
    assert not data["cv"]["sections"]
    assert "PRIVAD" not in json.dumps(data)
    fields = {f["path"]: f for f in report["fields"]}
    for source in cv.fields:
        if "NASCIMENTO" in source.name:
            selected = date if source.name == "DATA-NASCIMENTO" else place
            assert source.disposition == "private"
            assert fields[source.path]["status"] == (
                "exported" if selected else "private"
            )
            if selected:
                assert fields[source.path]["reason"] == "explicit-selection"


@pytest.mark.parametrize(
    "overrides",
    [
        {"include": ["lattes.endereco"]},
        {"exclude": ["profile"]},
        {
            "hide_fields": [
                "date",
                "CIDADE-NASCIMENTO",
                "UF-NASCIMENTO",
                "PAIS-DE-NASCIMENTO",
            ]
        },
    ],
)
def test_birth_opt_in_respects_profile_selection_and_field_filters(fixtures, overrides):
    data, _ = export_data(
        read_lattes(fixtures / "personal-details.xml"),
        Profile(
            sections={"profile": {"show_birth_date": True, "show_birth_place": True}},
            **overrides,
        ),
    )
    assert "custom_connections" not in data["cv"]
    assert "1990" not in json.dumps(data) and "Cidade Exemplo" not in json.dumps(data)


def test_missing_and_invalid_birth_data_remain_usable(fixtures, tmp_path):
    profile = Profile(
        include=["profile"],
        sections={"profile": {"show_birth_date": True, "show_birth_place": True}},
    )
    empty, _ = export_data(read_lattes(fixtures / "minimal.xml"), profile)
    assert "custom_connections" not in empty["cv"]
    tree = ET.parse(fixtures / "personal-details.xml")
    person = tree.find("DADOS-GERAIS")
    person.set("DATA-NASCIMENTO", "31021990")
    person.set("CIDADE-NASCIMENTO", "")
    person.set("UF-NASCIMENTO", "")
    source = tmp_path / "cv.xml"
    tree.write(source, encoding="utf-8")
    data, report = export_data(read_lattes(source), profile)
    assert (
        data["cv"]["custom_connections"][0]["placeholder"]
        == "Nascimento: 31021990 — Brasil"
    )
    assert any(i["code"] == "invalid-date" for i in report["issues"])


def test_field_hiding_applies_to_scholarship_metadata_and_award_institution(fixtures):
    data, _ = export_data(
        read_lattes(fixtures / "personal-details.xml"),
        Profile(hide_fields=["SIGLA-INSTITUICAO", "NOME-DA-ENTIDADE-PROMOTORA"]),
    )
    assert data["cv"]["sections"]["Formação acadêmica/titulação"][0]["summary"] == (
        "Bolsista: Fundação Exemplo de Pesquisa, Brasil"
    )
    assert "summary" not in data["cv"]["sections"]["Prêmios e títulos"][0]


def test_full_keeps_existing_private_and_auxiliary_field_policy(fixtures):
    data, report = export_data(
        read_lattes(fixtures / "personal-details.xml"), Profile(full=True)
    )
    text = json.dumps(data, ensure_ascii=False)
    assert "custom_connections" not in data["cv"]
    assert "1990" not in text and "PRIVAD" not in text and "FEP" not in text
    assert (
        "Fundação Exemplo de Pesquisa" in text
        and "Associação Exemplo de Ciência" in text
    )
    assert not any(f.get("reason") == "presentation" for f in report["fields"])


def test_new_controls_are_discoverable_from_the_catalogue(capsys):
    assert main(["sections"]) == 0
    assert "lattes2pdf sections profile" in capsys.readouterr().out
    for name, options in [
        ("profile", ["show_birth_date", "show_birth_place"]),
        ("lattes.formacao", ["show_scholarship"]),
        ("lattes.premios", ["show_institution"]),
    ]:
        assert main(["sections", name]) == 0
        text = capsys.readouterr().out
        assert all(option in text for option in options)
