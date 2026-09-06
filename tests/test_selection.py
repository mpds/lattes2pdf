import pytest

from cv_lattex.lattes import read_lattes
from cv_lattex.models import CVError
from cv_lattex.selection import Profile, load_profile, select


def test_section_prefixes_exclusions_and_order(fixtures):
    cv = read_lattes(fixtures / "bibliography.xml")
    selected = select(
        cv,
        Profile(
            include=["publications"],
            exclude=["publications.press"],
            order=["publications.books"],
        ),
    )
    assert selected.entries[0].section == "publications.books"
    assert len(selected.entries) == 9
    assert not any(
        e.section in {"profile", "publications.press"} for e in selected.entries
    )


def test_year_filters_apply_to_publication_year_and_keep_unknowns_explicitly(fixtures):
    cv = read_lattes(fixtures / "bibliography.xml")
    result = select(cv, Profile(include=["publications"], since=2024))
    assert {e.section for e in result.entries} == {
        "publications.articles",
        "publications.accepted",
    }
    assert any(issue.code == "unknown-year" for issue in result.issues)
    result = select(
        cv, Profile(include=["publications"], since=2024, unknown_year="exclude")
    )
    assert [e.year for e in result.entries] == [2024]


def test_section_years_do_not_filter_other_sections(fixtures):
    cv = read_lattes(fixtures / "general.xml")
    result = select(cv, Profile(section_years={"education": {"since": 2025}}))
    assert not any(e.section == "education" for e in result.entries)
    assert any(e.section == "experience" for e in result.entries)


def test_id_selection_and_unknown_id_errors(fixtures):
    cv = read_lattes(fixtures / "bibliography.xml")
    chosen = next(e for e in cv.entries if e.section == "publications.books")
    assert select(cv, Profile(include_ids=[chosen.id])).entries == [chosen]
    assert not select(
        cv, Profile(include_ids=[chosen.id], exclude_ids=[chosen.id])
    ).entries
    with pytest.raises(CVError, match="IDs desconhecidos"):
        select(cv, Profile(exclude_ids=["publications.books:inexistente"]))


def test_profile_and_cli_overrides_preserve_nested_filters(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text(
        "include: [education, publications]\nsection_years:\n  publications: {since: 2020}\nlanguage: pt\n",
        encoding="utf-8",
    )
    profile = load_profile(path, {"language": "en", "theme": None})
    assert profile.language == "en"
    assert profile.section_years == {"publications": {"since": 2020}}
    assert profile.include == ["education", "publications"]


@pytest.mark.parametrize(
    "text",
    [
        "include: publications",
        "include: [publicatons]",
        "ful: true",
        "since: true",
        "since: 2025\nuntil: 2020",
        "full: true\nexclude: [education]",
        "language: pt\nlanguage: en",
        "include: &items [education]\norder: *items",
        "theme: ../theme",
        "hide_fields: [NOME-COMPLETO]",
        "[]",
        "section_years: {education: 2020}",
    ],
)
def test_invalid_profiles_do_not_silently_change_selection(tmp_path, text):
    path = tmp_path / "profile.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(CVError):
        load_profile(path)
