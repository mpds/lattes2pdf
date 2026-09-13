import copy
import xml.etree.ElementTree as ET

import pytest

from lattes2pdf.cli import inspection
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
