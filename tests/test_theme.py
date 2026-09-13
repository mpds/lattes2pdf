import io
import json
import re
import shutil
import subprocess
import sys

import pytest
import yaml
from pypdf import PdfReader

from lattes2pdf.cli import main
from lattes2pdf.lattes import read_lattes
from lattes2pdf.models import CVError
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import Profile, load_profile
from lattes2pdf.theme import THEMES, load_theme


def text_of(pdf):
    return re.sub(
        r"\s+",
        " ",
        " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages),
    )


@pytest.fixture
def external_design(tmp_path):
    source = tmp_path / "tema externo"
    assert main(["theme", "classic", "-o", str(source)]) == 0
    (source / "classic").mkdir()
    (source / "classic/Header.j2.typ").write_text(
        "{% include 'typst/Header.j2.typ' %}\n#text[Modelo editorial fictício]\n"
    )
    (source / "fonts").mkdir()
    (source / "fonts/NOTICE.txt").write_text("Arquivo auxiliar fictício para fontes.\n")
    return source / "design.yaml"


def test_every_rendercv_theme_is_available_and_can_create_a_design(tmp_path):
    from rendercv.schema.models.design.built_in_design import available_themes

    assert set(THEMES) == set(available_themes)
    for name in available_themes:
        target = tmp_path / name
        assert main(["theme", name, "-o", str(target)]) == 0
        copied = load_theme(str(target / "design.yaml"))
        assert copied.design == load_theme(name).design
        assert list(target.iterdir()) == [target / "design.yaml"]


@pytest.mark.parametrize(
    "fixture,full",
    [("academic.xml", True), ("professional.xml", False), ("context.xml", False)],
)
def test_external_theme_keeps_selected_content_and_packages_assets(
    fixtures, tmp_path, fixture, full, external_design
):
    cv = read_lattes(fixtures / fixture)
    normal, _ = export_data(cv, Profile(full=full))
    styled, _ = export_data(cv, Profile(theme=str(external_design), full=full))
    assert styled["cv"] == normal["cv"]
    output = tmp_path / "cv.pdf"
    args = [
        "render",
        str(fixtures / fixture),
        "--theme",
        str(external_design),
        "-o",
        str(output),
    ]
    assert main(args + (["--full"] if full else [])) == 0
    report = json.loads(output.with_suffix(".report.json").read_text())
    assert report["renderer"]["theme"] == str(external_design)
    assert report["renderer"]["base_theme"] == "classic"
    assert (tmp_path / "classic/Header.j2.typ").read_bytes() == (
        external_design.parent / "classic/Header.j2.typ"
    ).read_bytes()
    assert (tmp_path / "fonts/NOTICE.txt").read_bytes() == (
        external_design.parent / "fonts/NOTICE.txt"
    ).read_bytes()
    text = text_of(output.read_bytes())
    assert cv.name in text
    assert "Modelo editorial fictício" in text
    if full:
        assert "Catálogos abertos & memória digital" in text
        # PDF extraction can insert spaces inside kerning pairs.
        assert "Volume:12" in text.replace(" ", "")
        assert "Clara Exemplo Fictícia" in text
    # The same theme assets can be reused by another CV without --force.
    assert (
        main(
            [
                "export",
                str(fixtures / fixture),
                "--theme",
                str(external_design),
                "-o",
                str(tmp_path / "outro.yaml"),
            ]
        )
        == 0
    )


