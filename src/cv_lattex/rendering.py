"""RenderCV YAML data with explicit accounting for exported and omitted fields."""

import re
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from urllib.parse import urlsplit

from cv_lattex.lattes import YEAR_NAMES
from cv_lattex.models import Curriculum, CVError, Entry, Issue, SourceField, catalog
from cv_lattex.selection import Profile, Selection, hidden, select, visible_fields

DEGREE_NAMES = {
    "GRADUACAO": "Graduação",
    "ESPECIALIZACAO": "Especialização",
    "POS-DOUTORADO": "Pós-doutorado",
    "LIVRE-DOCENCIA": "Livre-docência",
    "CURSO-TECNICO-PROFISSIONALIZANTE": "Curso técnico profissionalizante",
    "MESTRADO-PROFISSIONALIZANTE": "Mestrado profissional",
    "ENSINO-FUNDAMENTAL-PRIMEIRO-GRAU": "Ensino fundamental",
    "ENSINO-MEDIO-SEGUNDO-GRAU": "Ensino médio",
    "RESIDENCIA-MEDICA": "Residência médica",
    "APERFEICOAMENTO": "Aperfeiçoamento",
    "FORMACAO-COMPLEMENTAR-DE-EXTENSAO-UNIVERSITARIA": "Extensão universitária",
    "FORMACAO-COMPLEMENTAR-CURSO-DE-CURTA-DURACAO": "Curso de curta duração",
    "MBA": "MBA",
}


def literal(text: str) -> str:
    """Encode punctuation as literal Typst text through RenderCV's Markdown parser.

    Markdown backslash escapes alone are restored after Typst escaping upstream.
    Unicode escapes contain no source-controlled code or Markdown delimiters.
    """

    if not re.search(r"[\\`*_{}\[\]#$!|<>&\n\r\t]", text):
        return text
    # One wrapper avoids upstream placeholder collisions at ten or more commands.
    characters = "".join(
        char if char.isalnum() or char == " " else f"\\u{{{ord(char):x}}}"
        for char in text
    )
    return f'#text("{characters}")'


def label(name: str) -> str:
    if name in DEGREE_NAMES:
        return DEGREE_NAMES[name]
    return (
        name.removesuffix("-INGLES")
        .removesuffix("-EN")
        .replace("-", " ")
        .replace("_", " ")
        .capitalize()
    )


def _url(value: str) -> bool:
    try:
        url = urlsplit(value)
        return (
            url.scheme in {"http", "https"}
            and bool(url.hostname)
            and not url.username
            and not url.password
            and len(value) <= 2083
            and not re.search(r'[\s"\\<>]', value)
        )
    except ValueError:
        return False


def _authors(entry: Entry, issues: list[Issue]) -> tuple[list[str], set[str]]:
    groups = defaultdict(list)
    for source in entry.fields:
        if source.tag == "AUTORES":
            groups[source.path.rsplit("/", 1)[0]].append(source)
    authors = []
    used = set()
    for path, sources in groups.items():
        name = next(
            (
                f
                for key in ("NOME-COMPLETO-DO-AUTOR", "NOME-PARA-CITACAO")
                for f in sources
                if f.name == key and f.text
            ),
            None,
        )
        if name:
            order = next((f.text for f in sources if f.name == "ORDEM-DE-AUTORIA"), "")
            authors.append(
                (int(order) if re.fullmatch(r"[1-9]\d{0,8}", order) else None, name)
            )
            used.add(name.path)
    orders = [order for order, _ in authors]
    if authors and (None in orders or len(set(orders)) != len(orders)):
        issues.append(
            Issue(
                "author-order",
                entry.path,
                "Ordem de autoria ausente ou ambígua; mantida a ordem do XML.",
            )
        )
    else:
        authors.sort(key=lambda pair: pair[0])
    return [name.text for _, name in authors], used


