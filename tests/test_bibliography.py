import json
import xml.etree.ElementTree as ET

import pytest
import yaml

from lattes2pdf.cli import main
from lattes2pdf.lattes import read_lattes
from lattes2pdf.models import CVError
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import Profile, load_profile

EXPECTED = {
    "abnt": {
        "Artigos publicados": "SILVA, M. Extremos de chuva. Revista Exemplo de Clima, v. 8, n. 2, p. 10-18, 2024.",
        "Livros": "SILVA, M. Clima e sociedade. 2 ed. São Paulo: Editora Exemplo, 2023, 180 p.",
        "Capítulos de livros": "SILVA, M. Adaptação urbana. In: Cidades e clima. 2 ed. São Paulo: Editora Exemplo, 2024, p. 20-30.",
        "Trabalhos completos publicados em eventos": "SILVA, M. Cenários de precipitação. In: Simpósio Exemplo, 2024, Recife. Anais de Clima. São Paulo: Editora Exemplo, 2025, p. 40-45.",
        "Textos em jornais e revistas": "SILVA, M. O calor nas cidades. Jornal Exemplo, p. 7, Data de publicação: 01/03/2024, 2024.",
        "Software": "SILVA, M. ClimaAberto. 2025. #linebreak() Finalidade: Calcular índices de extremos climáticos.",
        "Trabalhos técnicos": "SILVA, M. Risco de inundação. Recife, 2024. #linebreak() Finalidade: Planejamento da adaptação.",
        "Produção artística e cultural": "SILVA, M. Mapas do amanhã. Museu Exemplo, 2024.",
    },
    "chicago": {
        "Artigos publicados": "SILVA, M. 2024. Extremos de chuva. In Revista Exemplo de Clima, v. 8, n. 2, p. 10-18.",
        "Livros": "SILVA, M. 2023. Clima e sociedade. 2 ed. São Paulo: Editora Exemplo, 180 p.",
        "Capítulos de livros": "SILVA, M. 2024. Adaptação urbana. In Cidades e clima. 2 ed. 20-30. São Paulo: Editora Exemplo.",
        "Trabalhos completos publicados em eventos": "SILVA, M. 2025. Cenários de precipitação. In Anais de Clima. Simpósio Exemplo, 2024, Recife. São Paulo: Editora Exemplo, p. 40-45.",
        "Textos em jornais e revistas": "SILVA, M. 2024. O calor nas cidades. In Jornal Exemplo, p. 7, Data de publicação: 01/03/2024.",
        "Software": "SILVA, M. 2025. ClimaAberto. #linebreak() Finalidade: Calcular índices de extremos climáticos.",
        "Trabalhos técnicos": "SILVA, M. 2024. Risco de inundação. Recife. #linebreak() Finalidade: Planejamento da adaptação.",
        "Produção artística e cultural": "SILVA, M. 2024. Mapas do amanhã. Museu Exemplo.",
    },
}


@pytest.mark.parametrize("style", EXPECTED)
def test_reference_composition_by_production_type(fixtures, style):
    source = fixtures / "reference-styles.xml"
    cv = read_lattes(source)
    data, report = export_data(
        cv,
        Profile(
            bibliography_style=style,
            authors={"highlight_self": False},
            hide_fields=["NATUREZA"],
            sections={"publications.articles": {"show_details": True}},
        ),
    )
    assert {k: v[0] for k, v in data["cv"]["sections"].items()} == EXPECTED[style]
    assert cv.raw_xml == source.read_bytes()
    assert not report["issues"] and not report["counts"].get("unmapped")


@pytest.mark.parametrize("style", EXPECTED)
@pytest.mark.parametrize("fixture", ["bibliography.xml", "technical.xml", "other.xml"])
def test_other_production_types_keep_available_content_without_duplicate_details(
    fixtures, style, fixture
):
    cv = read_lattes(fixtures / fixture)
    data, report = export_data(cv, Profile(bibliography_style=style))
    for entry in cv.entries:
        if (
            entry.section.startswith(("publications.", "technical."))
            or entry.section == "artistic"
        ):
            assert any(
                e["id"] == entry.id and e["status"] == "selected"
                for e in report["entries"]
            )
    assert not report["counts"].get("unmapped")
    assert "None" not in json.dumps(data)
    if fixture == "bibliography.xml":
        assert "Aceito para publicação" in data["cv"]["sections"]["Artigos aceitos"][0]
        assert "2022" not in data["cv"]["sections"]["Artigos aceitos"][0]
        assert (
            "Titulo do livro:" not in data["cv"]["sections"]["Capítulos de livros"][0]
        )


