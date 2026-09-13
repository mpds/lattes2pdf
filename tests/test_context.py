import json
import xml.etree.ElementTree as ET

import pytest

from lattes2pdf.cli import inspection
from lattes2pdf.lattes import read_lattes
from lattes2pdf.models import CVError
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import Profile


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
    assert events[0]["summary"] == "Simpósio Fictício de Memória"
    assert events[1]["name"] == "Congresso Fictício de Arquivos"
    assert "summary" not in events[1]
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
    assert "Descrição extensa" in sections["Projetos"][0]["description"]
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
    data, _ = export_data(
        read_lattes(fixtures / "context.xml"),
        Profile(language="en", sections={"events": {"show_event_type": True}}),
    )
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


def test_header_links_move_only_explicitly_selected_media_and_preserve_accounting(
    fixtures,
):
    cv = read_lattes(fixtures / "context.xml")
    social = next(
        e
        for e in cv.entries
        if e.section == "technical.web" and e.title() == "LinkedIn"
    )
    data, report = export_data(
        cv, Profile(include=["technical.web"], header_links=[social.id])
    )
    assert data["cv"]["custom_connections"] == [
        {
            "fontawesome_icon": "link",
            "placeholder": "LinkedIn",
            "url": "https://www.linkedin.com/in/pessoa-exemplo-ficticia/",
        }
    ]
    assert [e["name"] for e in data["cv"]["sections"]["Mídia digital"]] == [
        "Site de projeto"
    ]
    source = social.find("HOME-PAGE")
    assert (
        next(f for f in report["fields"] if f["path"] == source.path)["status"]
        == "exported"
    )
    assert not report["counts"].get("unmapped")
    for field in ("links", "contact"):
        hidden, _ = export_data(
            cv,
            Profile(
                include_ids=[social.id], header_links=[social.id], hide_fields=[field]
            ),
        )
        assert "custom_connections" not in hidden["cv"]
        assert not hidden["cv"]["sections"]
    hidden, _ = export_data(
        cv,
        Profile(
            include_ids=[social.id],
            header_links=[social.id],
            sections={"technical.web": {"show_links": False}},
        ),
    )
    assert "custom_connections" not in hidden["cv"] and not hidden["cv"]["sections"]
    with pytest.raises(CVError, match="header_links"):
        export_data(cv, Profile(exclude=["technical.web"], header_links=[social.id]))
    with pytest.raises(CVError, match="header_links"):
        export_data(cv, Profile(header_links=[cv.entries[0].id]))
    with pytest.raises(CVError, match="IDs desconhecidos"):
        export_data(cv, Profile(header_links=["technical.web:missing"]))


def test_invalid_media_url_stays_text_and_cannot_become_a_header_link(
    fixtures, tmp_path
):
    tree = ET.parse(fixtures / "context.xml")
    tree.find(".//DADOS-BASICOS-DA-MIDIA-SOCIAL-WEBSITE-BLOG").set(
        "HOME-PAGE", "javascript:alert(1)"
    )
    source = tmp_path / "cv.xml"
    tree.write(source, encoding="utf-8")
    cv = read_lattes(source)
    social = next(e for e in cv.entries if e.section == "technical.web")
    data, report = export_data(
        cv, Profile(include_ids=[social.id], header_links=[social.id])
    )
    assert "custom_connections" not in data["cv"]
    assert (
        "Link: javascript:alert(1)"
        == data["cv"]["sections"]["Mídia digital"][0]["summary"]
    )
    assert any(i["code"] == "invalid-url" for i in report["issues"])
    assert not report["counts"].get("unmapped")


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
