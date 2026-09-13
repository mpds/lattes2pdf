import json
import xml.etree.ElementTree as ET

import pytest
import yaml

from lattes2pdf.cli import main
from lattes2pdf.lattes import read_lattes
from lattes2pdf.models import CVError
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import Profile, load_profile, select


def titles(selection):
    return {e.title() for e in selection.entries}


def test_independent_periods_preserve_unrelated_content_and_context(fixtures):
    cv = read_lattes(fixtures / "periods.xml")
    selection = select(
        cv,
        Profile(
            periods={"professional": {"since": 2020}, "production": {"since": 2022}}
        ),
    )
    chosen = titles(selection)
    assert {
        "Sobreposto",
        "Atual",
        "Limite",
        "Posterior",
        "Fim conhecido",
        "Estágio atual",
        "Linha recente",
        "Artigo no limite",
    } <= chosen
    assert (
        not {
            "Encerrado",
            "Linha antiga",
            "Artigo antigo",
            "Trabalho completo antigo",
            "Software antigo",
        }
        & chosen
    )
    assert {
        "Meteorologia",
        "Análise de dados",
        "Projeto antigo",
        "Prêmio de pesquisa",
        "Inglês",
        "Evento organizado antigo",
        "Participação antiga",
    } <= chosen
    uncertain = {
        "Sem datas",
        "Invertido",
        "Fim inválido",
        "Estágio anterior incompleto",
        "Estágio sem situação",
        "Artigo sem ano",
    }
    assert uncertain <= chosen
    assert {
        e.title() for e in cv.entries if e.path in {i.path for i in selection.issues}
    } == uncertain
    omitted = {e.title(): selection.excluded.get(e.id) for e in cv.entries}
    assert omitted["Encerrado"] == "professional-period"
    assert omitted["Artigo antigo"] == "production-period"


def test_unknown_dates_excluded_only_within_active_scope(fixtures):
    cv = read_lattes(fixtures / "periods.xml")
    selected = select(
        cv, Profile(periods={"professional": {"since": 2020}}, unknown_year="exclude")
    )
    assert {"Atual", "Estágio atual", "Artigo sem ano", "Inglês"} <= titles(selected)
    assert not {
        "Sem datas",
        "Invertido",
        "Fim inválido",
        "Estágio anterior incompleto",
        "Estágio sem situação",
    } & titles(selected)
    assert not selected.issues


@pytest.mark.parametrize(
    "bounds,keep,drop",
    [
        (
            {"since": 2020, "until": 2020},
            {"Sobreposto", "Atual", "Limite"},
            {"Encerrado", "Posterior"},
        ),
        (
            {"until": 2014},
            set(),
            {"Encerrado", "Sobreposto", "Atual", "Limite", "Posterior"},
        ),
        (
            {"since": 2023},
            {"Atual", "Posterior"},
            {"Encerrado", "Sobreposto", "Limite", "Fim conhecido"},
        ),
    ],
)
def test_professional_period_uses_overlap_not_start_or_end_year(
    fixtures, bounds, keep, drop
):
    selected = select(
        read_lattes(fixtures / "periods.xml"), Profile(periods={"professional": bounds})
    )
    assert keep <= titles(selected)
    assert not drop & titles(selected)


def test_general_and_section_filters_remain_cumulative(fixtures):
    cv = read_lattes(fixtures / "periods.xml")
    selected = select(
        cv,
        Profile(
            periods={"production": {"since": 2020}},
            section_years={"lattes.artigos": {"until": 2021}},
            unknown_year="exclude",
        ),
    )
    assert not any(e.section == "publications.articles" for e in selected.entries)
    assert "Meteorologia" in titles(selected)
    general = select(cv, Profile(since=2020, periods={"production": {"since": 2022}}))
    assert "Meteorologia" not in titles(general)


def test_production_scope_does_not_depend_on_selected_alias(fixtures):
    cv = read_lattes(fixtures / "presentation.xml")
    result = select(
        cv,
        Profile(
            include=["lattes.inovacao", "lattes.patentes"],
            periods={"production": {"since": 2025}},
        ),
    )
    assert not result.entries
    cv = read_lattes(fixtures / "general.xml")
    unfiltered = select(cv, Profile())
    filtered = select(
        cv, Profile(periods={"production": {"since": 9999}}, unknown_year="exclude")
    )
    outside = {
        e.id
        for e in unfiltered.entries
        if e.section
        in {
            "education",
            "training",
            "supervision.completed",
            "supervision.ongoing",
            "events",
            "committees",
            "research.projects",
            "technical.events",
        }
    }
    assert outside <= {e.id for e in filtered.entries}
    assert not any(e.section == "artistic" for e in filtered.entries)


