"""Select diagnostics for records without losing file-wide problems."""

from lattes2pdf.models import Curriculum, Entry, Issue


def issue_owner(cv: Curriculum, issue: Issue) -> Entry | None:
    # Nested projects and appointments own their diagnostics, not the profile
    # or activity that contains them. The slash also distinguishes [1] from [10].
    return max(
        (
            entry
            for entry in cv.entries
            if issue.path == entry.path or issue.path.startswith(entry.path + "/")
        ),
        key=lambda entry: len(entry.path),
        default=None,
    )


def relevant_issues(
    cv: Curriculum, entries: list[Entry], issues: list[Issue]
) -> list[Issue]:
    selected = {entry.id for entry in entries}
    sections = {entry.section for entry in entries}
    all_sections = {entry.section for entry in cv.entries}
    result = []
    for issue in issues:
        owner = issue_owner(cv, issue)
        if owner and owner.id not in selected:
            continue
        if not owner and issue.path in all_sections and issue.path not in sections:
            continue
        result.append(issue)
    return result
