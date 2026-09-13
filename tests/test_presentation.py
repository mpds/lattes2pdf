import json
from importlib.resources import files

from lattes2pdf.lattes import read_lattes
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import Profile, load_profile


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