@pytest.mark.parametrize(
    "periods",
    [
        None,
        [],
        {"other": {}},
        {"professional": []},
        {"production": {"from": 2020}},
        {"professional": {"since": True}},
        {"production": {"until": "2020"}},
        {"professional": {"since": 2022, "until": 2020}},
    ],
)
def test_invalid_periods_fail_when_loading_profile(tmp_path, periods):
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump({"periods": periods}))
    with pytest.raises(CVError):
        load_profile(path)


def test_empty_periods_and_full_compatibility(fixtures):
    cv = read_lattes(fixtures / "periods.xml")
    assert (
        select(cv, Profile()).entries
        == select(
            cv, Profile(periods={"professional": {}, "production": {"since": None}})
        ).entries
    )
    assert (
        select(cv, Profile(full=True)).entries
        == select(cv, Profile(full=True, periods={"production": {}})).entries
    )
    with pytest.raises(CVError, match="--full"):
        select(cv, Profile(full=True, periods={"professional": {"since": 2020}}))


def test_ongoing_dates_respect_source_visibility_and_full(fixtures):
    cv = read_lattes(fixtures / "periods.xml")
    current = next(e for e in cv.entries if e.title() == "Atual")
    closed = next(e for e in cv.entries if e.title() == "Sobreposto")
    data, _ = export_data(
        cv,
        Profile(
            include_ids=[current.id, closed.id],
            periods={"professional": {"since": 2020}},
        ),
    )
    entries = {
        e["position"]: e for e in data["cv"]["sections"]["Experiência profissional"]
    }
    assert entries["Atual"]["start_date"] == 2015
    assert entries["Atual"]["end_date"] == "present"
    assert entries["Sobreposto"]["start_date"] == 2015
    assert entries["Sobreposto"]["end_date"] == 2022
    hidden, _ = export_data(
        cv, Profile(include_ids=[closed.id], hide_fields=["ANO-FIM"])
    )
    assert (
        hidden["cv"]["sections"]["Experiência profissional"][0]["date"]
        == "Início: 2015"
    )
    full, _ = export_data(cv, Profile(full=True))
    assert (
        next(
            e
            for e in full["cv"]["sections"]["Experiência profissional"]
            if e["position"] == "Atual"
        )["date"]
        == "Início: 2015"
    )


def test_inverted_months_and_incomplete_end_are_not_current(fixtures, tmp_path):
    tree = ET.parse(fixtures / "periods.xml")
    record = tree.find(".//VINCULOS")
    record.set("ANO-INICIO", "2020")
    record.set("ANO-FIM", "2020")
    record.set("MES-INICIO", "12")
    record.set("MES-FIM", "01")
    path = tmp_path / "cv.xml"
    tree.write(path, encoding="utf-8")
    cv = read_lattes(path)
    result = select(
        cv, Profile(periods={"professional": {"since": 2020}}, unknown_year="exclude")
    )
    assert "Encerrado" not in titles(result)
    record.set("ANO-FIM", "")
    tree.write(path, encoding="utf-8")
    cv = read_lattes(path)
    result = select(
        cv, Profile(periods={"professional": {"since": 2020}}, unknown_year="exclude")
    )
    assert "Encerrado" not in titles(result)


@pytest.mark.parametrize("command", ["export", "render"])
def test_profile_cli_export_preserves_ids_and_records_period_exclusion(
    fixtures, tmp_path, command
):
    profile = tmp_path / "profile.yaml"
    assert main(["profile", "completo", "-o", str(profile)]) == 0
    settings = yaml.safe_load(profile.read_text())
    settings["periods"] = {
        "professional": {"since": 2020},
        "production": {"since": 2022},
    }
    profile.write_text(yaml.safe_dump(settings))
    target = tmp_path / ("cv.pdf" if command == "render" else "cv.yaml")
    source = fixtures / "periods.xml"
    before = source.read_bytes()
    assert (
        main([command, str(source), "--profile", str(profile), "-o", str(target)]) == 0
    )
    output = yaml.safe_load(target.with_suffix(".yaml").read_text())
    assert (
        output["cv"]["sections"]["Formação acadêmica/titulação"][0]["end_date"] == 2014
    )
    report = json.loads(target.with_suffix(".report.json").read_text())
    assert "professional-period" in json.dumps(
        report
    ) and "production-period" in json.dumps(report)
    assert source.read_bytes() == before
    cv = read_lattes(source)
    assert {e.id for e in select(cv, load_profile(profile)).entries} <= {
        e.id for e in cv.entries
    }
