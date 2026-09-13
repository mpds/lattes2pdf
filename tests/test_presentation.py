import json
import xml.etree.ElementTree as ET
from importlib.resources import files

import pytest

from lattes2pdf.cli import inspection
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
