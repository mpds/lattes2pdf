import copy
import json
import logging
import subprocess
import xml.etree.ElementTree as ET

import pytest
import yaml

from lattes2pdf.cli import inspection, main
from lattes2pdf.lattes import read_lattes


@pytest.fixture
def diagnostic_source(fixtures, tmp_path):
    tree = ET.parse(fixtures / "presentation.xml")
    tree.find("DADOS-GERAIS").set("CAMPO-FICTICIO-PERFIL", "perfil")
    tree.find(".//MESTRADO").set("ANO-DE-CONCLUSAO", "20xx")
    project = tree.find(".//PARTICIPACAO-EM-PROJETO")
    project.find("PROJETO-DE-PESQUISA").set("CAMPO-FICTICIO-PROJETO", "projeto")
    another = copy.deepcopy(project)
    another.find("PROJETO-DE-PESQUISA").set("NOME-DO-PROJETO", "Outro projeto fictício")
    tree.find(".//ATIVIDADES-DE-PARTICIPACAO-EM-PROJETO").append(another)
    ET.SubElement(tree.getroot(), "BLOCO-FICTICIO-GLOBAL")
    path = tmp_path / "diagnostics.xml"
    tree.write(path, encoding="utf-8")
    return path


def test_inspection_scopes_nested_diagnostics_and_keeps_global_issues(
    diagnostic_source,
):
    cv = read_lattes(diagnostic_source)
    complete = inspection(cv)
    education = inspection(cv, ["lattes.formacao"])
    assert {i["code"] for i in education["issues"]} == {
        "invalid-year",
        "unknown-element",
    }
    assert all("PROJETO" not in i["path"] for i in education["issues"])
    profile = inspection(cv, ["profile"])
    assert {i["code"] for i in profile["issues"]} == {
        "unknown-field",
        "unknown-element",
    }
    assert all(
        "MESTRADO" not in i["path"] and "PROJETO" not in i["path"]
        for i in profile["issues"]
    )
    combined = inspection(cv, ["lattes.formacao", "lattes.projetos"])
    assert any("CAMPO-FICTICIO-PROJETO" in i["path"] for i in combined["issues"])
    assert all("CAMPO-FICTICIO-PERFIL" not in i["path"] for i in combined["issues"])
    assert {e["id"] for e in education["entries"]} <= {
        e["id"] for e in complete["entries"]
    }
    duplicates = [i for i in complete["issues"] if i["code"] == "duplicate-identity"]
    assert len(duplicates) == 2 and all(i["level"] == "DEBUG" for i in duplicates)


@pytest.mark.parametrize("level", ["ERROR", "DEBUG"])
def test_json_is_clean_and_log_level_does_not_erase_diagnostics(
    diagnostic_source, capsys, level
):
    assert (
        main(["inspect", str(diagnostic_source), "--json", "--log-level", level]) == 0
    )
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert captured.err == ""
    assert any(i["level"] == "DEBUG" for i in result["issues"])
    assert any(i["level"] == "WARNING" for i in result["issues"])


def test_inspect_groups_warnings_and_limits_paths_to_debug(diagnostic_source, capsys):
    args = ["inspect", str(diagnostic_source), "--section", "lattes.projetos"]
    assert main(args) == 0
    captured = capsys.readouterr()
    assert "Projetos" in captured.out
    assert captured.err.count("[unknown-field]") == 1
    assert "2 ocorrências" in captured.err
    assert "duplicate-identity" not in captured.err
    assert "/CURRICULO-VITAE" not in captured.err and "invalid-year" not in captured.err
    assert main(args + ["--log-level", "DEBUG"]) == 0
    debug = capsys.readouterr()
    assert debug.out == captured.out
    assert "/CURRICULO-VITAE" in debug.err
    assert "CAMPO-FICTICIO-PROJETO" in debug.err
    assert "CAMPO-FICTICIO-PERFIL" not in debug.err


@pytest.mark.parametrize("before", [False, True])
def test_level_works_before_or_after_subcommand_and_restores_logging(
    fixtures, tmp_path, capsys, before
):
    root = logging.getLogger()
    app = logging.getLogger("lattes2pdf")
    original = (root.level, root.handlers[:], app.level, app.handlers[:], app.propagate)
    args = ["profile", "resumido", "-o", str(tmp_path / "profile.yaml")]
    level = ["--log-level", "error"]
    assert main(level + args if before else args + level) == 0
    assert capsys.readouterr() == ("", "")
    assert main(["profile", "ampliado", "-o", str(tmp_path / "another.yaml")]) == 0
    captured = capsys.readouterr()
    assert (
        captured.out == ""
        and captured.err.count("INFO     lattes2pdf [output-written]") == 1
    )
    assert (
        root.level,
        root.handlers,
        app.level,
        app.handlers,
        app.propagate,
    ) == original


