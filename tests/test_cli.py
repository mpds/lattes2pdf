import json
import os

import pytest
import yaml

from lattes2pdf.cli import main
from lattes2pdf.lattes import read_lattes


@pytest.mark.parametrize("command", ["export", "render"])
def test_list_and_repeated_options_keep_selection_and_profile_precedence(
    fixtures, tmp_path, capsys, command
):
    source = fixtures / "presentation.xml"
    cv = read_lattes(source)
    education = next(e.id for e in cv.entries if e.section == "education")
    training = next(e.id for e in cv.entries if e.section == "training")
    software = next(e.id for e in cv.entries if e.section == "technical.software")
    paper = next(e.id for e in cv.entries if e.title() == "Catálogos comunitários")
    abstract = next(e.id for e in cv.entries if e.title() == "Memória compartilhada")
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        yaml.safe_dump(
            {
                "include": ["events"],
                "exclude": ["education"],
                "include_ids": [software],
                "exclude_ids": [paper],
                "order": ["education", "publications"],
                "hide_fields": ["date"],
                "sections": {"education": {"show_thesis": True}},
            }
        )
    )
    options = {
        "--include": ["lattes.formacao", "lattes.anais", "lattes.patentes"],
        "--exclude": ["training", "publications.conference.abstracts"],
        "--include-id": [education, training, software, paper, abstract],
        "--exclude-id": [software, training],
        "--order": ["publications", "education", "profile"],
        "--hide-field": ["thesis", "authors", "details"],
    }
    results = []
    for syntax in ("repeated", "list", "mixed"):
        output = tmp_path / (syntax + (".pdf" if command == "render" else ".yaml"))
        args = [command, str(source), "--profile", str(profile), "-o", str(output)]
        for option, values in options.items():
            if syntax == "repeated":
                args.extend(item for value in values for item in (option, value))
            elif syntax == "list":
                args.extend([option, *values])
            else:
                args.extend([option, *values[:-1], option, values[-1]])
        assert main(args) == 0
        capsys.readouterr()
        results.append(
            (
                yaml.safe_load(output.with_suffix(".yaml").read_text()),
                json.loads(output.with_suffix(".report.json").read_text()),
            )
        )
    assert results[0] == results[1] == results[2]
    data, report = results[0]
    assert list(data["cv"]["sections"]) == [
        "Trabalhos completos publicados em eventos",
        "Formação acadêmica/titulação",
    ]
    assert {e["id"] for e in report["entries"] if e["status"] == "selected"} == {
        education,
        paper,
    }
    assert data["cv"]["sections"]["Formação acadêmica/titulação"][0]["end_date"] == 2023
    assert "Título:" not in json.dumps(data, ensure_ascii=False)
    paper_entry = data["cv"]["sections"]["Trabalhos completos publicados em eventos"][0]
    assert "Ana Exemplo Fictícia" not in json.dumps(paper_entry, ensure_ascii=False)


def test_inspect_combines_section_lists_and_repetitions(fixtures, capsys):
    source = str(fixtures / "presentation.xml")
    results = []
    for filters in (
        [
            "--section",
            "education",
            "--section",
            "training",
            "--section",
            "publications.conference.full",
        ],
        ["--section", "education", "training", "publications.conference.full"],
        [
            "--section",
            "education",
            "training",
            "--section",
            "publications.conference.full",
        ],
    ):
        assert main(["inspect", source, *filters, "--json"]) == 0
        results.append(json.loads(capsys.readouterr().out))
    assert results[0] == results[1] == results[2]
    assert results[0]["sections"] == {
        "education": 1,
        "training": 1,
        "publications.conference": 1,
    }


@pytest.mark.parametrize(
    "option",
    [
        "--include",
        "--exclude",
        "--include-id",
        "--exclude-id",
        "--order",
        "--hide-field",
        "--section",
    ],
)
def test_list_options_require_a_value_before_the_next_option(
    fixtures, tmp_path, capsys, option
):
    if option == "--section":
        args = ["inspect", str(fixtures / "minimal.xml"), option, "--json"]
    else:
        args = [
            "export",
            str(fixtures / "minimal.xml"),
            option,
            "-o",
            str(tmp_path / "cv.yaml"),
        ]
    assert main(args) == 2
    assert "[invalid-arguments]" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


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
    assert "ERROR    lattes2pdf [invalid-input]" in capsys.readouterr().err
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
