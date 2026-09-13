import json
import xml.etree.ElementTree as ET
from importlib.resources import files

import pytest

from lattes2pdf.cli import inspection, main
from lattes2pdf.lattes import read_lattes
from lattes2pdf.models import CVError
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import Profile, load_profile, select

FULL = "Trabalhos completos publicados em eventos"
ABSTRACTS = "Resumos publicados em eventos"


@pytest.mark.parametrize(
    "selector", ["lattes.anais", "publications.conference", "publications"]
)
def test_conference_sections_keep_ids_and_group_expanded_abstracts(fixtures, selector):
    cv = read_lattes(fixtures / "presentation.xml")
    original_ids = [e.id for e in cv.entries]
    profile = Profile(include=[selector], hide_fields=["details"])
    data, report = export_data(cv, profile)
    sections = data["cv"]["sections"]
    assert list(sections) == [FULL, ABSTRACTS]
    assert [e["title"] for e in sections[FULL]] == ["Catálogos comunitários"]
    assert [e["title"] for e in sections[ABSTRACTS]] == [
        "Memória compartilhada",
        "Fontes orais abertas",
    ]
    assert [e.id for e in cv.entries] == original_ids
    selected = [e for e in report["entries"] if e["status"] == "selected"]
    assert len(selected) == 3 and all(
        e["id"].startswith("publications.conference:") for e in selected
    )
    assert len(inspection(cv, ["publications.conference.abstracts"])["entries"]) == 2


def test_conference_subgroups_support_filters_titles_and_id_exclusions(fixtures):
    cv = read_lattes(fixtures / "presentation.xml")
    abstract = next(e for e in cv.entries if e.title() == "Memória compartilhada")
    profile = Profile(
        include=["lattes.anais"],
        exclude=["publications.conference.full"],
        exclude_ids=[abstract.id],
        hide_fields=["details"],
        sections={"publications.conference.abstracts": {"title": "Meus resumos"}},
    )
    data, _ = export_data(cv, profile)
    assert list(data["cv"]["sections"]) == ["Meus resumos"]
    assert data["cv"]["sections"]["Meus resumos"][0]["title"] == "Fontes orais abertas"
    profile = Profile(
        include=["publications.conference.abstracts"],
        section_years={"publications.conference.abstracts": {"since": 2024}},
    )
    assert [e.id for e in select(cv, profile).entries] == [abstract.id]
    with pytest.raises(CVError, match="Título de seção repetido"):
        export_data(
            cv,
            Profile(
                include=["lattes.anais"],
                sections={"publications.conference.full": {"title": ABSTRACTS}},
            ),
        )


def test_conference_missing_nature_is_kept_without_guessing(fixtures, tmp_path):
    tree = ET.parse(fixtures / "presentation.xml")
    tree.find(".//DADOS-BASICOS-DO-TRABALHO").set("NATUREZA", "")
    path = tmp_path / "cv.xml"
    tree.write(path, encoding="utf-8")
    cv = read_lattes(path)
    data, _ = export_data(
        cv, Profile(include=["lattes.anais"], hide_fields=["details"])
    )
    assert FULL not in data["cv"]["sections"]
    assert (
        data["cv"]["sections"]["Trabalhos em eventos"][0]["title"]
        == "Catálogos comunitários"
    )
    data, _ = export_data(cv, Profile(full=True))
    assert (
        FULL not in data["cv"]["sections"] and ABSTRACTS not in data["cv"]["sections"]
    )


@pytest.mark.parametrize(
    "selector", ["lattes.patentes", "lattes.inovacao", "technical.software"]
)
def test_registration_details_follow_the_record_without_duplicates(fixtures, selector):
    cv = read_lattes(fixtures / "presentation.xml")
    data, report = export_data(cv, Profile(include=[selector], hide_fields=["details"]))
    entry = next(iter(data["cv"]["sections"].values()))[0]
    assert entry["summary"].splitlines() == [
        "Instituição de registro: Instituto Fictício de Registros",
        "Número do registro: REG-FICTICIO-001",
        "Data de depósito: 31/12/2023",
        "Data da concessão: 29/02/2024",
    ]
    fields = {f["path"]: f for f in report["fields"]}
    for source in cv.fields:
        if source.tag == "REGISTRO-OU-PATENTE":
            assert fields[source.path]["status"] == "exported"
    data, _ = export_data(cv, Profile(include=["lattes.patentes", "lattes.inovacao"]))
    assert json.dumps(data).count("REG-FICTICIO-001") == 1


