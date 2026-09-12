import json
from importlib.resources import files

import pytest
import yaml

from lattes2pdf.cli import PRESETS, main
from lattes2pdf.lattes import read_lattes
from lattes2pdf.models import catalog
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import load_profile, select


@pytest.mark.parametrize("preset", PRESETS)
def test_preset_stdout_is_a_standalone_editable_profile(preset, tmp_path, capsys):
    assert main(["profile", preset]) == 0
    captured = capsys.readouterr()
    assert not captured.err
    path = tmp_path / "profile.yaml"
    path.write_text(captured.out, encoding="utf-8")
    profile = load_profile(path)
    assert profile.include
    assert not profile.include_ids and not profile.exclude_ids
    assert not profile.header_links
    assert profile.since is None and profile.until is None and not profile.section_years
    assert all("title" not in options for options in profile.sections.values())
    assert "cv" not in yaml.safe_load(captured.out)


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize(
    "filename", ["academic.xml", "professional.xml", "minimal.xml"]
)
def test_presets_keep_bio_and_use_the_existing_selection_rules(
    preset, filename, fixtures, tmp_path
):
    path = tmp_path / "profile.yaml"
    assert main(["profile", preset, "-o", str(path)]) == 0
    profile = load_profile(path)
    cv = read_lattes(fixtures / filename)
    assert not cv.issues
    data, report = export_data(cv, profile)
    assert cv.raw_xml == (fixtures / filename).read_bytes()
    assert data["cv"]["name"] == cv.name
    selection = select(cv, profile)
    included = {entry.id for entry in selection.entries}
    assert {
        entry["id"] for entry in report["entries"] if entry["status"] == "selected"
    } == included
    assert all(
        entry["reason"] == "section"
        for entry in report["entries"]
        if entry["status"] == "excluded"
    )
    assert not report["counts"].get("unmapped") and not report["counts"].get("unknown")
    assert set(data["cv"]["sections"]) <= {
        section["pt"] for section in catalog()["sections"].values()
    }
    bio = next((f.text for f in cv.fields if f.name == "TEXTO-RESUMO-CV-RH"), None)
    if bio:
        if preset == "resumido":
            assert "Perfil" not in data["cv"]["sections"]
            assert bio not in json.dumps(data, ensure_ascii=False)
        else:
            assert data["cv"]["sections"]["Perfil"] == [bio]
        assert data["cv"]["email"].endswith("@example.org")
    else:
        assert "Perfil" not in data["cv"]["sections"]
    if filename == "professional.xml":
        assert "Produção artística e cultural" in data["cv"]["sections"]
        assert "Trabalhos técnicos" in data["cv"]["sections"]
        assert "Artigos publicados" not in data["cv"]["sections"]
    if filename == "academic.xml":
        article = data["cv"]["sections"]["Artigos publicados"][0]
        assert bool(article["authors"]) == (preset != "resumido")
        text = json.dumps(data, ensure_ascii=False)
        assert ("Título do trabalho" in text) == (preset == "academico")
        assert ("Orientação:" in text) == (preset == "academico")


def test_preset_copy_can_be_customized_with_bio_and_record_ids(fixtures, tmp_path):
    path = tmp_path / "meu.profile.yaml"
    assert main(["profile", "resumido", "-o", str(path)]) == 0
    config = yaml.safe_load(path.read_text())
    config["hide_fields"].remove("summary")
    config["hide_fields"].remove("authors")
    cv = read_lattes(fixtures / "academic.xml")
    degree = next(
        e for e in cv.entries if e.section == "education" and e.tag == "GRADUACAO"
    )
    config["exclude_ids"] = [degree.id]
    config["sections"]["education"]["title"] = "Minha formação"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    result = tmp_path / "cv.yaml"
    assert (
        main(
            [
                "export",
                str(fixtures / "academic.xml"),
                "--profile",
                str(path),
                "--language",
                "en",
                "--theme",
                "moderncv",
                "-o",
                str(result),
            ]
        )
        == 0
    )
    data = yaml.safe_load(result.read_text())
    assert data["cv"]["sections"]["Profile"][0].startswith(
        "Researcher in digital preservation"
    )
    assert data["cv"]["sections"]["Published articles"][0]["authors"]
    assert len(data["cv"]["sections"]["Minha formação"]) == 1
    assert data["design"]["theme"] == "moderncv"
    report = json.loads(result.with_suffix(".report.json").read_text())
    assert next(e for e in report["entries"] if e["id"] == degree.id)["reason"] == "id"
    # Editing the copy does not alter the distributed preset.
    fresh = tmp_path / "fresh.yaml"
    assert main(["profile", "resumido", "-o", str(fresh)]) == 0
    assert "summary" in load_profile(fresh).hide_fields


