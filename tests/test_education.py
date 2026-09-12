import json
import xml.etree.ElementTree as ET

import pytest
import yaml

from lattes2pdf.cli import main
from lattes2pdf.lattes import read_lattes
from lattes2pdf.models import CVError
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import Profile, load_profile

TITLE = "Formação acadêmica/titulação"


def test_education_defaults_preserve_records_states_and_source(fixtures):
    source = fixtures / "education.xml"
    cv = read_lattes(source)
    data, report = export_data(cv, Profile())
    entries = data["cv"]["sections"][TITLE]
    assert len(entries) == 5
    doctorate, masters, incomplete, graduation, missing = entries
    assert doctorate["end_date"] == "present"
    assert "Em andamento" not in doctorate["summary"]
    assert masters["start_date"] == 2021 and masters["end_date"] == 2023
    assert "Concluído" not in masters["summary"]
    assert incomplete["date"] == "Início: 2020"
    assert "Incompleto" in incomplete["summary"]
    assert "end_date" not in incomplete
    assert graduation["end_date"] == 2019
    assert missing["date"] == "Início: 2013"
    assert "summary" not in missing and "end_date" not in missing
    text = json.dumps(data, ensure_ascii=False)
    for omitted in [
        "ID-FICTICIO",
        "AGENCIA-FICTICIA",
        "Clara Exemplo",
        "Flag",
        "Preservação digital",
    ]:
        assert omitted not in text
    assert any(f.get("reason") == "presentation" for f in report["fields"])
    assert not report["counts"].get("unmapped")
    assert cv.raw_xml == source.read_bytes()
    assert any(f.value == "ID-FICTICIO" for f in cv.fields)
    full, full_report = export_data(cv, Profile(full=True))
    assert "ID-FICTICIO" in json.dumps(full)
    assert not any(f.get("reason") == "presentation" for f in full_report["fields"])


def test_education_options_translation_and_explicit_hiding(fixtures):
    cv = read_lattes(fixtures / "education.xml")
    sections = {
        "education": {
            "show_thesis": True,
            "show_advisors": True,
            "title": "My education",
        }
    }
    data, report = export_data(cv, Profile(language="en", sections=sections))
    text = json.dumps(data, ensure_ascii=False)
    assert "My education" in data["cv"]["sections"]
    assert "Preserving community collections" in text
    assert "Preservação de acervos comunitários" not in text
    assert "Memória e acesso a coleções digitais" in text  # No English version in XML.
    assert "Work title: Preserving community collections" in text
    assert "Advisor: Clara Exemplo" in text and "Co-advisor: Bruno Exemplo" in text
    assert "Incomplete" in text
    assert all(e["section"] in {"profile", "education"} for e in report["entries"])
    data, report = export_data(
        cv, Profile(sections=sections, hide_fields=["advisors", "thesis"])
    )
    text = json.dumps(data, ensure_ascii=False)
    assert "Clara Exemplo" not in text and "Preservação de acervos" not in text
    assert any(f.get("reason") == "field-filter" for f in report["fields"])


@pytest.mark.parametrize(
    "tag,field",
    [
        ("GRADUACAO", "TITULO-DO-TRABALHO-DE-CONCLUSAO-DE-CURSO"),
        ("ESPECIALIZACAO", "TITULO-DA-MONOGRAFIA"),
        ("MESTRADO-PROFISSIONALIZANTE", "TITULO-DA-DISSERTACAO-TESE"),
        ("RESIDENCIA-MEDICA", "TITULO-DA-RESIDENCIA-MEDICA"),
        ("LIVRE-DOCENCIA", "TITULO-DO-TRABALHO"),
    ],
)
def test_work_title_variants_from_the_cnpq_schema(tmp_path, tag, field):
    root = ET.Element("CURRICULO-VITAE")
    person = ET.SubElement(root, "DADOS-GERAIS", {"NOME-COMPLETO": "Pessoa Fictícia"})
    group = ET.SubElement(person, "FORMACAO-ACADEMICA-TITULACAO")
    ET.SubElement(
        group,
        tag,
        {field: "Trabalho fictício", "NOME-INSTITUICAO": "Instituição Fictícia"},
    )
    source = tmp_path / "cv.xml"
    ET.ElementTree(root).write(source, encoding="utf-8")
    cv = read_lattes(source)
    data, _ = export_data(cv, Profile(sections={"education": {"show_thesis": True}}))
    assert "Título do trabalho: Trabalho fictício" in json.dumps(
        data, ensure_ascii=False
    )