def _dates(entry: Entry, issues: list[Issue], language: str) -> tuple[dict, set[str]]:
    used = set()

    def partial(year_names, month_names):
        year = entry.find(*year_names)
        month = entry.find(*month_names)
        if not year:
            return None, set()
        if not re.fullmatch(r"[1-9]\d{3}", year.text):
            issues.append(
                Issue(
                    "invalid-date", year.path, "Data inválida preservada nos detalhes."
                )
            )
            return None, set()
        value = year.text
        sources = {year.path}
        if month:
            if re.fullmatch(r"\d{1,2}", month.text) and 1 <= int(month.text) <= 12:
                value += f"-{int(month.text):02d}"
                sources.add(month.path)
            else:
                issues.append(
                    Issue(
                        "invalid-date",
                        month.path,
                        "Mês inválido preservado nos detalhes.",
                    )
                )
        return value, sources

    start, start_fields = partial(("ANO-DE-INICIO", "ANO-INICIO"), ("MES-INICIO",))
    end, end_fields = partial(("ANO-DE-CONCLUSAO", "ANO-FIM"), ("MES-FIM",))
    state = entry.find("STATUS-DO-CURSO", "FLAG-PERIODO", "SITUACAO")
    ongoing = state and state.text in {"EM_ANDAMENTO", "EM ANDAMENTO", "ATUAL"}
    if (
        start
        and end
        and start[:4] > end[:4]
        or (start and end and len(start) == len(end) and start > end)
    ):
        issues.append(
            Issue(
                "reversed-dates",
                entry.path,
                "Intervalo invertido preservado nos detalhes.",
            )
        )
        return {}, used
    if start and (end or ongoing):
        used = start_fields | end_fields
        # RenderCV treats string years as January, while integer years stay imprecise.
        return {
            "start_date": int(start) if len(start) == 4 else start,
            "end_date": (int(end) if len(end) == 4 else end) if end else "present",
        }, used
    if start:
        # A lone start_date implicitly means "present" in RenderCV.
        prefix = "Início" if language == "pt" else "Start"
        return {"date": f"{prefix}: {start}"}, start_fields
    if end:
        prefix = "Conclusão" if language == "pt" else "End"
        return {"date": f"{prefix}: {end}"}, end_fields
    year = entry.find(*YEAR_NAMES)
    if year and re.fullmatch(r"[1-9]\d{3}", year.text):
        return {"date": int(year.text)}, {year.path}
    return {}, used


def _entry_kind(entry: Entry, authors: list[str]) -> str:
    kind = catalog()["sections"][entry.section]["kind"]
    title = entry.title_field()
    institution = entry.find("NOME-INSTITUICAO", "NOME-INSTITUICAO-EMPRESA")
    if kind in {"education", "experience"} and not (title and institution):
        return "normal"
    if kind == "publication" and not (title and authors):
        return "normal"
    return kind


def _details(entry: Entry, used: set[str]) -> list[str]:
    details = []
    for source in entry.fields:
        if source.disposition != "content" or source.path in used or not source.text:
            continue
        # Repeated children need context so a project member is not confused with its author.
        tag = source.path.rsplit("/", 1)[0].rsplit("/", 1)[-1]
        name = label(source.name) if source.name != "#text" else label(source.tag)
        if source.path.rsplit("/", 1)[0] != entry.path and not source.tag.startswith(
            ("DADOS-BASICOS", "DETALHAMENTO")
        ):
            name = f"{label(tag)} — {name}"
        details.append(f"{literal(name)}: {literal(source.text)}")
        used.add(source.path)
    return details