def test_profile_copy_refuses_overwrite_unless_requested(tmp_path, capsys):
    path = tmp_path / "profile.yaml"
    path.write_text("theme: moderncv\n", encoding="utf-8")
    assert main(["profile", "academico", "-o", str(path)]) == 2
    assert path.read_text() == "theme: moderncv\n"
    assert "--force" in capsys.readouterr().err
    assert main(["profile", "academico", "-o", str(path), "--force"]) == 0
    assert load_profile(path).section_option("education", "show_thesis")


def test_profile_copy_protects_the_distributed_preset_even_with_force(capsys):
    source = files("lattes2pdf").joinpath("presets", "academico.yaml")
    original = source.read_bytes()
    assert main(["profile", "academico", "-o", str(source), "--force"]) == 2
    assert "distintas" in capsys.readouterr().err
    assert source.read_bytes() == original


def test_unknown_preset_does_not_create_a_file(tmp_path, capsys):
    output = tmp_path / "profile.yaml"
    with pytest.raises(SystemExit) as exc:
        main(["profile", "../catalog", "-o", str(output)])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize("command", ["export", "render"])
def test_default_cli_uses_academic_preset_and_full_bypasses_it(
    command, fixtures, tmp_path, monkeypatch
):
    # PDF compilation is covered separately; compare the content passed to it.
    monkeypatch.setattr("lattes2pdf.cli.render_pdf", lambda *a, **kw: b"PDF")
    monkeypatch.setattr("lattes2pdf.cli.rendercv_version", lambda: "2.8")
    source = str(fixtures / "academic.xml")
    preset = tmp_path / "academic.profile.yaml"
    assert main(["profile", "academico", "-o", str(preset)]) == 0
    outputs = {}
    for name, options in {
        "default": [],
        "explicit": ["--profile", str(preset)],
        "full": ["--full"],
    }.items():
        path = tmp_path / (name + (".pdf" if command == "render" else ".yaml"))
        assert main([command, source, "-o", str(path), *options]) == 0
        outputs[name] = yaml.safe_load(path.with_suffix(".yaml").read_text())
    assert outputs["default"] == outputs["explicit"]
    assert "Orientação:" in json.dumps(outputs["default"], ensure_ascii=False)
    full, _ = export_data(read_lattes(source), load_profile(None, {"full": True}))
    assert outputs["full"] == full
    assert outputs["full"] != outputs["default"]


def test_explicit_profile_does_not_inherit_default_and_cli_overrides_it(
    fixtures, tmp_path
):
    profile = tmp_path / "profile.yaml"
    profile.write_text("include: [education]\n")
    output = tmp_path / "cv.yaml"
    assert (
        main(
            [
                "export",
                str(fixtures / "academic.xml"),
                "--profile",
                str(profile),
                "--theme",
                "moderncv",
                "-o",
                str(output),
            ]
        )
        == 0
    )
    data = yaml.safe_load(output.read_text())
    assert list(data["cv"]["sections"]) == ["Formação acadêmica/titulação"]
    assert "Orientação:" not in json.dumps(data, ensure_ascii=False)
    assert data["design"]["theme"] == "moderncv"