def test_status_remains_explicit_without_visible_end_dates(fixtures):
    cv = read_lattes(fixtures / "education.xml")
    data, _ = export_data(cv, Profile(hide_fields=["date"]))
    entries = data["cv"]["sections"][TITLE]
    assert "Em andamento" in entries[0]["summary"]
    assert "Concluído" in entries[1]["summary"]
    assert "Incompleto" in entries[2]["summary"]


def test_concise_presentation_does_not_change_other_sections_or_reclassify_unknown_fields(
    fixtures, tmp_path
):
    cv = read_lattes(fixtures / "academic.xml")
    full, _ = export_data(cv, Profile(full=True))
    normal, _ = export_data(cv, Profile())
    concise = {TITLE, "Artigos publicados", "Idiomas"}
    assert {k: v for k, v in full["cv"]["sections"].items() if k not in concise} == {
        k: v for k, v in normal["cv"]["sections"].items() if k not in concise
    }
    root = ET.parse(fixtures / "education.xml")
    root.find(".//MESTRADO").set("CAMPO-FUTURO", "Conteúdo fictício")
    source = tmp_path / "future.xml"
    root.write(source, encoding="utf-8")
    _, report = export_data(read_lattes(source), Profile())
    assert any(
        f["path"].endswith("/@CAMPO-FUTURO") and f["status"] == "unknown"
        for f in report["fields"]
    )


@pytest.mark.parametrize(
    "config",
    [
        "sections: []",
        "sections: {educaton: {show_thesis: true}}",
        "sections: {publications: {title: Produção}}",
        "sections: {education: {show_thesys: true}}",
        "sections: {education: {show_thesis: 1}}",
        "sections: {education: {title: ''}}",
        "sections: {education: {title: 123}}",
        "sections: {education: {title: 'Linha\n\n  extra'}}",
        "sections: {experience: {show_advisors: true}}",
        "full: true\nsections: {education: {show_thesis: true}}",
    ],
)
def test_invalid_section_options_are_actionable(tmp_path, config):
    path = tmp_path / "profile.yaml"
    path.write_text(config, encoding="utf-8")
    with pytest.raises(CVError):
        load_profile(path)


def test_duplicate_display_titles_do_not_merge_sections(fixtures):
    profile = Profile(sections={"education": {"title": "Artigos publicados"}})
    with pytest.raises(CVError, match="Título de seção repetido"):
        export_data(read_lattes(fixtures / "academic.xml"), profile)


def test_section_reference_and_id_workflow(fixtures, tmp_path, capsys):
    assert main(["sections", "education"]) == 0
    help_text = capsys.readouterr().out
    assert "show_thesis" in help_text and "show_advisors" in help_text
    assert main(["sections", "publications"]) == 0
    assert "publications.articles" in capsys.readouterr().out
    assert main(["sections", "educaton"]) == 2
    assert "lattes2pdf sections" in capsys.readouterr().err
    source = str(fixtures / "education.xml")
    assert main(["inspect", source, "--section", "education"]) == 0
    inventory_text = capsys.readouterr().out
    assert "Doutorado — Ciência da Informação (2025)" in inventory_text
    assert "Mestrado — Ciência da Informação (2023)" in inventory_text
    assert main(["inspect", source, "--section", "education", "--json"]) == 0
    records = json.loads(capsys.readouterr().out)["entries"]
    assert len(records) == 5 and all(e["section"] == "education" for e in records)
    chosen = next(e for e in records if e["title"] == "Gestão de acervos")["id"]
    path = tmp_path / "profile.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "include": ["education"],
                "exclude_ids": [chosen],
                "sections": {"education": {"show_thesis": True}},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "cv.yaml"
    assert main(["export", source, "--profile", str(path), "-o", str(output)]) == 0
    document = yaml.safe_load(output.read_text())
    assert len(document["cv"]["sections"][TITLE]) == 4
    assert "Gestão de acervos" not in output.read_text()
    report = json.loads(output.with_suffix(".report.json").read_text())
    assert next(e for e in report["entries"] if e["id"] == chosen)["reason"] == "id"
