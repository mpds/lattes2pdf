"""Scoped production years and professional intervals, without changing record IDs."""

import re
from collections import defaultdict

from lattes2pdf.categories import CATEGORIES
from lattes2pdf.models import Entry, SourceField

DATE_FIELDS = {"ANO-INICIO", "MES-INICIO", "ANO-FIM", "MES-FIM", "FLAG-PERIODO"}


def period_group(entry: Entry) -> str | None:
    if CATEGORIES["lattes.atuacao"].matches(entry):
        return "professional"
    if (
        entry.section.startswith(("publications.", "technical."))
        and entry.section != "technical.events"
        or entry.section == "artistic"
    ):
        return "production"
    return None


def date_index(fields: list[SourceField]) -> dict[str, dict[str, str]]:
    result = defaultdict(dict)
    for source in fields:
        if source.name in DATE_FIELDS and source.disposition == "content":
            result[source.path.rsplit("/", 1)[0]][source.name] = source.text
    return result


def professional_dates(
    entry: Entry, index: dict[str, dict[str, str]]
) -> dict[str, str]:
    # Research lines inherit the period of their enclosing research activity,
    # never the dates of another employment record at the same institution.
    path = entry.path
    while path:
        if path in index:
            return index[path]
        if entry.section != "research.lines":
            break
        path = path.rsplit("/", 1)[0]
    return {}


def ongoing_employment(entry: Entry) -> bool:
    """Lattes employment records have no status flag: a missing end means current."""
    values = {f.name: f.text for f in entry.fields if f.tag == "VINCULOS"}
    return (
        entry.tag == "VINCULOS"
        and bool(re.fullmatch(r"[1-9]\d{3}", values.get("ANO-INICIO", "")))
        and not values.get("ANO-FIM")
        and not values.get("MES-FIM")
    )


def professional_overlap(
    entry: Entry, values: dict[str, str], since: int | None, until: int | None
) -> bool | None:
    """Return None when the available dates cannot establish overlap or exclusion."""
    for key, value in values.items():
        if not value or key == "FLAG-PERIODO":
            continue
        if key.startswith("ANO") and not re.fullmatch(r"[1-9]\d{3}", value):
            return None
        if key.startswith("MES") and (
            not re.fullmatch(r"\d{1,2}", value) or not 1 <= int(value) <= 12
        ):
            return None
    start = int(values["ANO-INICIO"]) if values.get("ANO-INICIO") else None
    end = int(values["ANO-FIM"]) if values.get("ANO-FIM") else None
    if (
        values.get("MES-INICIO")
        and start is None
        or values.get("MES-FIM")
        and end is None
    ):
        return None
    if start is not None and end is not None:
        if (
            start > end
            or start == end
            and values.get("MES-INICIO")
            and values.get("MES-FIM")
            and int(values["MES-INICIO"]) > int(values["MES-FIM"])
        ):
            return None
    if (
        since is not None
        and end is not None
        and end < since
        or until is not None
        and start is not None
        and start > until
    ):
        return False
    if any(
        year is not None
        and (since is None or year >= since)
        and (until is None or year <= until)
        for year in (start, end)
    ):
        return True
    ongoing = (
        end is None
        and not values.get("MES-FIM")
        and (entry.tag == "VINCULOS" or values.get("FLAG-PERIODO") == "ATUAL")
    )
    if start is not None and (end is not None or ongoing):
        return True
    return None
