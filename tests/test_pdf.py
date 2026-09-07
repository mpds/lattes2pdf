import io
import json
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from importlib.metadata import PackageNotFoundError

import pytest
import yaml
from pypdf import PdfReader

from cv_lattex.backend import render_pdf, rendercv_version
from cv_lattex.cli import main
from cv_lattex.lattes import read_lattes
from cv_lattex.models import CVError
from cv_lattex.rendering import export_data
from cv_lattex.selection import THEMES, Profile


def pdf_text(data: bytes) -> str:
    return re.sub(
        r"\s+",
        " ",
        " ".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages),
    )


@pytest.mark.parametrize("theme", THEMES)
def test_themes_render_content_dates_and_links(fixtures, tmp_path, theme):
    output = tmp_path / "currículo final.pdf"
    assert (
        main(
            [
                "render",
                str(fixtures / "academic.xml"),
                "-o",
                str(output),
                "--theme",
                theme,
                "--full",
            ]
        )
        == 0
    )
    data = output.read_bytes()
    text = pdf_text(data)
    for expected in [
        "Ana Exemplo Fictícia",
        "Ciência da Informação",
        "AcervoLivre",
        "Catálogos abertos & memória digital",
        "Bruno Exemplo Fictício",
        "Volume: 12",
        "2024",
        "Graduação",
        "Mestrado",
    ]:
        # PDF kerning can become a spurious space during text extraction.
        assert expected.replace(" ", "") in text.replace(" ", "")
    assert "Jan 2024" not in text and "Jan 2021" not in text
    assert "Rua Privada" not in text
    assert "#text" not in text and "\\u{" not in text
    reader = PdfReader(io.BytesIO(data))
    links = [
        annotation.get_object().get("/A", {}).get("/URI", "")
        for page in reader.pages
        for annotation in page.get("/Annots", [])
    ]
    assert any("10.0000/example.memory" in link for link in links)
    assert round(float(reader.pages[0].mediabox.width)) == 595
    report = json.loads(output.with_suffix(".report.json").read_text(encoding="utf-8"))
    assert report["renderer"]["theme"] == theme
    document = yaml.safe_load(output.with_suffix(".yaml").read_text(encoding="utf-8"))
    assert document["cv"]["sections"]["Artigos publicados"][0]["date"] == 2024


def test_zip_profiles_and_hidden_fields_reach_the_pdf(fixtures, tmp_path):
    source = tmp_path / "cv.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.write(fixtures / "academic.xml", "export/cv.xml")
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "include: [education, publications]\norder: [publications, education]\nlanguage: en\nhide_fields: [authors, details]\n",
        encoding="utf-8",
    )
    output = tmp_path / "cv.pdf"
    assert (
        main(["render", str(source), "-o", str(output), "--profile", str(profile)]) == 0
    )
    text = pdf_text(output.read_bytes())
    assert "Open catalogs & digital memory" in text
    assert text.index("Published articles") < text.index("Education")
    assert "Bruno Exemplo" not in text
    assert "AcervoLivre" not in text
    assert "Volume" not in text


def test_multiline_details_remain_text_and_long_entries_span_pages(fixtures, tmp_path):
    tree = ET.parse(fixtures / "academic.xml")
    description = tree.find(".//DETALHAMENTO-DO-SOFTWARE")
    description.set(
        "FINALIDADE",
        "Início do relato.\n\n"
        + "Documentação do acervo e preservação da memória. " * 450
        + "Fim do relato.",
    )
    path = tmp_path / "long.xml"
    tree.write(path, encoding="utf-8")
    data, _ = export_data(read_lattes(path), Profile(include=["technical.software"]))
    result = render_pdf(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    reader = PdfReader(io.BytesIO(result))
    assert len(reader.pages) >= 3
    text = pdf_text(result)
    assert "Início do relato." in text and "Fim do relato." in text
    assert text.count("Documentação do acervo") == 450
    assert "#text" not in text


def test_literal_symbols_survive_compilation(fixtures):
    cv = read_lattes(fixtures / "latin1.xml")
    data, _ = export_data(cv, Profile(full=True))
    text = pdf_text(
        render_pdf(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    )
    assert 'Formação, extensão e ação. Texto literal: "exemplo"' in text
    assert "_ % # { } \\ $ [ ]" in text


def test_render_failure_keeps_existing_outputs(fixtures, tmp_path, monkeypatch, capsys):
    output = tmp_path / "cv.pdf"
    for path in [
        output,
        output.with_suffix(".yaml"),
        output.with_suffix(".report.json"),
    ]:
        path.write_bytes(b"existing")

    def fail(*args, **kwargs):
        raise CVError("Falha de compilação")

    monkeypatch.setattr("cv_lattex.cli.render_pdf", fail)
    assert (
        main(["render", str(fixtures / "academic.xml"), "-o", str(output), "--force"])
        == 2
    )
    assert "Falha de compilação" in capsys.readouterr().err
    assert all(path.read_bytes() == b"existing" for path in tmp_path.iterdir())


def test_sidecar_collision_is_detected_before_compiling(
    fixtures, tmp_path, monkeypatch
):
    profile = tmp_path / "cv.yaml"
    profile.write_text("theme: classic\n", encoding="utf-8")

    def unexpected(*args, **kwargs):
        pytest.fail("Compilation must not run with an output collision")

    monkeypatch.setattr("cv_lattex.cli.render_pdf", unexpected)
    assert (
        main(
            [
                "render",
                str(fixtures / "academic.xml"),
                "-o",
                str(tmp_path / "cv.pdf"),
                "--profile",
                str(profile),
                "--force",
            ]
        )
        == 2
    )
    assert list(tmp_path.iterdir()) == [profile]


@pytest.mark.parametrize(
    "failure", ["timeout", "validation", "network", "missing-output"]
)
def test_backend_failures_are_actionable_and_temporary_files_are_removed(
    monkeypatch, failure
):
    directories = []

    def run(command, **kwargs):
        directories.append(kwargs["cwd"])
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        message = (
            b"failed to download package" if failure == "network" else b"invalid input"
        )
        return subprocess.CompletedProcess(
            command, 0 if failure == "missing-output" else 1, b"", message
        )

    monkeypatch.setattr("cv_lattex.backend.subprocess.run", run)
    with pytest.raises(
        CVError,
        match={"timeout": "--timeout", "network": "packages.typst.org"}.get(
            failure, "invalid input"
        ),
    ):
        render_pdf("cv: {name: Exemplo}")
    assert all(not path.exists() for path in directories)


def test_missing_or_unsupported_backend_has_an_install_hint(monkeypatch):
    def missing(_):
        raise PackageNotFoundError("rendercv")

    monkeypatch.setattr("cv_lattex.backend.version", missing)
    with pytest.raises(CVError, match="pip install"):
        rendercv_version()
    monkeypatch.setattr("cv_lattex.backend.version", lambda _: "3.0")
    with pytest.raises(CVError, match="não é suportado"):
        rendercv_version()
