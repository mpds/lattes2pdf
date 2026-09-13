import json
from pathlib import Path

import pytest
import yaml

from lattes2pdf.cli import inspection, main
from lattes2pdf.lattes import read_lattes
from lattes2pdf.models import CVError
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import Profile, load_profile, select


@pytest.fixture
def native_cv(fixtures):
    cv = read_lattes(fixtures / "native-categories.xml")
    assert not cv.issues
    return cv


@pytest.mark.parametrize(
    "category, expected",
    [
        ("formacao", {"education", "training"}),
        ("atuacao", {"experience", "activities.internships"}),
        ("projetos", {"research.projects"}),
        ("eventos", {"events", "technical.events"}),
    ],
)
def test_native_categories_include_related_sections_without_project_context_duplicates(
    native_cv, category, expected
):
    selection = select(native_cv, Profile(include=["lattes." + category]))
    assert {e.section for e in selection.entries} == expected


@pytest.mark.parametrize(
    "category, titles",
    [
        ("software", {"Software Livre Exemplo"}),
        ("patentes", {"Software Registrado Exemplo"}),
        (
            "assessoria-consultoria",
            {"Consultoria em acervos", "Assessoria em arquivos"},
        ),
        ("extensao-tecnologica", {"Extensão de acervo digital"}),
        ("trabalhos-tecnicos", {"Parecer sobre catalogação"}),
        ("inovacao", {"Projeto Acervo Aberto", "Software Registrado Exemplo"}),
        ("popularizacao", {"Acervos para todos", "Software Registrado Exemplo"}),
    ],
)
def test_native_subsets_are_available_in_selection_and_inspection(
    native_cv, category, titles
):
    selector = "lattes." + category
    selection = select(native_cv, Profile(include=[selector]))
    assert {e.title() for e in selection.entries} == titles
    assert {e["title"] for e in inspection(native_cv, [selector])["entries"]} == titles


def test_combined_categories_never_repeat_a_record_and_id_exclusion_still_wins(
    native_cv,
):
    profile = Profile(
        include=[
            "lattes.projetos",
            "lattes.patentes",
            "lattes.inovacao",
            "lattes.popularizacao",
        ],
        hide_fields=["details"],
    )
    data, report = export_data(native_cv, profile)
    text = json.dumps(data, ensure_ascii=False)
    for title in [
        "Projeto Acervo Aberto",
        "Software Registrado Exemplo",
        "Acervos para todos",
    ]:
        assert text.count(title) == 1
    assert sum(e["status"] == "selected" for e in report["entries"]) == 3
    chosen = next(
        e for e in native_cv.entries if e.title() == "Software Registrado Exemplo"
    )
    profile.exclude_ids = [chosen.id]
    data, report = export_data(native_cv, profile)
    assert chosen.title() not in json.dumps(data, ensure_ascii=False)
    assert next(e for e in report["entries"] if e["id"] == chosen.id)["reason"] == "id"


def test_category_exclusions_and_years_compose_with_canonical_sections(native_cv):
    profile = Profile(
        include=["technical", "lattes.projetos"],
        exclude=["lattes.patentes"],
        section_years={"lattes.software": {"since": 2024}},
        order=["research.projects", "technical.work"],
    )
    entries = select(native_cv, profile).entries
    assert entries[0].section == "research.projects"
    assert not any(e.section == "technical.software" for e in entries)
    assert any(e.title() == "Consultoria em acervos" for e in entries)


def test_address_toggle_is_independent_of_generic_details_and_other_private_fields(
    native_cv,
):
    for show in [False, True]:
        data, report = export_data(
            native_cv,
            Profile(
                include=["profile"],
                show_address=show,
                hide_fields=["details", "summary"],
            ),
        )
        text = json.dumps(data, ensure_ascii=False)
        for value in [
            "Rua Profissional Fictícia",
            "Rua Residencial Fictícia",
            "contato@example.org",
        ]:
            assert (value in text) == show
        assert "DOCUMENTO-PRIVADO" not in text
        if show:
            residential = [
                f for f in report["fields"] if "ENDERECO-RESIDENCIAL" in f["path"]
            ]
            assert all(
                f["status"] == "exported" and f["reason"] == "explicit-selection"
                for f in residential
            )
    data, _ = export_data(
        native_cv, Profile(show_address=True, hide_fields=["contact"])
    )
    assert "Rua Residencial Fictícia" not in json.dumps(data, ensure_ascii=False)
    legacy, _ = export_data(native_cv, Profile(include=["profile"]))
    assert legacy["cv"]["email"] == "trabalho@example.org"
    assert "Rua Residencial Fictícia" not in json.dumps(legacy, ensure_ascii=False)


def test_other_information_and_leave_are_explicit_categories(native_cv):
    data, _ = export_data(
        native_cv,
        Profile(
            include=["lattes.outras-informacoes", "lattes.licencas"],
            hide_fields=["details"],
        ),
    )
    text = json.dumps(data, ensure_ascii=False)
    assert "Disponibilidade para colaboração fictícia" in text
    assert "Pesquisadora fictícia em acervos" not in text
    assert "MATERNIDADE" in text
    assert "Rua Residencial Fictícia" not in text
    assert "DOCUMENTO-PRIVADO" not in text


