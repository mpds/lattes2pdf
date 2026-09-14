"""Behavior/security contracts of the browser's supported surface."""

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import browser_adapter as adapter

from lattes2pdf.models import CVError
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import load_profile

FIXTURES = Path(__file__).resolve().parents[2] / "tests/fixtures"


@pytest.fixture(autouse=True)
def document_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "DOCUMENT", tmp_path)
    monkeypatch.setattr(adapter, "_document", None)
    monkeypatch.setattr(adapter, "_archive_bytes", None)


@pytest.fixture
def settings():
    return dict(
        model="resumido",
        basis="resumido",
        categories=[],
        theme="classic",
        bibliography="abnt",
        informed=True,
        etAl=False,
        professional=None,
        production=None,
        language="pt",
    )


def test_simple_profile_round_trip_and_cli_parity(settings, tmp_path):
    settings.update(
        model="personalizado",
        categories=["lattes.formacao", "lattes.artigos"],
        theme="opal",
        bibliography="chicago",
        informed=False,
        etAl=True,
        professional=2020,
        production=2024,
    )
    saved = adapter.export_profile(settings)
    restored = json.loads(adapter.import_profile(saved.encode()))
    assert restored["model"] == "personalizado"
    for field in (
        "categories",
        "theme",
        "bibliography",
        "informed",
        "etAl",
        "professional",
        "production",
    ):
        assert restored[field] == settings[field]
    path = tmp_path / "reusable.yaml"
    path.write_text(saved)
    adapter.load_document((FIXTURES / "academic.xml").read_bytes())
    browser = json.loads(adapter.prepare(settings))
    native, report = export_data(adapter._document, load_profile(path))
    assert yaml.safe_load(browser["yaml"]) == native
    assert {k: v for k, v in browser["report"].items() if k != "renderer"} == report


def test_moderncv_exports_explicit_browser_font_and_preserves_profile(settings):
    settings["theme"] = "moderncv"
    adapter.load_document((FIXTURES / "academic.xml").read_bytes())
    result = json.loads(adapter.prepare(settings))
    data = yaml.safe_load(result["yaml"])
    assert data["design"]["typography"]["font_family"] == "XCharter"
    assert "XCharter" in result["typst"]
    assert "Fontin" not in result["typst"]
    restored = json.loads(
        adapter.import_profile(adapter.export_profile(settings).encode())
    )
    assert json.loads(adapter.prepare(restored))["yaml"] == result["yaml"]


@pytest.mark.parametrize("preset", adapter.PRESETS)
def test_unmodified_builtin_profiles_reimport(preset):
    raw = adapter.files("lattes2pdf").joinpath("presets", preset + ".yaml").read_bytes()
    result = json.loads(adapter.import_profile(raw))
    assert result["model"] == preset


@pytest.mark.parametrize(
    "extra",
    [
        {"full": True},
        {"include_ids": ["private-marker"]},
        {"until": 2025},
        {"order": ["education"]},
        {"theme": "../theme.yaml"},
        {"periods": {"production": {"until": 2025}}},
        {"sections": {"education": {"show_advisors": False}}},
        {"authors": {"name_case": "upper"}},
    ],
)
def test_advanced_profiles_are_never_silently_simplified(settings, extra):
    profile = yaml.safe_load(adapter.export_profile(settings))
    profile.update(extra)
    with pytest.raises(CVError):
        adapter.import_profile(yaml.safe_dump(profile).encode())


@pytest.mark.parametrize(
    "raw",
    [
        b"include: &a [profile]\nexclude: *a",
        b"theme: classic\ntheme: opal",
        b"!!python/object/apply:os.system [false]",
        b"a: [" * 20 + b"]" * 20,
        b"#" * 65537,
    ],
)
def test_unsafe_or_unbounded_profiles_rejected(raw):
    with pytest.raises(CVError):
        adapter.import_profile(raw)


def test_empty_categories_cannot_become_complete_cv(settings):
    settings["model"] = "personalizado"
    with pytest.raises(CVError, match="ao menos uma"):
        adapter.export_profile(settings)


def test_custom_selection_uses_the_core_canonical_order(settings):
    settings.update(
        model="personalizado",
        categories=["lattes.premios", "lattes.formacao"],
    )
    profile = adapter._profile(settings)
    assert profile.include == [
        "profile",
        "lattes.formacao",
        "lattes.premios",
    ]
    catalogue = json.loads(adapter.catalog_data())
    keys = [category["key"] for category in catalogue["categories"]]
    assert keys.index("lattes.formacao") < keys.index("lattes.premios")


def test_address_and_other_information_are_independent(settings):
    adapter.load_document((FIXTURES / "native-categories.xml").read_bytes())
    settings.update(model="personalizado", categories=["lattes.formacao"])
    without = yaml.safe_load(json.loads(adapter.prepare(settings))["yaml"])["cv"][
        "sections"
    ]
    assert "Endereço" not in without and "Outras informações relevantes" not in without
    settings["categories"] = ["lattes.endereco", "lattes.outras-informacoes"]
    with_categories = yaml.safe_load(json.loads(adapter.prepare(settings))["yaml"])[
        "cv"
    ]["sections"]
    assert (
        "Endereço" in with_categories
        and "Outras informações relevantes" in with_categories
    )
    assert "Formação acadêmica/titulação" not in with_categories


def test_periods_remove_only_the_active_bound(settings):
    settings.update(professional=2020, production=2024)
    data = yaml.safe_load(adapter.export_profile(settings))
    assert data["periods"] == {
        "professional": {"since": 2020},
        "production": {"since": 2024},
    }
    settings["professional"] = None
    data = yaml.safe_load(adapter.export_profile(settings))
    assert data["periods"] == {"professional": {}, "production": {"since": 2024}}


def archive(entries):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as output:
        for name, content in entries:
            output.writestr(name, content)
    return data.getvalue()


def test_xml_zip_member_choice_and_latin1_match(settings):
    raw = (FIXTURES / "latin1.xml").read_bytes()
    adapter.load_document(raw)
    expected = json.loads(adapter.prepare(settings))["yaml"]
    zipped = archive(
        [
            ("folder/cv.xml", raw),
            ("second.xml", (FIXTURES / "academic.xml").read_bytes()),
        ]
    )
    assert json.loads(adapter.load_document(zipped)) == {
        "members": ["folder/cv.xml", "second.xml"]
    }
    assert adapter._document is None
    adapter.choose_member("folder/cv.xml")
    assert json.loads(adapter.prepare(settings))["yaml"] == expected


@pytest.mark.parametrize(
    "raw",
    [
        b'<!DOCTYPE CURRICULO-VITAE [<!ENTITY x "a">]><CURRICULO-VITAE/>',
        b"<CURRICULO-VITAE>",
        b"<x>" * 130 + b"</x>" * 130,
        archive([("../cv.xml", b"<x/>")]),
        archive([("cv.xml", b"<x/>"), ("cv.xml", b"<x/>")]),
        archive([("cv.xml", b" " * (adapter.MAX_BYTES + 1))]),
    ],
)
def test_invalid_input_discards_previous_document(raw, settings):
    adapter.load_document((FIXTURES / "academic.xml").read_bytes())
    with pytest.raises(CVError):
        adapter.load_document(raw)
    with pytest.raises(CVError, match="Selecione um currículo"):
        adapter.prepare(settings)
