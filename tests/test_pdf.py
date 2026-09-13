import io
import json
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from importlib.metadata import PackageNotFoundError
from importlib.resources import files

import pytest
import yaml
from pypdf import PdfReader

from lattes2pdf.backend import render_pdf, rendercv_version
from lattes2pdf.cli import PRESETS, main
from lattes2pdf.lattes import read_lattes
from lattes2pdf.models import CVError
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import THEMES, Profile, load_profile


def pdf_text(data: bytes) -> str:
    return re.sub(
        r"\s+",
        " ",
        " ".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages),
    )


@pytest.mark.parametrize("theme", THEMES)
def test_presentation_order_descriptions_and_registrations_reach_each_theme(
    fixtures, theme
):
    profile = load_profile(files("lattes2pdf").joinpath("presets", "completo.yaml"))
    profile.theme = theme
    data, _ = export_data(read_lattes(fixtures / "presentation.xml"), profile)
    pdf = render_pdf(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    # Some native fonts map visible hyphens to U+00AD in PDF text extraction.
    text = pdf_text(pdf).replace("\u00ad", "-").replace(" ", "")
    for first, second in (
        ("Mestrado em Arquivologia", "Universidade Fictícia"),
        ("Curso de curta duração em Preservação digital", "Escola Fictícia de Acervos"),
        ("Pesquisadora", "Instituto Fictício de Memória"),
        ("Trabalhos completos publicados em eventos", "Resumos publicados em eventos"),
    ):
        assert text.index(first.replace(" ", "")) < text.index(second.replace(" ", ""))
    for expected in (
        "Título: Memória comunitária",
        "Descrição: Pesquisa fictícia",
        "documentos [públicos] & relatos locais",
        "Instituição de registro: Instituto Fictício de Registros",
        "Número do registro: REG-FICTICIO-001",
        "Data de depósito: 31/12/2023",
        "Data da concessão: 29/02/2024",
    ):
        assert text.count(expected.replace(" ", "")) == 1
    for omitted in ("Título do trabalho", "Exposição; Outras Formas", "#text", "\\u{"):
        assert omitted.replace(" ", "") not in text


@pytest.mark.parametrize("theme", THEMES)
def test_birth_scholarship_and_award_context_reach_each_theme(
    fixtures, tmp_path, theme
):
    tree = ET.parse(fixtures / "personal-details.xml")
    tree.find("DADOS-GERAIS").set("CIDADE-NASCIMENTO", "Cidade Exemplo [Norte] & Sul")
    source = tmp_path / "cv.xml"
    tree.write(source, encoding="utf-8")
    data, _ = export_data(
        read_lattes(source),
        Profile(
            theme=theme,
            hide_fields=["details", "summary"],
            sections={"profile": {"show_birth_date": True, "show_birth_place": True}},
        ),
    )
    pdf = render_pdf(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    text = pdf_text(pdf).replace(" ", "")
    for expected in (
        "Nascimento: 15/04/1990 — Cidade Exemplo [Norte] & Sul/PR, Brasil",
        "Bolsista: Fundação Exemplo de Pesquisa, FEP, Brasil",
        "Prêmio de destaque científico",
        "Associação Exemplo de Ciência",
    ):
        assert expected.replace(" ", "") in text
    assert "PRIVAD" not in text and "#text" not in text and "\\u{" not in text
    assert text.count("15/04/1990") == 1


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


def test_education_presentation_and_profile_options_reach_the_pdf(fixtures, tmp_path):
    profile = tmp_path / "formacao.yaml"
    profile.write_text(
        "include: [education]\nsections:\n  education:\n    show_thesis: true\n    show_advisors: true\n    title: Minha formação\n",
        encoding="utf-8",
    )
    output = tmp_path / "education.pdf"
    assert (
        main(
            [
                "render",
                str(fixtures / "education.xml"),
                "--profile",
                str(profile),
                "-o",
                str(output),
            ]
        )
        == 0
    )
    text = pdf_text(output.read_bytes()).replace(" ", "")
    for expected in [
        "Minha formação",
        "Título: Preservação de acervos comunitários",
        "Coorientação: Bruno Exemplo",
        "Incompleto",
        "Início: 2013",
    ]:
        assert expected.replace(" ", "") in text
    for omitted in [
        "ID-FICTICIO",
        "AGENCIA-FICTICIA",
        "Flag",
        "Palavra chave",
        "Concluído",
        "Em andamento",
    ]:
        assert omitted.replace(" ", "") not in text


@pytest.mark.parametrize("theme", THEMES)
def test_articles_with_missing_authors_keep_dates_journals_and_links(fixtures, theme):
    cv = read_lattes(fixtures / "articles.xml")
    data, _ = export_data(
        cv,
        Profile(
            theme=theme, sections={"publications.articles": {"show_details": True}}
        ),
    )
    result = render_pdf(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    text = pdf_text(result).replace(" ", "")
    for expected in (
        "Catálogos abertos e memória comunitária",
        "Clara Exemplo Fictícia",
        "Organização de coleções sem autoria informada",
        "Cadernos Fictícios de Documentação",
        "Inventário de fontes orais",
        "v. 12",
        "p. 10-19",
        "p. e204",
        "2025",
        "2022",
    ):
        assert expected.replace(" ", "") in text
    for omitted in ("Nota cadastral", "Natureza", "0000-0000", "presente", "et al."):
        assert omitted.replace(" ", "") not in text
    assert "AnaExemploFictícia,BrunoExemploFictício,ClaraExemploFictícia" in text
    bold, regular = [], []
    for page in PdfReader(io.BytesIO(result)).pages:
        page.extract_text(
            visitor_text=lambda text, cm, tm, font, size: (
                bold
                if font and "bold" in str(font.get("/BaseFont")).lower()
                else regular
            ).append(text)
        )
    # Count author highlights after the first title, independent of header styling.
    article_bold = (
        "".join(bold)
        .replace(" ", "")
        .split("Catálogosabertosememóriacomunitária", 1)[1]
    )
    assert article_bold.count("AnaExemploFictícia") == 2
    assert "BrunoExemploFictício," in "".join(regular).replace(" ", "")
    links = [
        annotation.get_object().get("/A", {}).get("/URI", "")
        for page in PdfReader(io.BytesIO(result)).pages
        for annotation in page.get("/Annots", [])
    ]
    assert any("10.0000/example.collections" in link for link in links)
    assert any("example.org/preservacao" in link for link in links)


def test_article_profile_hides_authors_and_links_in_pdf(fixtures, tmp_path):
    profile = tmp_path / "articles.profile.yaml"
    profile.write_text(
        "include: [publications.articles]\nsections:\n  publications.articles:\n    show_authors: false\n    show_links: false\n",
        encoding="utf-8",
    )
    output = tmp_path / "articles.pdf"
    assert (
        main(
            [
                "render",
                str(fixtures / "articles.xml"),
                "--profile",
                str(profile),
                "-o",
                str(output),
            ]
        )
        == 0
    )
    text = pdf_text(output.read_bytes())
    assert "Catálogos abertos" in text and "Revista Fictícia de Memória" in text
    assert "Clara Exemplo" not in text and "Bruno Exemplo" not in text
    assert "10.0000" not in text
    assert all(not page.get("/Annots") for page in PdfReader(output).pages)


@pytest.mark.parametrize("hide_authors", [False, True])
def test_chapter_book_title_survives_compilation_without_details(
    fixtures, tmp_path, hide_authors
):
    tree = ET.parse(fixtures / "bibliography.xml")
    book_title = "Livro fictício de memória & acervos"
    tree.find(".//DETALHAMENTO-DO-CAPITULO").set("TITULO-DO-LIVRO", book_title)
    source = tmp_path / "chapter.xml"
    tree.write(source, encoding="utf-8")
    hide_fields = ["details", "authors"] if hide_authors else ["details"]
    data, _ = export_data(
        read_lattes(source),
        Profile(include=["publications.chapters"], hide_fields=hide_fields),
    )
    result = render_pdf(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    text = pdf_text(result).replace(" ", "")
    assert text.count(book_title.replace(" ", "")) == 1
    assert "Trabalhofictício:do-capitulo" in text
    assert "2022" in text
    assert "#text" not in text and "\\u{" not in text


@pytest.mark.parametrize("name_case", ["original", "upper", "title"])
def test_author_case_and_self_identity_reach_the_pdf(fixtures, name_case):
    data, _ = export_data(
        read_lattes(fixtures / "authors.xml"), Profile(authors={"name_case": name_case})
    )
    result = render_pdf(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    text = pdf_text(result).replace(" ", "").replace("’", "'")
    byline = {
        "original": "BRUNO d'ÁVILA, SILVA, ANA, Clara de Souza",
        "upper": "BRUNO D'ÁVILA, SILVA, ANA, CLARA DE SOUZA",
        "title": "Bruno D'Ávila, Silva, Ana, Clara De Souza",
    }[name_case]
    assert byline.replace(" ", "") in text
    assert "#text" not in text and "**" not in text


def test_exported_author_list_can_be_edited_directly(fixtures):
    data, _ = export_data(
        read_lattes(fixtures / "authors.xml"),
        Profile(include=["publications.articles"], authors={"highlight_self": False}),
    )
    document = yaml.safe_load(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    article = document["cv"]["sections"]["Artigos publicados"][0]
    article["authors"][1] = "Ana da Silva"
    article["authors"].append("Diego Exemplo")
    result = render_pdf(yaml.safe_dump(document, allow_unicode=True, sort_keys=False))
    text = pdf_text(result).replace(" ", "").replace("’", "'")
    assert "BRUNOd'ÁVILA,AnadaSilva,ClaradeSouza,DiegoExemplo" in text
    bold = []
    for page in PdfReader(io.BytesIO(result)).pages:
        page.extract_text(
            visitor_text=lambda text, cm, tm, font, size: (
                bold.append(text)
                if font and "bold" in str(font.get("/BaseFont")).lower()
                else None
            )
        )
    # Only the header is bold when author highlighting is disabled.
    assert "".join(bold).replace(" ", "").count("AnadaSilva") == 1


def test_author_symbols_are_literal_even_when_highlighted(fixtures, tmp_path):
    tree = ET.parse(fixtures / "authors.xml")
    author = tree.find(".//ARTIGO-PUBLICADO/AUTORES")
    name = 'Silva_* & #read("inexistente") [Nome]'
    author.set("NOME-COMPLETO-DO-AUTOR", name)
    path = tmp_path / "cv.xml"
    tree.write(path, encoding="utf-8")
    data, _ = export_data(read_lattes(path), Profile(include=["publications.articles"]))
    result = render_pdf(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    text = pdf_text(result)
    assert (name + ",").replace(" ", "") in text.replace(" ", "")
    assert "#text" not in text and "\\u{" not in text


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("filename", ["academic.xml", "professional.xml"])
def test_preset_profiles_render_contrasting_cvs(fixtures, tmp_path, preset, filename):
    profile = tmp_path / "profile.yaml"
    output = tmp_path / "cv.pdf"
    assert main(["profile", preset, "-o", str(profile)]) == 0
    assert (
        main(
            [
                "render",
                str(fixtures / filename),
                "--profile",
                str(profile),
                "-o",
                str(output),
            ]
        )
        == 0
    )
    text = pdf_text(output.read_bytes()).replace(" ", "")
    if filename == "academic.xml":
        bio = "Pesquisadoraempreservaçãodigital"
        assert ("ana@example.org" in text) == (preset != "resumido")
        assert "Catálogosabertos&memóriadigital" in text
        assert "BrunoExemploFictício" in text
        assert "Título:" in text
    else:
        bio = "Museólogacomatuaçãoemacessibilidadecultural"
        assert ("sofia@example.org" in text) == (preset != "resumido")
        assert "Percursosdamemórialocal" in text
        assert "Diagnósticodeacessibilidadeemmuseuscomunitários" in text
        assert "Artigospublicados" not in text
    assert bio not in text


@pytest.mark.parametrize("theme", THEMES)
def test_context_and_explicit_header_links_render_across_themes(fixtures, theme):
    cv = read_lattes(fixtures / "context.xml")
    social = next(
        e
        for e in cv.entries
        if e.section == "technical.web" and e.title() == "LinkedIn"
    )
    data, _ = export_data(
        cv,
        Profile(
            theme=theme,
            hide_fields=["details"],
            header_links=[social.id],
            exclude=["experience", "activities.projects"],
        ),
    )
    pdf = render_pdf(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    text = pdf_text(pdf)
    for expected in (
        "LinkedIn",
        "Iniciação científica: Diana Exemplo Fictícia",
        "Doutorado: Eduardo Exemplo Fictício",
        "Coorientação",
        "Universidade Fictícia do Vale",
        "Integrantes:",
        "Bruno Exemplo Fictício",
        "Leitura: bem",
        "Fala: razoavelmente",
        "Escrita: pouco",
        "Simpósio Fictício de Memória",
        "Congresso Fictício de Arquivos",
    ):
        assert expected.replace(" ", "") in text.replace(" ", "")
    assert "Carla Exemplo Fictícia" not in text
    assert "#text" not in text and "\\u{" not in text
    reader = PdfReader(io.BytesIO(pdf))
    links = [
        a.get_object().get("/A", {}).get("/URI")
        for p in reader.pages
        for a in p.get("/Annots", [])
    ]
    assert "https://www.linkedin.com/in/pessoa-exemplo-ficticia/" in links
    assert "https://example.org/encontro" in links
    assert "https://example.org/entrevista" in links


def test_header_link_labels_and_media_urls_preserve_literal_punctuation(
    fixtures, tmp_path
):
    tree = ET.parse(fixtures / "context.xml")
    social = tree.find(".//DADOS-BASICOS-DA-MIDIA-SOCIAL-WEBSITE-BLOG")
    social.set("TITULO", "Perfil [pessoal] & contatos")
    address = "https://example.org/entrevista_(aberta)?a=1&b=2"
    tree.find(".//DADOS-BASICOS-DO-PROGRAMA-DE-RADIO-OU-TV").set("HOME-PAGE", address)
    source = tmp_path / "cv.xml"
    tree.write(source, encoding="utf-8")
    cv = read_lattes(source)
    entry = next(e for e in cv.entries if e.section == "technical.web")
    radio = next(e for e in cv.entries if e.section == "technical.broadcasts")
    data, _ = export_data(
        cv, Profile(include_ids=[entry.id, radio.id], header_links=[entry.id])
    )
    pdf = render_pdf(yaml.safe_dump(data, allow_unicode=True))
    assert "Perfil [pessoal] & contatos" in pdf_text(pdf)
    assert "#text" not in pdf_text(pdf)
    reader = PdfReader(io.BytesIO(pdf))
    links = [
        a.get_object().get("/A", {}).get("/URI")
        for p in reader.pages
        for a in p.get("/Annots", [])
    ]
    assert "https://example.org/entrevista_%28aberta%29?a=1&b=2" in links


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

    monkeypatch.setattr("lattes2pdf.cli.render_pdf", fail)
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

    monkeypatch.setattr("lattes2pdf.cli.render_pdf", unexpected)
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

    monkeypatch.setattr("lattes2pdf.backend.subprocess.run", run)
    with pytest.raises(
        CVError,
        match={"timeout": "--timeout", "network": "packages.typst.org"}.get(
            failure, "--log-level DEBUG"
        ),
    ) as captured:
        render_pdf("cv: {name: Exemplo}")
    if failure in {"validation", "missing-output"}:
        assert captured.value.details == "invalid input"
    assert all(not path.exists() for path in directories)


def test_missing_or_unsupported_backend_has_an_install_hint(monkeypatch):
    def missing(_):
        raise PackageNotFoundError("rendercv")

    monkeypatch.setattr("lattes2pdf.backend.version", missing)
    with pytest.raises(CVError, match="pip install"):
        rendercv_version()
    monkeypatch.setattr("lattes2pdf.backend.version", lambda _: "3.0")
    with pytest.raises(CVError, match="não é suportado"):
        rendercv_version()