def test_excluding_other_information_preserves_address_and_profile(native_cv):
    profile = Profile(
        include=["profile", "lattes.outras-informacoes"],
        exclude=["lattes.outras-informacoes"],
        show_address=True,
    )
    data, report = export_data(native_cv, profile)
    text = json.dumps(data, ensure_ascii=False)
    assert "Disponibilidade para colaboração fictícia" not in text
    assert "Rua Residencial Fictícia" in text
    assert "Pesquisadora fictícia em acervos" in text
    info = next(
        f for f in report["fields"] if "@OUTRAS-INFORMACOES-RELEVANTES" in f["path"]
    )
    assert info["status"] == "excluded"


def test_custom_order_and_titles_apply_with_native_categories(native_cv):
    profile = Profile(
        include=[
            "profile",
            "lattes.formacao",
            "lattes.patentes",
            "lattes.outras-informacoes",
        ],
        order=["lattes.patentes", "education", "profile"],
        sections={
            "lattes.patentes": {"title": "Registros"},
            "education": {"title": "Estudos"},
        },
        show_address=True,
        hide_fields=["details"],
    )
    data, _ = export_data(native_cv, profile)
    titles = list(data["cv"]["sections"])
    assert titles[:2] == ["Registros — Software", "Estudos"]
    assert titles.index("Estudos") < titles.index("Endereço")
    profile.sections["education"]["title"] = "Endereço"
    with pytest.raises(CVError, match="Título de seção repetido"):
        export_data(native_cv, profile)


def test_all_native_categories_remain_editable_and_do_not_mean_full(native_cv):
    data, report = export_data(
        native_cv,
        Profile(include=["lattes"], exclude=["lattes.patentes"], show_address=False),
    )
    assert not report["full_requested"]
    assert "Software Registrado Exemplo" not in json.dumps(data, ensure_ascii=False)
    assert not any(
        e["section"] == "activities.projects" and e["status"] == "selected"
        for e in report["entries"]
    )


@pytest.mark.parametrize("value", [True, False, "yes", 1])
def test_full_does_not_accept_address_options(value):
    with pytest.raises(CVError):
        Profile(full=True, show_address=value).validate()


def test_cli_address_override_and_category_help(fixtures, tmp_path, capsys):
    assert main(["sections"]) == 0
    default_catalogue = capsys.readouterr().out
    assert "lattes.formacao" in default_catalogue
    assert main(["sections", "lattes"]) == 0
    assert capsys.readouterr().out == default_catalogue
    assert main(["sections", "lattes.formacao"]) == 0
    category_help = capsys.readouterr().out
    assert "education — Formação acadêmica/titulação" in category_help
    assert "training — Formação complementar" in category_help
    assert "sections.education" in category_help and "show_advisors" in category_help
    profile = tmp_path / "profile.yaml"
    assert main(["profile", "ampliado", "-o", str(profile)]) == 0
    output = tmp_path / "cv.yaml"
    assert (
        main(
            [
                "export",
                str(fixtures / "native-categories.xml"),
                "--profile",
                str(profile),
                "--no-show-address",
                "-o",
                str(output),
            ]
        )
        == 0
    )
    assert "Rua Residencial Fictícia" not in output.read_text()
    assert (
        main(
            [
                "export",
                str(fixtures / "native-categories.xml"),
                "--show-address",
                "--include",
                "lattes.formacao",
                "--force",
                "-o",
                str(output),
            ]
        )
        == 0
    )
    data = yaml.safe_load(output.read_text())
    assert set(data["cv"]["sections"]) == {
        "Endereço",
        "Formação acadêmica/titulação",
        "Formação complementar",
    }


def test_category_inspection_groups_and_ids_drive_exclusions(
    fixtures, tmp_path, capsys
):
    source = str(fixtures / "native-categories.xml")
    inspect_args = ["inspect", source, "--section", "lattes.formacao"]
    assert main(inspect_args) == 0
    text = capsys.readouterr().out
    assert "training — Formação complementar" in text
    assert "--exclude GRUPO" in text and "--exclude-id ID" in text
    assert main(inspect_args + ["--json"]) == 0
    inventory = json.loads(capsys.readouterr().out)
    training = next(e for e in inventory["entries"] if e["section"] == "training")
    assert training["id"] in text
    for option, value in [("--exclude", "training"), ("--exclude-id", training["id"])]:
        output = tmp_path / (option + ".yaml")
        assert (
            main(
                [
                    "export",
                    source,
                    "--include",
                    "lattes.formacao",
                    option,
                    value,
                    "-o",
                    str(output),
                ]
            )
            == 0
        )
        data = yaml.safe_load(output.read_text())
        assert list(data["cv"]["sections"]) == ["Formação acadêmica/titulação"]


@pytest.mark.parametrize("name", ["resumido", "ampliado", "completo"])
def test_presets_have_native_content_boundaries(native_cv, name):
    profile = load_profile(
        Path(__file__).parents[1] / "src/lattes2pdf/presets" / f"{name}.yaml"
    )
    data, _ = export_data(native_cv, profile)
    text = json.dumps(data, ensure_ascii=False)
    for title in [
        "Arquivologia",
        "Preservação digital",
        "Catalogação fictícia",
        "Software Livre Exemplo",
        "Parecer sobre catalogação",
    ]:
        assert title in text
    for title in [
        "Projeto Acervo Aberto",
        "Software Registrado Exemplo",
        "Consultoria em acervos",
        "Extensão de acervo digital",
        "Congresso Exemplo",
    ]:
        assert (title in text) == (name == "completo")
    for title in ["Inglês", "Prêmio Exemplo", "Rua Residencial Fictícia"]:
        assert (title in text) == (name != "resumido")
    assert "DOCUMENTO-PRIVADO" not in text