def _render_entry(
    entry: Entry,
    kind: str,
    authors: list[str],
    author_fields: set[str],
    profile: Profile,
    issues: list[Issue],
) -> tuple[dict, set[str]]:
    used = set()
    title = entry.title_field(profile.language)
    name = literal(title.text) if title else label(entry.tag)
    if title:
        used.add(title.path)
    result = {"name": name}
    if (
        kind == "normal"
        and title
        and len(catalog()["sections"][entry.section]["tags"]) > 1
    ):
        result["name"] = f"{label(entry.tag)} — {name}"
    institution = entry.find("NOME-INSTITUICAO", "NOME-INSTITUICAO-EMPRESA")
    if kind == "education":
        result = {
            "institution": literal(institution.text),
            "area": name,
            "degree": label(entry.tag),
        }
        used.add(institution.path)
    elif kind == "experience":
        result = {"company": literal(institution.text), "position": name}
        used.add(institution.path)
    elif kind == "publication":
        result = {"title": name, "authors": [literal(author) for author in authors]}
        used.update(author_fields)
        journal = entry.find(
            "TITULO-DO-PERIODICO-OU-REVISTA",
            "NOME-DO-EVENTO",
            "TITULO-DO-JORNAL-OU-REVISTA",
        )
        if journal:
            result["journal"] = literal(journal.text)
            used.add(journal.path)
        doi = entry.find("DOI")
        if doi:
            value = doi.text.removeprefix("https://doi.org/").removeprefix(
                "http://doi.org/"
            )
            if re.fullmatch(r"10\.\d{4,9}/[^\s\"<>\\]+", value):
                result["doi"] = value
                used.add(doi.path)
            else:
                issues.append(
                    Issue(
                        "invalid-doi", doi.path, "DOI inválido preservado nos detalhes."
                    )
                )
        url = entry.find("HOME-PAGE-DO-TRABALHO", "HOME-PAGE")
        if url and not result.get("doi"):
            if _url(url.text):
                result["url"] = url.text
                used.add(url.path)
            else:
                issues.append(
                    Issue(
                        "invalid-url", url.path, "URL inválida preservada nos detalhes."
                    )
                )
    if kind != "publication" and authors:
        result["summary"] = literal(
            ("Autores: " if profile.language == "pt" else "Authors: ")
            + "; ".join(authors)
        )
        used.update(author_fields)
    dates, date_fields = _dates(entry, issues, profile.language)
    if kind == "publication" and "start_date" in dates:
        result["date"] = f"{dates['start_date']} – {dates['end_date']}"
    else:
        result.update(dates)
    used.update(date_fields)
    if "details" not in profile.hide_fields:
        details = _details(entry, used)
        if details:
            if kind == "publication":
                # Blank lines terminate RenderCV's Markdown summary block prematurely.
                result["summary"] = "\n".join(details)
            else:
                result["highlights"] = details
    return result, used


def _profile(
    entry: Entry, output: dict, profile: Profile, issues: list[Issue]
) -> set[str]:
    used = set()
    name = entry.find("NOME-COMPLETO")
    if name:
        used.add(name.path)
    for key, names in {
        "email": ("E-MAIL", "ELETRONICO"),
        "website": ("HOME-PAGE",),
    }.items():
        source = entry.find(*names)
        if source:
            valid = (
                _url(source.text)
                if key == "website"
                else bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", source.text))
            )
            if valid:
                output[key] = source.text
                used.add(source.path)
            else:
                issues.append(
                    Issue(
                        "invalid-contact",
                        source.path,
                        "Contato inválido preservado nos detalhes.",
                    )
                )
    summary = entry.find("TEXTO-RESUMO-CV-RH", language=profile.language)
    sections = output["sections"]
    content = []
    if summary:
        content.append(literal(summary.text))
        used.add(summary.path)
    if "details" not in profile.hide_fields:
        content.extend(_details(entry, used))
    if content:
        sections[catalog()["sections"]["profile"][profile.language]] = content
    return used


def _report(
    cv: Curriculum,
    selection: Selection,
    visible: dict[str, list[SourceField]],
    used: set[str],
    issues: list[Issue],
    profile: Profile,
) -> dict:
    owners = defaultdict(set)
    for entry in cv.entries:
        for source in entry.fields:
            owners[source.path].add(entry.id)
    selected_ids = {entry.id for entry in selection.entries}
    visible_paths = {source.path for sources in visible.values() for source in sources}
    records = []
    for source in cv.fields:
        status = source.disposition
        reason = None
        if source.path in used and status == "private":
            status = "exported"
            reason = "explicit-selection"
        elif status in {"content", "unknown"}:
            if source.path in used:
                status = "exported"
            elif owners[source.path] and not owners[source.path] & selected_ids:
                status = "excluded"
                reason = "entry-filter"
            elif status == "content":
                if not source.text:
                    status = "empty"
                elif (
                    source.path in visible_paths
                    and "details" not in profile.hide_fields
                ):
                    status = "unmapped"
                elif owners[source.path]:
                    status = "excluded"
                    if hidden(source, profile):
                        reason = "field-filter"
                    elif source.path not in visible_paths:
                        reason = "language"
                    else:
                        reason = "details"
                else:
                    status = "unmapped"
        record = {"path": source.path, "status": status}
        if reason:
            record["reason"] = reason
        records.append(record)
    counts = dict(Counter(record["status"] for record in records))
    return {
        "format_version": 1,
        "full_requested": profile.full,
        "counts": counts,
        "entries": [
            {
                "id": entry.id,
                "section": entry.section,
                "status": "excluded" if entry.id in selection.excluded else "selected",
                "reason": selection.excluded.get(entry.id),
            }
            for entry in cv.entries
        ],
        "fields": records,
        "issues": [asdict(issue) for issue in issues],
    }