@pytest.mark.parametrize(
    "option,value",
    [
        ("show_registration_institution", "Instituto Fictício de Registros"),
        ("show_registration_number", "REG-FICTICIO-001"),
        ("show_deposit_date", "31/12/2023"),
        ("show_grant_date", "29/02/2024"),
    ],
)
def test_each_registration_detail_can_be_hidden_even_with_generic_details_enabled(
    fixtures, option, value
):
    cv = read_lattes(fixtures / "presentation.xml")
    data, report = export_data(
        cv,
        Profile(
            include=["lattes.inovacao"], sections={"lattes.patentes": {option: False}}
        ),
    )
    entry = next(iter(data["cv"]["sections"].values()))[0]
    assert len(entry["summary"].splitlines()) == 3
    assert value not in json.dumps(entry, ensure_ascii=False)
    assert any(f.get("reason") == "presentation" for f in report["fields"])


def test_registration_missing_invalid_and_hidden_fields_remain_distinct(
    fixtures, tmp_path
):
    tree = ET.parse(fixtures / "presentation.xml")
    record = tree.find(".//REGISTRO-OU-PATENTE")
    record.set("DATA-DE-CONCESSAO", "31022024")
    record.set("DATA-PEDIDO-DE-DEPOSITO", "")
    path = tmp_path / "cv.xml"
    tree.write(path, encoding="utf-8")
    cv = read_lattes(path)
    data, report = export_data(
        cv,
        Profile(
            include=["technical.software"],
            hide_fields=["CODIGO-DO-REGISTRO-OU-PATENTE"],
        ),
    )
    text = json.dumps(data, ensure_ascii=False)
    assert "Data da concessão: 31022024" in text
    assert "Data de depósito" not in text and "REG-FICTICIO-001" not in text
    assert any(i["code"] == "invalid-date" for i in report["issues"])


def test_project_description_and_event_type_defaults_can_be_overridden(fixtures):
    cv = read_lattes(fixtures / "presentation.xml")
    profile = load_profile(files("lattes2pdf").joinpath("presets", "completo.yaml"))
    data, _ = export_data(cv, profile)
    assert "description" in data["cv"]["sections"]["Projetos"][0]
    assert "Exposição; Outras Formas" not in json.dumps(data, ensure_ascii=False)
    profile.sections["research.projects"]["show_description"] = False
    profile.sections["events"]["show_event_type"] = True
    data, _ = export_data(cv, profile)
    assert "description" not in data["cv"]["sections"]["Projetos"][0]
    assert "Exposição; Outras Formas" in json.dumps(data, ensure_ascii=False)


def test_external_design_without_description_placeholder_keeps_project_text(fixtures):
    cv = read_lattes(fixtures / "presentation.xml")
    data, _ = export_data(
        cv,
        Profile(
            include=["research.projects"],
            sections={"research.projects": {"show_description": True}},
        ),
        design={"theme": "classic"},
    )
    entry = data["cv"]["sections"]["Projetos"][0]
    assert "description" not in entry and "Pesquisa fictícia" in entry["summary"]


def test_subgroup_and_registration_controls_are_discoverable(capsys):
    assert main(["sections", "lattes.anais"]) == 0
    text = capsys.readouterr().out
    assert (
        "publications.conference.full" in text
        and "publications.conference.abstracts" in text
    )
    assert main(["sections", "lattes.patentes"]) == 0
    text = capsys.readouterr().out
    assert "show_registration_number" in text and "show_deposit_date" in text