@pytest.mark.parametrize("base", ["classic", "terceiro"])
def test_external_theme_profile_relative_path_and_standalone_render(
    fixtures, tmp_path, monkeypatch, base, external_design
):
    source = external_design.parent
    (source / "notas-pessoais.xml").write_text("do not copy neighboring files")
    config = source / "design.yaml"
    design = yaml.safe_load(config.read_text())
    design["design"]["page"]["left_margin"] = "3cm"
    if base != "classic":
        (source / "classic").rename(source / base)
        design["design"]["theme"] = base
        (source / base / "__init__.py").write_text(
            "from typing import Literal\n"
            "from rendercv.schema.models.design.classic_theme import ClassicTheme\n"
            "class TerceiroTheme(ClassicTheme):\n"
            "    theme: Literal['terceiro'] = 'terceiro'\n"
        )
    config.write_text(yaml.safe_dump(design))
    profile = tmp_path / "perfil.yaml"
    profile.write_text(
        'theme: "tema externo/design.yaml"\ninclude: [education, publications.articles]\n'
    )
    out = tmp_path / "resultado"
    out.mkdir()
    monkeypatch.chdir(out)
    assert load_profile(profile).theme == str(config)
    assert load_profile(profile, {"theme": "classic"}).theme == "classic"
    output = out / "cv.pdf"
    assert (
        main(
            [
                "render",
                str(fixtures / "academic.xml"),
                "--profile",
                str(profile),
                "-o",
                str(output),
            ]
        )
        == 0
    )
    text = text_of(output.read_bytes())
    assert "Modelo editorial fictício" in text
    assert not (out / "notas-pessoais.xml").exists()
    assert (
        yaml.safe_load(output.with_suffix(".yaml").read_text())["design"]["page"][
            "left_margin"
        ]
        == "3cm"
    )
    shutil.rmtree(source)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "rendercv",
            "render",
            str(output.with_suffix(".yaml")),
            "--pdf-path",
            "recompilado.pdf",
            "--dont-generate-markdown",
            "--dont-generate-html",
            "--dont-generate-png",
        ],
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout.decode() + result.stderr.decode()
    assert text_of((out / "recompilado.pdf").read_bytes()) == text


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        "design: []",
        "cv: {}\ndesign: {theme: classic}",
        "design: {theme: ../escape}",
        "design: {theme: classic, theme: ink}",
        "design: &x {theme: classic, other: *x}",
    ],
)
def test_invalid_external_design_does_not_write(fixtures, tmp_path, raw):
    design = tmp_path / "design.yaml"
    design.write_text(raw)
    assert (
        main(
            [
                "export",
                str(fixtures / "minimal.xml"),
                "--theme",
                str(design),
                "-o",
                str(tmp_path / "cv.yaml"),
            ]
        )
        == 2
    )
    assert list(tmp_path.iterdir()) == [design]


def test_asset_collision_and_compile_failure_preserve_outputs(
    fixtures, tmp_path, monkeypatch
):
    folder = tmp_path / "classic"
    folder.mkdir()
    custom = folder / "Preamble.j2.typ"
    custom.write_text("user customization")
    output = tmp_path / "cv.pdf"
    args = [
        "render",
        str(fixtures / "minimal.xml"),
        "--theme",
        "classic",
        "-o",
        str(output),
    ]

    def fail(*args, **kwargs):
        raise CVError("Compilation failed")

    monkeypatch.setattr("lattes2pdf.cli.render_pdf", fail)
    assert main(args) == 2
    assert main(args + ["--force"]) == 2
    assert custom.read_text() == "user customization"
    assert sorted(tmp_path.rglob("*")) == [folder, custom]


def test_theme_inputs_and_symlink_destinations_are_protected(
    fixtures, tmp_path, external_design
):
    source = external_design.parent
    assert main(["theme", "classic", "-o", str(source)]) == 2
    config = external_design
    original = config.read_bytes()
    assert (
        main(
            [
                "export",
                str(fixtures / "minimal.xml"),
                "--theme",
                str(config),
                "-o",
                str(config),
                "--force",
            ]
        )
        == 2
    )
    assert config.read_bytes() == original
    target = tmp_path / "out"
    target.mkdir()
    (target / "classic").symlink_to(source / "classic", target_is_directory=True)
    assert (
        main(
            [
                "export",
                str(fixtures / "minimal.xml"),
                "--theme",
                str(config),
                "-o",
                str(target / "cv.yaml"),
                "--force",
            ]
        )
        == 2
    )
    assert list(target.iterdir()) == [target / "classic"]


def test_stale_overrides_cannot_change_standalone_output_silently(
    fixtures, tmp_path, external_design
):
    args = ["export", str(fixtures / "minimal.xml"), "-o", str(tmp_path / "cv.yaml")]
    assert main(args + ["--theme", str(external_design)]) == 0
    original = (tmp_path / "cv.yaml").read_bytes()
    assert main(args + ["--theme", "classic", "--force"]) == 2
    assert (tmp_path / "cv.yaml").read_bytes() == original
