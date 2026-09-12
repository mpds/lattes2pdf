import json
import os

import pytest
import yaml

from lattes2pdf.cli import main


def test_inspect_ids_can_drive_export(fixtures, tmp_path, capsys):
    source = str(fixtures / "bibliography.xml")
    assert main(["inspect", source, "--json"]) == 0
    inventory = json.loads(capsys.readouterr().out)
    article = next(
        e for e in inventory["entries"] if e["section"] == "publications.articles"
    )
    output = tmp_path / "cv.yaml"
    assert (
        main(
            [
                "export",
                source,
                "-o",
                str(output),
                "--include-id",
                article["id"],
                "--theme",
                "moderncv",
            ]
        )
        == 0
    )
    data = yaml.safe_load(output.read_text())
    report = json.loads(output.with_suffix(".report.json").read_text())
    assert list(data["cv"]["sections"]) == ["Artigos publicados"]
    assert data["design"]["theme"] == "moderncv"
    assert report["counts"]["exported"] > 0


@pytest.mark.parametrize(
    "collision", ["input", "hardlink", "profile", "report", "existing"]
)
def test_output_collisions_are_rejected_before_writing(
    fixtures, tmp_path, capsys, collision
):
    source = tmp_path / "input.xml"
    original = (fixtures / "minimal.xml").read_bytes()
    source.write_bytes(original)
    profile = tmp_path / "profile.yaml"
    profile.write_text("theme: classic\n")
    output = tmp_path / "cv.yaml"
    report = tmp_path / "report.json"
    args = ["export", str(source), "--profile", str(profile)]
    if collision == "input":
        output = source
    elif collision == "hardlink":
        os.link(source, output)
    elif collision == "profile":
        output = profile
    elif collision == "report":
        report = output
    else:
        report.write_text("existing")
    if collision != "existing":
        args.append("--force")
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}
    assert main(args + ["-o", str(output), "--report", str(report)]) == 2
    assert "Erro:" in capsys.readouterr().err
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_full_failure_leaves_no_outputs_and_force_replaces_only_outputs(
    fixtures, tmp_path
):
    output = tmp_path / "cv.yaml"
    args = ["export", str(fixtures / "extensions.xml"), "-o", str(output), "--full"]
    assert main(args) == 2
    assert not list(tmp_path.iterdir())
    assert main(args + ["--allow-unmapped"]) == 0
    output.write_text("old")
    assert main(args + ["--allow-unmapped", "--force"]) == 0
    assert yaml.safe_load(output.read_text())["cv"]["name"] == "Ana Exemplo Fictícia"


def test_invalid_profile_and_bad_input_return_errors_without_tracebacks(
    fixtures, tmp_path, capsys
):
    profile = tmp_path / "profile.yaml"
    profile.write_text("includes: [education]")
    assert (
        main(
            [
                "export",
                str(fixtures / "minimal.xml"),
                "--profile",
                str(profile),
                "-o",
                str(tmp_path / "cv.yaml"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "cv.yaml").exists()
    assert main(["inspect", str(fixtures / "malformed.xml")]) == 2
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
