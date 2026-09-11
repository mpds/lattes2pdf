import io
import json
import re
import shutil
import subprocess
import sys

import pytest
import yaml
from pypdf import PdfReader

from cv_lattex.backend import render_pdf
from cv_lattex.cli import main
from cv_lattex.lattes import read_lattes
from cv_lattex.models import CVError
from cv_lattex.rendering import export_data
from cv_lattex.selection import Profile, load_profile
from cv_lattex.theme import load_theme


def text_of(pdf):
    return re.sub(
        r"\s+",
        " ",
        " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages),
    )


@pytest.mark.parametrize(
    "fixture,full",
    [("academic.xml", True), ("professional.xml", False), ("context.xml", False)],
)
def test_bundled_theme_keeps_selected_content_and_packages_assets(
    fixtures, tmp_path, fixture, full
):
    cv = read_lattes(fixtures / fixture)
    normal, _ = export_data(cv, Profile(full=full))
    styled, _ = export_data(cv, Profile(theme="garamond", full=full))
    assert styled["cv"] == normal["cv"]
    output = tmp_path / "cv.pdf"
    args = ["render", str(fixtures / fixture), "--theme", "garamond", "-o", str(output)]
    assert main(args + (["--full"] if full else [])) == 0
    report = json.loads(output.with_suffix(".report.json").read_text())
    assert report["renderer"]["theme"] == "garamond"
    assert report["renderer"]["base_theme"] == "classic"
    assert (tmp_path / "classic/entries/PublicationEntry.j2.typ").is_file()
    assert (tmp_path / "fonts/OFL.txt").is_file()
    text = text_of(output.read_bytes())
    assert cv.name in text
    if full:
        assert "“Catálogos abertos & memória digital”" in text
        # PDF extraction can insert spaces inside kerning pairs in EB Garamond.
        assert "Volume:12" in text.replace(" ", "")
        assert "Clara Exemplo Fictícia" in text
    # The same theme assets can be reused by another CV without --force.
    assert (
        main(
            [
                "export",
                str(fixtures / fixture),
                "--theme",
                "garamond",
                "-o",
                str(tmp_path / "outro.yaml"),
            ]
        )
        == 0
    )


@pytest.mark.parametrize("base", ["classic", "terceiro"])
def test_external_theme_profile_relative_path_and_standalone_render(
    fixtures, tmp_path, monkeypatch, base
):
    source = tmp_path / "tema externo"
    assert main(["theme", "garamond", "-o", str(source)]) == 0
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
    (source / base / "Header.j2.typ").write_text(
        "{% include 'typst/Header.j2.typ' %}\n#text[Modelo editorial fictício]\n"
    )
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
        "garamond",
        "-o",
        str(output),
    ]

    def fail(*args, **kwargs):
        raise CVError("Compilation failed")

    monkeypatch.setattr("cv_lattex.cli.render_pdf", fail)
    assert main(args) == 2
    assert main(args + ["--force"]) == 2
    assert custom.read_text() == "user customization"
    assert sorted(tmp_path.rglob("*")) == [folder, custom]


def test_theme_inputs_and_symlink_destinations_are_protected(fixtures, tmp_path):
    source = tmp_path / "source"
    assert main(["theme", "garamond", "-o", str(source)]) == 0
    assert main(["theme", "garamond", "-o", str(source)]) == 2
    config = source / "design.yaml"
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
                "garamond",
                "-o",
                str(target / "cv.yaml"),
                "--force",
            ]
        )
        == 2
    )
    assert list(target.iterdir()) == [target / "classic"]


def test_stale_overrides_cannot_change_standalone_output_silently(fixtures, tmp_path):
    args = ["export", str(fixtures / "minimal.xml"), "-o", str(tmp_path / "cv.yaml")]
    assert main(args + ["--theme", "garamond"]) == 0
    original = (tmp_path / "cv.yaml").read_bytes()
    assert main(args + ["--theme", "classic", "--force"]) == 2
    assert (tmp_path / "cv.yaml").read_bytes() == original


@pytest.mark.parametrize("language", ["pt", "en"])
def test_garamond_dates_symbols_and_author_abbreviation(fixtures, language):
    theme = load_theme("garamond")
    document, _ = export_data(
        read_lattes(fixtures / "academic.xml"),
        Profile(theme="garamond", language=language),
    )
    prefix, month = ("Início", "Out") if language == "pt" else ("Start", "Oct")
    document["cv"]["sections"] = {
        "Experience": [
            {
                "company": '#text("ÁRVORE \\u{26} AÇÃO")',
                "position": "Research",
                "date": f"{prefix}: 2024-10",
                "location": "Cidade",
            },
            {"company": "TESTE", "position": "Research", "date": f"{prefix}: 2024-13"},
            {
                "company": "TESTE",
                "position": "Research",
                "start_date": "2020-01",
                "end_date": "present",
            },
        ],
        "Publications": [
            {
                "title": f"Reference {n}",
                "authors": ["**Silva, Ana**", "Costa, Lia", "Lima, Rui", "Sousa, João"][
                    :n
                ],
                "journal": '#text("JOURNAL \\u{26} CIÊNCIA \\u{5b}A\\u{5d}")',
                "date": 2024,
            }
            for n in (0, 1, 3, 4)
        ],
    }
    pdf = render_pdf(yaml.safe_dump(document, allow_unicode=True), assets=theme.assets)
    text = text_of(pdf)
    assert "Árvore & Ação" in text and "Journal & Ciência [A]" in text
    assert f"{month} 2024" in text and f"{prefix}: 2024-13" in text
    assert "Silva, Ana, Costa, Lia, Lima, Rui." in text
    assert "Silva, Ana et al." in text and text.count("et al.") == 1
    fonts = {
        str(f.get_object()["/BaseFont"])
        for p in PdfReader(io.BytesIO(pdf)).pages
        for f in p["/Resources"]["/Font"].values()
    }
    assert any("SemiBold" in f for f in fonts) and any("Italic" in f for f in fonts)


def test_garamond_preserves_long_entries(fixtures):
    theme = load_theme("garamond")
    document, _ = export_data(
        read_lattes(fixtures / "academic.xml"), Profile(theme="garamond")
    )
    document["cv"]["sections"] = {
        "Projects": [
            {
                "name": "Memória cultural",
                "summary": "Início do relato. "
                + "Documentação do acervo. " * 450
                + "Fim do relato.",
            }
        ]
    }
    pdf = render_pdf(yaml.safe_dump(document, allow_unicode=True), assets=theme.assets)
    assert len(PdfReader(io.BytesIO(pdf)).pages) >= 2
    text = text_of(pdf)
    assert text.count("Documentação do acervo.") == 450
    assert "Fim do relato." in text