@pytest.mark.parametrize("style", EXPECTED)
def test_reference_controls_never_reintroduce_hidden_fields(fixtures, style):
    cv = read_lattes(fixtures / "reference-styles.xml")
    data, report = export_data(
        cv,
        Profile(
            bibliography_style=style,
            hide_fields=[
                "authors",
                "date",
                "TITULO-DO-LIVRO",
                "NOME-DA-EDITORA",
                "PAGINA-FINAL",
            ],
            sections={"publications.articles": {"show_details": True}},
        ),
    )
    text = json.dumps(data["cv"]["sections"], ensure_ascii=False)
    for hidden in [
        "SILVA, M.",
        "2024",
        "2023",
        "Editora Exemplo",
        "Cidades e clima",
        "10-18",
    ]:
        assert hidden not in text
    assert "Adaptação urbana" in text and "p. 10" in text
    assert all(
        f["status"] == "excluded"
        for f in report["fields"]
        if f["path"].endswith("/@NOME-DA-EDITORA")
    )
    concise, _ = export_data(
        cv, Profile(bibliography_style=style, hide_fields=["details"])
    )
    assert "v. 8" not in concise["cv"]["sections"]["Artigos publicados"][0]
    assert "Finalidade:" not in concise["cv"]["sections"]["Software"][0]


@pytest.mark.parametrize("style", EXPECTED)
def test_author_toggles_and_missing_metadata_are_independent_of_style(
    fixtures, tmp_path, style
):
    cv = read_lattes(fixtures / "author-controls.xml")
    data, _ = export_data(
        cv, Profile(bibliography_style=style, authors={"et_al": True})
    )
    ref = data["cv"]["sections"]["Artigos publicados"][0]
    assert ref.startswith("COSTA, H. et al.") and "et al.." not in ref
    assert "SOUZA" not in ref
    fullnames, _ = export_data(
        cv,
        Profile(
            bibliography_style=style,
            authors={"et_al": True, "use_informed_citation": False},
        ),
    )
    assert fullnames["cv"]["sections"]["Artigos publicados"][0].startswith(
        "Helena Costa et al."
    )
    tree = ET.parse(fixtures / "reference-styles.xml")
    article = tree.find(".//ARTIGO-PUBLICADO")
    article.remove(article.find("AUTORES"))
    basic = article.find("DADOS-BASICOS-DO-ARTIGO")
    basic.set("ANO-DO-ARTIGO", "")
    article.remove(article.find("DETALHAMENTO-DO-ARTIGO"))
    path = tmp_path / "cv.xml"
    tree.write(path, encoding="utf-8")
    missing, _ = export_data(
        read_lattes(path), Profile(bibliography_style=style, include=["lattes.artigos"])
    )
    assert missing["cv"]["sections"]["Artigos publicados"] == ["Extremos de chuva."]


@pytest.mark.parametrize("style", EXPECTED)
def test_registration_controls_and_overlapping_categories(fixtures, style):
    cv = read_lattes(fixtures / "presentation.xml")
    data, report = export_data(
        cv,
        Profile(
            bibliography_style=style,
            include=["lattes.patentes", "lattes.inovacao"],
            sections={
                "lattes.patentes": {
                    "show_registration_number": False,
                    "show_deposit_date": True,
                }
            },
        ),
    )
    refs = [v for section in data["cv"]["sections"].values() for v in section]
    assert len(refs) == 1
    assert "REG-FICTICIO-001" not in refs[0]
    assert "Data de depósito: 31/12/2023" in refs[0]
    assert sum(e["status"] == "selected" for e in report["entries"]) == 1


def test_cli_style_overrides_preset_without_changing_theme(fixtures, tmp_path):
    source = fixtures / "reference-styles.xml"
    for style in ("abnt", "chicago"):
        output = tmp_path / f"{style}.yaml"
        assert (
            main(
                [
                    "export",
                    str(source),
                    "--theme",
                    "moderncv",
                    "--bibliography-style",
                    style,
                    "-o",
                    str(output),
                ]
            )
            == 0
        )
        data = yaml.safe_load(output.read_text())
        assert data["design"]["theme"] == "moderncv"
        ref = data["cv"]["sections"]["Artigos publicados"][0]
        assert (ref.index("2024") < ref.index("Extremos de chuva")) == (
            style == "chicago"
        )
    output = tmp_path / "default.yaml"
    assert main(["export", str(source), "-o", str(output)]) == 0
    assert yaml.safe_load(output.read_text())["cv"]["sections"]["Artigos publicados"][
        0
    ].endswith("2024.")


@pytest.mark.parametrize("value", ["apa", False, {}, []])
def test_invalid_style_fails_before_output(tmp_path, value):
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump({"bibliography_style": value}))
    with pytest.raises(CVError, match="bibliography_style"):
        load_profile(path)


def test_full_remains_independent_and_theme_presentation_is_available(fixtures):
    cv = read_lattes(fixtures / "reference-styles.xml")
    for profile in (Profile(), Profile(bibliography_style=None), Profile(full=True)):
        data, _ = export_data(cv, profile)
        assert isinstance(data["cv"]["sections"]["Artigos publicados"][0], dict)
    with pytest.raises(CVError, match="--full"):
        export_data(cv, Profile(full=True, bibliography_style="abnt"))
