import json
import xml.etree.ElementTree as ET

import pytest

from cv_lattex.cli import inspection
from cv_lattex.lattes import read_lattes
from cv_lattex.rendering import export_data
from cv_lattex.selection import Profile


def test_concise_sections_keep_context_and_report_what_was_displayed(fixtures):
    cv = read_lattes(fixtures / "context.xml")
    data, report = export_data(cv, Profile(hide_fields=["details"]))
    sections = data["cv"]["sections"]
    completed = sections["Orientações concluídas"][0]
    assert completed["name"] == "Catalogação de mapas históricos"
    assert "Iniciação científica: Diana Exemplo Fictícia" in completed["summary"]
    ongoing = sections["Orientações em andamento"][0]
    assert "Doutorado: Eduardo Exemplo Fictício" in ongoing["summary"]
    assert "Coorientação" in ongoing["summary"]
    for name in ["Estágios", "Extensão", "Outras atividades", "Conselhos e comissões"]:
        assert "Universidade Fictícia do Vale" in sections[name][0]["summary"]
    project = sections["Projetos"][0]
    assert project["name"] == "Memórias abertas"
    assert "Universidade Fictícia do Vale" in project["summary"]
    assert (
        "Ana Exemplo Fictícia (responsável), Bruno Exemplo Fictício"
        in project["summary"]
    )
    assert "Descrição extensa" not in project["summary"]
    language = sections["Idiomas"][0]
    assert language["summary"] == "Leitura: bem; Fala: razoavelmente; Escrita: pouco"
    events = sections["Participação em eventos"]
    assert events[0]["name"] == "Mapas e comunidades"
    assert events[0]["summary"].splitlines() == [
        "Simpósio Fictício de Memória",
        "Simpósio; Apresentação Oral",
    ]
    assert events[1]["name"] == "Congresso Fictício de Arquivos"
    assert events[1]["summary"] == "Congresso"
    assert any(
        e["title"] == "Congresso Fictício de Arquivos"
        for e in inspection(cv, ["events"])["entries"]
    )
    assert "Carla Exemplo Fictícia" not in json.dumps(data, ensure_ascii=False)
    assert (
        "[Link](https://example.org/entrevista)" in sections["Rádio e TV"][0]["summary"]
    )
    assert "linkedin.com" in sections["Mídia digital"][0]["summary"]
    fields = {f["path"]: f for f in report["fields"]}
    for source in cv.fields:
        if source.name in {
            "NOME-DO-ORIENTADO",
            "NOME-DO-ORIENTANDO",
            "NOME-DO-EVENTO",
            "PROFICIENCIA-DE-LEITURA",
        }:
            assert fields[source.path]["status"] == "exported"
        if source.name == "PROFICIENCIA-DE-COMPREENSAO":
            assert fields[source.path]["reason"] == "presentation"
    assert not report["counts"].get("unmapped") and not report["counts"].get("unknown")
    assert cv.raw_xml == (fixtures / "context.xml").read_bytes()


def test_context_options_and_explicit_field_filters_do_not_leak(fixtures):
    cv = read_lattes(fixtures / "context.xml")
    data, report = export_data(
        cv,
        Profile(
            sections={
                "supervision.completed": {
                    "show_students": False,
                    "show_institution": False,
                },
                "languages": {"show_proficiency": False},
                "research.projects": {"show_members": False, "show_description": True},
                "technical.events": {"show_authors": True, "show_links": False},
                "technical.broadcasts": {"show_authors": True},
                "activities.internships": {"show_institution": False},
            },
            hide_fields=["details", "NOME-DO-EVENTO"],
        ),
    )
    sections = data["cv"]["sections"]
    text = json.dumps(sections, ensure_ascii=False)
    assert "Diana Exemplo Fictícia" not in text
    assert "Bruno Exemplo Fictício" not in text
    assert "Descrição extensa" in sections["Projetos"][0]["summary"]
    assert "summary" not in sections["Idiomas"][0]
    assert "summary" not in sections["Estágios"][0]
    assert "Carla Exemplo Fictícia" in sections["Organização de eventos"][0]["summary"]
    assert "https://example.org/encontro" not in text
    assert "Simpósio Fictício de Memória" not in text
    assert sections["Participação em eventos"][1]["name"] == "Evento sem nome informado"
    assert not report["counts"].get("unmapped")


@pytest.mark.parametrize(
    "nature,level",
    [
        ("INICIACAO_CIENTIFICA", "Iniciação científica"),
        ("TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO", "Graduação"),
        (
            "MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO",
            "Aperfeiçoamento/especialização",
        ),
        ("Atividade interdisciplinar", "Atividade interdisciplinar"),
    ],
)
def test_supervision_level_uses_canonical_values_and_preserves_other_text(
    fixtures, tmp_path, nature, level
):
    tree = ET.parse(fixtures / "context.xml")
    tree.find(".//DADOS-BASICOS-DE-OUTRAS-ORIENTACOES-CONCLUIDAS").set(
        "NATUREZA", nature
    )
    source = tmp_path / "cv.xml"
    tree.write(source, encoding="utf-8")
    data, _ = export_data(
        read_lattes(source), Profile(include=["supervision.completed"])
    )
    entry = data["cv"]["sections"]["Orientações concluídas"][0]
    assert entry["summary"].startswith(level + ": Diana Exemplo Fictícia")


def test_context_english_uses_source_translations_and_keeps_proficiency_values(
    fixtures,
):
    data, _ = export_data(read_lattes(fixtures / "context.xml"), Profile(language="en"))
    sections = data["cv"]["sections"]
    assert sections["Completed supervision"][0]["name"] == "Cataloguing historical maps"
    assert "Undergraduate research" in sections["Completed supervision"][0]["summary"]
    assert (
        "Fictional Memory Symposium\nSymposium"
        in sections["Event participation"][0]["summary"]
    )
    assert (
        "Reading: well; Speaking: reasonably; Writing: a little"
        == sections["Languages"][0]["summary"]
    )
    assert "Open memories" == sections["Projects"][0]["name"]


def test_full_retains_context_and_raw_details_without_concise_omissions(fixtures):
    cv = read_lattes(fixtures / "context.xml")
    data, report = export_data(cv, Profile(full=True))
    text = json.dumps(data, ensure_ascii=False)
    assert "Descrição extensa" in text
    assert "Carla Exemplo Fictícia" in text
    source = next(f for f in cv.fields if f.name == "PROFICIENCIA-DE-COMPREENSAO")
    assert (
        next(f for f in report["fields"] if f["path"] == source.path)["status"]
        == "exported"
    )
    assert not report["counts"].get("unknown") and not report["counts"].get("unmapped")