def export_data(cv: Curriculum, profile: Profile) -> tuple[dict, dict]:
    selection = select(cv, profile)
    issues = cv.issues + selection.issues
    output = {"name": literal(cv.name), "sections": {}}
    name_field = next(entry for entry in cv.entries if entry.section == "profile").find(
        "NOME-COMPLETO"
    )
    used = {name_field.path}
    visible = {entry.id: visible_fields(entry, profile) for entry in selection.entries}
    groups = defaultdict(list)
    for entry in selection.entries:
        sources = visible[entry.id]
        if not sources:
            continue
        # Administrative author order participates in rendering but is never displayed.
        order = [f for f in entry.fields if f.name == "ORDEM-DE-AUTORIA"]
        view = replace(entry, fields=sources + order)
        if entry.section == "profile":
            used.update(_profile(view, output, profile, issues))
        else:
            groups[entry.section].append(view)
    for section, entries in groups.items():
        author_lists = [_authors(entry, issues) for entry in entries]
        kinds = {
            _entry_kind(entry, authors[0])
            for entry, authors in zip(entries, author_lists)
        }
        kind = next(iter(kinds)) if len(kinds) == 1 else "normal"
        if kind == "normal" and catalog()["sections"][section]["kind"] != "normal":
            issues.append(
                Issue(
                    "generic-layout",
                    section,
                    "Seção usa entradas genéricas para preservar registros incompletos ou campos ocultos.",
                )
            )
        rendered = []
        for entry, (authors, author_fields) in zip(entries, author_lists):
            result, consumed = _render_entry(
                entry, kind, authors, author_fields, profile, issues
            )
            rendered.append(result)
            used.update(consumed)
        output["sections"][catalog()["sections"][section][profile.language]] = rendered
    # Honor profile order including the profile section itself.
    labels = [
        catalog()["sections"][entry.section][profile.language]
        for entry in selection.entries
    ]
    output["sections"] = {
        name: output["sections"][name]
        for name in dict.fromkeys(labels)
        if name in output["sections"]
    }
    report = _report(cv, selection, visible, used, issues, profile)
    unmapped = report["counts"].get("unknown", 0) + report["counts"].get("unmapped", 0)
    if profile.full and unmapped and not profile.allow_unmapped:
        raise CVError(
            f"Modo completo bloqueado: {unmapped} campos/elementos não mapeados. "
            "Consulte inspect --json; use --allow-unmapped para aceitar as omissões registradas no relatório."
        )
    data = {
        "cv": output,
        "design": {
            "theme": profile.theme,
            "page": {"size": "a4", "show_top_note": False},
            "entries": {"allow_page_break": True},
            "templates": {"education_entry": {"degree_column": None}},
        },
        "locale": {"language": "portuguese" if profile.language == "pt" else "english"},
    }
    education_template = data["design"]["templates"]["education_entry"]
    if profile.theme == "classic":
        # Full degree names cannot fit the theme's narrow abbreviation column.
        education_template["main_column"] = (
            "**INSTITUTION**\nDEGREE_WITH_AREA\nSUMMARY\nHIGHLIGHTS"
        )
    elif profile.theme == "sb2nov":
        education_template["main_column"] = (
            "**INSTITUTION**\n*DEGREE_WITH_AREA*\nSUMMARY\nHIGHLIGHTS"
        )
    return data, report