@pytest.mark.parametrize("command", ["export", "theme", "profile"])
def test_file_confirmations_use_stderr(fixtures, tmp_path, capsys, command):
    args = {
        "export": [str(fixtures / "minimal.xml"), "-o", str(tmp_path / "cv.yaml")],
        "theme": ["classic", "-o", str(tmp_path / "theme")],
        "profile": ["completo", "-o", str(tmp_path / "profile.yaml")],
    }[command]
    assert main([command, *args]) == 0
    captured = capsys.readouterr()
    assert captured.out == "" and "INFO     lattes2pdf [output-written]" in captured.err
    assert main(["profile", "resumido"]) == 0
    captured = capsys.readouterr()
    assert yaml.safe_load(captured.out)["include"]
    assert captured.err == ""


def test_export_keeps_all_issues_in_report_even_when_console_is_filtered(
    diagnostic_source, tmp_path, capsys
):
    output = tmp_path / "cv.yaml"
    args = [
        "export",
        str(diagnostic_source),
        "--include",
        "lattes.formacao",
        "-o",
        str(output),
    ]
    assert main(args) == 0
    captured = capsys.readouterr()
    assert "[invalid-year]" in captured.err and "duplicate-identity" not in captured.err
    assert "activities.projects" not in captured.err
    report = json.loads(output.with_suffix(".report.json").read_text())
    assert any(
        i["code"] == "duplicate-identity" and i["level"] == "DEBUG"
        for i in report["issues"]
    )
    assert main(args + ["--force", "--log-level", "ERROR"]) == 0
    assert capsys.readouterr() == ("", "")
    assert json.loads(output.with_suffix(".report.json").read_text()) == report


@pytest.mark.parametrize(
    "args",
    [
        ["inspect"],
        ["inspect", "--bogus"],
        ["--log-level", "TRACE", "inspect", "cv.zip"],
    ],
)
def test_argument_errors_follow_log_format(args, capsys):
    assert main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("ERROR    lattes2pdf [invalid-arguments]")
    assert "--help" in captured.err and "Traceback" not in captured.err


def test_missing_input_has_actionable_error_and_nonzero_exit(tmp_path, capsys):
    assert main(["inspect", str(tmp_path / "missing.zip"), "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "[input-not-found]" in captured.err
    assert "Confira o caminho" in captured.err and "Traceback" not in captured.err


@pytest.mark.parametrize(
    "args", [["--log-level", "DEBUG", "inspect"], ["inspect", "--log-level", "DEBUG"]]
)
def test_debug_level_applies_to_argument_errors(args, capsys):
    assert main(args) == 2
    captured = capsys.readouterr()
    assert "ERROR    lattes2pdf [invalid-arguments]" in captured.err
    assert "DEBUG    lattes2pdf [invalid-arguments]" in captured.err
    assert "usage:" in captured.err


def test_renderer_details_and_traceback_are_only_shown_in_debug(
    fixtures, tmp_path, capsys, monkeypatch
):
    def failed(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 1, b"", b"FICTITIOUS RENDERER DETAILS"
        )

    monkeypatch.setattr("lattes2pdf.backend.subprocess.run", failed)
    args = ["render", str(fixtures / "minimal.xml"), "-o", str(tmp_path / "cv.pdf")]
    assert main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "[renderer-failed]" in captured.err
    assert "FICTITIOUS" not in captured.err and "Traceback" not in captured.err
    assert not (tmp_path / "cv.pdf").exists()
    assert main(args + ["--log-level", "DEBUG"]) == 2
    debug = capsys.readouterr()
    assert "FICTITIOUS RENDERER DETAILS" in debug.err and "Traceback" in debug.err


def test_unexpected_cli_error_is_brief_and_debuggable(capsys, monkeypatch):
    def failed(*args, **kwargs):
        raise RuntimeError("FICTITIOUS INTERNAL FAILURE")

    monkeypatch.setattr("lattes2pdf.cli.read_lattes", failed)
    assert main(["inspect", "cv.xml"]) == 1
    captured = capsys.readouterr()
    assert "[internal-error]" in captured.err and "FICTITIOUS" not in captured.err
    assert main(["inspect", "cv.xml", "--log-level", "DEBUG"]) == 1
    assert "FICTITIOUS INTERNAL FAILURE" in capsys.readouterr().err
