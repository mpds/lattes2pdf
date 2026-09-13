"""RenderCV YAML data with explicit accounting for exported and omitted fields."""

import re
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import datetime
from urllib.parse import quote, urlsplit

from lattes2pdf.categories import (
    CATEGORIES,
    category_names,
    matches_prefix,
    matches_selector,
    presentation_category,
    presentation_section,
)
from lattes2pdf.lattes import YEAR_NAMES
from lattes2pdf.models import Curriculum, CVError, Entry, Issue, SourceField, catalog
from lattes2pdf.sections import SECTION_OPTIONS
from lattes2pdf.selection import Profile, Selection, hidden, select, visible_fields
from lattes2pdf.theme import load_theme

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


def _author_groups(entry: Entry) -> dict[str, list[SourceField]]:
    groups = defaultdict(list)
    for source in entry.fields:
        if source.tag == "AUTORES":
            groups[source.path.rsplit("/", 1)[0]].append(source)
    return groups


def _self_author(entry: Entry, owner_id: str, owner_name: str) -> str | None:
    """Match original metadata before filtering or changing the displayed spelling."""
    id_matches, name_matches = [], []
    for path, sources in _author_groups(entry).items():
        attributes = {source.name: source.text for source in sources}
        author_id = attributes.get("NRO-ID-CNPQ", "")
        if owner_id and author_id:
            if owner_id == author_id:
                id_matches.append(path)
        elif attributes.get("NOME-COMPLETO-DO-AUTOR") == owner_name:
            name_matches.append(path)
    # An explicit ID takes precedence over names, including a conflicting ID.
    matches = id_matches or name_matches
    return matches[0] if len(matches) == 1 else None


def _authors(
    entry: Entry, issues: list[Issue], profile: Profile, self_path: str | None
) -> tuple[list[str], set[str]]:
    """Return safely formatted names in the declared authorship order."""
    authors = []
    used = set()
    name_fields = ("NOME-COMPLETO-DO-AUTOR", "NOME-PARA-CITACAO")
    if profile.authors.get("use_informed_citation", not profile.full):
        name_fields = tuple(reversed(name_fields))
    for path, sources in _author_groups(entry).items():
        name = next(
            (f for key in name_fields for f in sources if f.name == key and f.text),
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
    abbreviate = profile.authors.get("et_al", False) and len(authors) > 3
    if abbreviate:
        authors = authors[:1]
        used = {name.path for _, name in authors}
    formatted = []
    name_case = profile.authors.get("name_case", "original")
    for _, name in authors:
        display = name.text
        if name_case == "upper":
            display = display.upper()
        elif name_case == "title":
            display = display.title()
        display = literal(display)
        if self_path == name.path.rsplit("/", 1)[0]:
            display = f"**{display}**"
        formatted.append(display)
    if abbreviate:
        formatted[0] += " et al."
    return formatted, used


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


def _institution_details(
    cv: Curriculum, profile: Profile
) -> dict[str, dict[str, SourceField]]:
    """Index auxiliary institution metadata without adding records or changing IDs."""
    groups = defaultdict(dict)
    for source in cv.fields:
        if (
            source.tag == "INFORMACAO-ADICIONAL-INSTITUICAO"
            and source.disposition == "administrative"
            and source.text
            and not hidden(source, profile)
        ):
            groups[source.path.rsplit("/", 1)[0]][source.name] = source
    return {
        fields["CODIGO-INSTITUICAO"].text: fields
        for fields in groups.values()
        if "CODIGO-INSTITUICAO" in fields
    }


def _scholarship(
    entry: Entry, institutions: dict[str, dict[str, SourceField]], language: str
) -> tuple[str, set[str]]:
    scholarship = entry.find("FLAG-BOLSA")
    if not scholarship or scholarship.text != "SIM":
        return "", set()
    used = {scholarship.path}
    prefix = "Bolsista" if language == "pt" else "Scholarship holder"
    agency = entry.find("NOME-AGENCIA")
    if not agency:
        return prefix, used
    used.add(agency.path)
    parts = [agency.text]
    code = entry.find("CODIGO-AGENCIA-FINANCIADORA")
    institution = institutions.get(code.text, {}) if code else {}
    for name in ("SIGLA-INSTITUICAO", "NOME-PAIS-INSTITUICAO"):
        source = institution.get(name)
        if source:
            # The registered agency name may already contain its acronym or country.
            if not re.search(
                rf"(?<!\w){re.escape(source.text)}(?!\w)",
                ", ".join(parts),
                re.IGNORECASE,
            ):
                parts.append(source.text)
            used.add(source.path)
    return prefix + ": " + ", ".join(parts), used


def _render_education(
    entry: Entry,
    kind: str,
    profile: Profile,
    issues: list[Issue],
    institutions: dict[str, dict[str, SourceField]],
) -> tuple[dict, set[str]]:
    """Present education without copying leftover registration fields into the CV."""
    used = set()

    def take(*names):
        source = entry.find(*names, language=profile.language)
        if source:
            used.add(source.path)
            return source.text
        return ""

    course = take("NOME-CURSO", "NOME-DO-CURSO")
    institution = take("NOME-INSTITUICAO", "NOME-INSTITUICAO-EMPRESA")
    degree = label(entry.tag)
    lines = []
    if kind == "education":
        result = {
            "institution": literal(institution),
            "area": literal(course),
            "degree": degree,
        }
    else:
        connector = " em " if profile.language == "pt" else " in "
        result = {"name": literal(degree + (connector + course if course else ""))}
        if institution:
            lines.append(institution)

    dates, date_fields = _dates(entry, issues, profile.language)
    result.update(dates)
    used.update(date_fields)
    state = entry.find("STATUS-DO-CURSO", "STATUS-DO-ESTAGIO")
    if state:
        states = {
            "CONCLUIDO": ("Concluído", "Completed"),
            "EM_ANDAMENTO": ("Em andamento", "In progress"),
            "INCOMPLETO": ("Incompleto", "Incomplete"),
        }
        has_end_year = any(
            source.name in {"ANO-DE-CONCLUSAO", "ANO-FIM"}
            and source.path in date_fields
            for source in entry.fields
        )
        if state.text == "EM_ANDAMENTO" and dates.get("end_date") == "present":
            used.add(state.path)  # The status is represented by the open date range.
        elif not (state.text == "CONCLUIDO" and has_end_year):
            lines.append(
                states.get(state.text, (state.text, state.text))[
                    profile.language == "en"
                ]
            )
            used.add(state.path)

    if profile.section_option("education", "show_thesis"):
        thesis = take(
            "TITULO-DO-TRABALHO-DE-CONCLUSAO-DE-CURSO",
            "TITULO-DA-MONOGRAFIA",
            "TITULO-DA-DISSERTACAO-TESE",
            "TITULO-DA-RESIDENCIA-MEDICA",
            "TITULO-DO-TRABALHO",
        )
        if thesis:
            prefix = "Título" if profile.language == "pt" else "Title"
            lines.append(f"{prefix}: {thesis}")
    if profile.section_option("education", "show_advisors"):
        for names, labels in (
            (
                (
                    "NOME-COMPLETO-DO-ORIENTADOR",
                    "NOME-DO-ORIENTADOR",
                    "NOME-ORIENTADOR-GRAD",
                    "NOME-ORIENTADOR-DOUT",
                ),
                ("Orientação", "Advisor"),
            ),
            (("NOME-DO-CO-ORIENTADOR",), ("Coorientação", "Co-advisor")),
            (
                ("NOME-DO-ORIENTADOR-CO-TUTELA",),
                ("Orientação em cotutela", "Joint supervision"),
            ),
            (
                ("NOME-DO-ORIENTADOR-SANDUICHE",),
                ("Orientação no período sanduíche", "Visiting-period advisor"),
            ),
        ):
            advisor = take(*names)
            if advisor:
                lines.append(f"{labels[profile.language == 'en']}: {advisor}")
    if profile.section_option("education", "show_scholarship"):
        scholarship, scholarship_fields = _scholarship(
            entry, institutions, profile.language
        )
        if scholarship:
            lines.append(scholarship)
            used.update(scholarship_fields)
    if lines:
        result["summary"] = "\n".join(literal(line) for line in lines)
    return result, used


def _publication_links(entry: Entry, issues: list[Issue]) -> tuple[dict, set[str]]:
    result = {}
    used = set()
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
                Issue("invalid-doi", doi.path, "DOI inválido preservado nos detalhes.")
            )
    url = entry.find("HOME-PAGE-DO-TRABALHO", "HOME-PAGE")
    if url and not result.get("doi"):
        if _url(url.text):
            result["url"] = url.text
            used.add(url.path)
        else:
            issues.append(
                Issue("invalid-url", url.path, "URL inválida preservada nos detalhes.")
            )
    return result, used


def _render_article(
    entry: Entry,
    authors: list[str],
    author_fields: set[str],
    profile: Profile,
    issues: list[Issue],
) -> tuple[dict, set[str]]:
    """Present published articles, including records with missing bibliographic data."""
    used = set(author_fields)

    def take(name):
        source = entry.find(name, language=profile.language)
        if source:
            used.add(source.path)
            return source.text
        return ""

    title = take("TITULO-DO-ARTIGO")
    fallback = "Artigo publicado" if profile.language == "pt" else "Published article"
    result = {
        "title": literal(title or fallback),
        "authors": authors,
    }
    year = take("ANO-DO-ARTIGO")
    if year:
        if re.fullmatch(r"[1-9]\d{3}", year):
            result["date"] = int(year)
        else:
            result["date"] = literal(year)
            issues.append(
                Issue(
                    "invalid-date",
                    entry.find("ANO-DO-ARTIGO").path,
                    "Ano do artigo inválido; exibido como texto.",
                )
            )

    journal = take("TITULO-DO-PERIODICO-OU-REVISTA")
    citation = [journal] if journal else []
    if (
        profile.section_option(entry.section, "show_details")
        and "details" not in profile.hide_fields
    ):
        for name, prefix in (
            ("VOLUME", "v."),
            ("FASCICULO", "n." if profile.language == "pt" else "no."),
            ("SERIE", "série" if profile.language == "pt" else "series"),
        ):
            value = take(name)
            if value:
                citation.append(f"{prefix} {value}")
        first, last = take("PAGINA-INICIAL"), take("PAGINA-FINAL")
        if first:
            pages = f"{first}-{last}" if last and last != first else first
            citation.append(f"p. {pages}")
        elif last:
            prefix = "p. final" if profile.language == "pt" else "p. ending at"
            citation.append(f"{prefix} {last}")
    if citation:
        result["journal"] = literal(", ".join(citation))

    if profile.section_option(entry.section, "show_links"):
        links, link_fields = _publication_links(entry, issues)
        result.update(links)
        used.update(link_fields)
        invalid = []
        # Invalid identifiers remain visible as text, never as clickable links.
        for name, prefix in (("DOI", "DOI"), ("HOME-PAGE-DO-TRABALHO", "URL")):
            source = entry.find(name)
            if name == "HOME-PAGE-DO-TRABALHO" and "doi" in links:
                continue
            if source and source.path not in link_fields:
                invalid.append(literal(f"{prefix}: {source.text}"))
                used.add(source.path)
        if invalid:
            result["summary"] = "\n".join(invalid)
    return result, used


def _term(value: str, language: str) -> str:
    """Translate documented categorical values, retaining unrecognized source text."""
    terms = {
        "MESTRADO": ("Mestrado", "Master's"),
        "DOUTORADO": ("Doutorado", "Doctorate"),
        "POS_DOUTORADO": ("Pós-doutorado", "Postdoctoral"),
        "GRADUACAO": ("Graduação", "Undergraduate"),
        "INICIACAO_CIENTIFICA": ("Iniciação científica", "Undergraduate research"),
        "APERFEICOAMENTO_ESPECIALIZACAO": (
            "Aperfeiçoamento/especialização",
            "Specialization",
        ),
        "MONOGRAFIA_DE_CONCLUSAO_DE_CURSO_APERFEICOAMENTO_E_ESPECIALIZACAO": (
            "Aperfeiçoamento/especialização",
            "Specialization",
        ),
        "TRABALHO_DE_CONCLUSAO_DE_CURSO_GRADUACAO": ("Graduação", "Undergraduate"),
        "ORIENTACAO_DE_OUTRA_NATUREZA": ("Outra natureza", "Other supervision"),
        "ORIENTADOR_PRINCIPAL": ("Orientação", "Supervision"),
        "ORIENTADOR": ("Orientação", "Supervision"),
        "CO_ORIENTADOR": ("Coorientação", "Co-supervision"),
        "CONGRESSO": ("Congresso", "Congress"),
        "FEIRA": ("Feira", "Fair"),
        "SEMINARIO": ("Seminário", "Seminar"),
        "SIMPOSIO": ("Simpósio", "Symposium"),
        "OFICINA": ("Oficina", "Workshop"),
        "ENCONTRO": ("Encontro", "Meeting"),
        "EXPOSICAO": ("Exposição", "Exhibition"),
        "OLIMPIADA": ("Olimpíada", "Olympiad"),
        "ORGANIZACAO": ("Organização", "Organization"),
        "ENTREVISTA": ("Entrevista", "Interview"),
        "COMENTARIO": ("Comentário", "Commentary"),
        "REDE_SOCIAL": ("Rede social", "Social network"),
        "OUTRO": ("Outro", "Other"),
        "OUTRA": ("Outra", "Other"),
        "BEM": ("bem", "well"),
        "RAZOAVELMENTE": ("razoavelmente", "reasonably"),
        "POUCO": ("pouco", "a little"),
    }
    terms.update(
        {pair[0].upper().replace("-", "_"): pair for pair in list(terms.values())}
    )
    return terms.get(value.upper().replace("-", "_"), (value, value))[language == "en"]


def _render_context(
    entry: Entry,
    authors: list[str],
    author_fields: set[str],
    profile: Profile,
    issues: list[Issue],
) -> tuple[dict, set[str]]:
    """Keep each section's useful context independent of generic leftover details."""
    used = set()
    english = profile.language == "en"

    def take(*names):
        source = entry.find(*names, language=profile.language)
        if source:
            used.add(source.path)
            return source.text
        return ""

    def option(name):
        return profile.section_option(entry.section, name)

    title = entry.title_field(profile.language)
    name = title.text if title else ""
    if title:
        used.add(title.path)
    lines = []
    description = ""
    if entry.section.startswith("supervision."):
        level = next(
            (
                entry.tag.removeprefix(prefix)
                for prefix in (
                    "ORIENTACOES-CONCLUIDAS-PARA-",
                    "ORIENTACAO-EM-ANDAMENTO-DE-",
                )
                if entry.tag.startswith(prefix)
            ),
            "",
        )
        level = _term(level or take("NATUREZA"), profile.language)
        student = (
            take("NOME-DO-ORIENTADO", "NOME-DO-ORIENTANDO")
            if option("show_students")
            else ""
        )
        lines.append(": ".join(value for value in (level, student) if value))
        if option("show_institution"):
            institution = take("NOME-DA-INSTITUICAO", "NOME-INSTITUICAO")
            course = take("NOME-DO-CURSO", "NOME-CURSO")
            lines.append(", ".join(value for value in (institution, course) if value))
        role = take("TIPO-DE-ORIENTACAO", "TIPO-DE-ORIENTACAO-CONCLUIDA")
        if role:
            lines.append(_term(role, profile.language))
        name = name or (
            "Supervision without a work title"
            if english
            else "Orientação sem título de trabalho"
        )
    elif entry.section == "awards":
        if option("show_institution"):
            lines.append(take("NOME-DA-ENTIDADE-PROMOTORA"))
    elif entry.section.startswith("activities."):
        if option("show_institution"):
            context = [
                take("NOME-INSTITUICAO"),
                take("NOME-ORGAO"),
                take("NOME-UNIDADE"),
            ]
            lines.append(", ".join(dict.fromkeys(value for value in context if value)))
    elif entry.section == "research.projects":
        lines.append(take("NOME-INSTITUICAO"))
        if option("show_members"):
            members = []
            groups = defaultdict(list)
            for source in entry.fields:
                if source.tag == "INTEGRANTES-DO-PROJETO":
                    groups[source.path.rsplit("/", 1)[0]].append(source)
            for sources in groups.values():
                member = next(
                    (
                        f
                        for key in ("NOME-COMPLETO", "NOME-PARA-CITACAO")
                        for f in sources
                        if f.name == key and f.text
                    ),
                    None,
                )
                if member:
                    display = member.text
                    used.add(member.path)
                    responsible = next(
                        (
                            f
                            for f in sources
                            if f.name == "FLAG-RESPONSAVEL" and f.text == "SIM"
                        ),
                        None,
                    )
                    if responsible:
                        display += " (responsible)" if english else " (responsável)"
                        used.add(responsible.path)
                    members.append(display)
            if members:
                lines.append(
                    ("Members: " if english else "Integrantes: ") + ", ".join(members)
                )
        if option("show_description"):
            description = take("DESCRICAO-DO-PROJETO")
    elif entry.section == "languages":
        if option("show_proficiency"):
            skills = []
            for suffix, labels in (
                ("LEITURA", ("Leitura", "Reading")),
                ("FALA", ("Fala", "Speaking")),
                ("ESCRITA", ("Escrita", "Writing")),
                ("COMPREENSAO", ("Compreensão", "Understanding")),
            ):
                source = entry.find("PROFICIENCIA-DE-" + suffix)
                if source and source.text != "NAO_INFORMADO":
                    value = take(source.name)
                    skills.append(
                        f"{labels[english]}: {_term(value, profile.language)}"
                    )
            lines.append("; ".join(skills))
    elif entry.section == "events":
        event = take("NOME-DO-EVENTO")
        if name and event and event != name:
            lines.append(event)
        name = (
            name
            or event
            or ("Unnamed event" if english else "Evento sem nome informado")
        )
        if option("show_event_type"):
            nature = take("NATUREZA")
            if not nature and entry.tag.startswith("PARTICIPACAO-EM-"):
                nature = entry.tag.removeprefix("PARTICIPACAO-EM-")
            participation = take("TIPO-PARTICIPACAO")
            lines.append(
                "; ".join(
                    _term(value, profile.language)
                    for value in (nature, participation)
                    if value
                )
            )
    elif entry.section == "technical.events":
        lines.append(take("INSTITUICAO-PROMOTORA"))
        nature = take("NATUREZA")
        lines.append(
            "; ".join(
                _term(value, profile.language)
                for value in (nature if nature != "ORGANIZACAO" else "", take("TIPO"))
                if value
            )
        )
    elif entry.section == "technical.broadcasts":
        lines.append(take("EMISSORA", "VEICULO-DE-DIVULGACAO"))
        lines.append(_term(take("NATUREZA"), profile.language))

    result = {"name": literal(name or label(entry.tag))}
    if description:
        prefix = "Description" if english else "Descrição"
        result["description"] = literal(f"{prefix}: {description}")
    dates, date_fields = _dates(entry, issues, profile.language)
    result.update(dates)
    used.update(date_fields)
    formatted = [literal(line) for line in lines if line]
    if entry.section.startswith("technical.") and authors:
        formatted.append(("Authors: " if english else "Autores: ") + ", ".join(authors))
        used.update(author_fields)
    if "show_links" in SECTION_OPTIONS[entry.section] and option("show_links"):
        links, link_fields = _publication_links(entry, issues)
        used.update(link_fields)
        url = "https://doi.org/" + links["doi"] if "doi" in links else links.get("url")
        if url:
            formatted.append(f"[Link]({quote(url, safe=':/?&=%#@+,-._~')})")
        elif source := entry.find("HOME-PAGE-DO-TRABALHO", "HOME-PAGE", "DOI"):
            formatted.append(literal(f"Link: {source.text}"))
            used.add(source.path)
    if formatted:
        result["summary"] = "\n".join(formatted)
    return result, used


def _header_link(entry: Entry, output: dict, profile: Profile) -> set[str]:
    """Move an explicitly selected digital-media link to the header without guessing ownership."""
    source = entry.find("HOME-PAGE")
    if not source:
        return set()
    if not _url(source.text):
        # The normal media entry will retain the invalid address as text.
        return set()
    title = entry.title_field(profile.language)
    output.setdefault("custom_connections", []).append(
        {
            "fontawesome_icon": "link",
            "placeholder": literal(title.text if title else "Link"),
            "url": source.text,
        }
    )
    return {source.path} | ({title.path} if title else set())


def _render_entry(
    entry: Entry,
    kind: str,
    authors: list[str],
    author_fields: set[str],
    profile: Profile,
    issues: list[Issue],
    institutions: dict[str, dict[str, SourceField]],
) -> tuple[dict, set[str]]:
    if entry.section == "education" and not profile.full:
        return _render_education(entry, kind, profile, issues, institutions)
    if entry.section == "publications.articles" and not profile.full:
        return _render_article(entry, authors, author_fields, profile, issues)
    if entry.section in SECTION_OPTIONS and not profile.full:
        return _render_context(entry, authors, author_fields, profile, issues)
    used = set()
    title = entry.title_field(profile.language)
    name = literal(title.text) if title else label(entry.tag)
    if title:
        used.add(title.path)
    book = (
        entry.find("TITULO-DO-LIVRO", language=profile.language)
        if entry.section == "publications.chapters"
        else None
    )
    result = {"name": name}
    if (
        kind == "normal"
        and title
        and len(catalog()["sections"][entry.section]["tags"]) > 1
    ):
        connector = " — "
        if entry.section == "training" and not profile.full:
            connector = " em " if profile.language == "pt" else " in "
        result["name"] = f"{label(entry.tag)}{connector}{name}"
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
    elif entry.section == "training" and institution and not profile.full:
        result["summary"] = literal(institution.text)
        used.add(institution.path)
    elif kind == "publication":
        result = {"title": name, "authors": authors}
        used.update(author_fields)
        journal = book or entry.find(
            "TITULO-DO-PERIODICO-OU-REVISTA",
            "NOME-DO-EVENTO",
            "TITULO-DO-JORNAL-OU-REVISTA",
        )
        if journal:
            result["journal"] = literal(journal.text)
            used.add(journal.path)
        links, link_fields = _publication_links(entry, issues)
        result.update(links)
        used.update(link_fields)
    if kind != "publication" and authors:
        result["summary"] = (
            "Autores: " if profile.language == "pt" else "Authors: "
        ) + ", ".join(authors)
        used.update(author_fields)
    dates, date_fields = _dates(entry, issues, profile.language)
    if kind == "publication" and "start_date" in dates:
        result["date"] = f"{dates['start_date']} – {dates['end_date']}"
    else:
        result.update(dates)
    used.update(date_fields)
    if book and kind != "publication":
        prefix = "Livro" if profile.language == "pt" else "Book"
        result["highlights"] = [literal(f"{prefix}: {book.text}")]
        used.add(book.path)
    if "details" not in profile.hide_fields:
        details = _details(entry, used)
        if details:
            if kind == "publication":
                # Blank lines terminate RenderCV's Markdown summary block prematurely.
                result["summary"] = "\n".join(details)
            else:
                result.setdefault("highlights", []).extend(details)
    return result, used


def _addresses(entry: Entry, profile: Profile) -> tuple[list[dict], set[str]]:
    entries, used = [], set()
    for tag, pt, en in (
        ("ENDERECO-PROFISSIONAL", "Endereço profissional", "Professional address"),
        ("ENDERECO-RESIDENCIAL", "Endereço residencial", "Residential address"),
        ("ENDERECO", "Endereço eletrônico", "Electronic address"),
    ):
        fields = [f for f in entry.fields if f.tag == tag and f.text]
        if not fields:
            continue
        highlights = []
        labels = {
            "E-MAIL": "E-mail",
            "ELETRONICO": "E-mail",
            "HOME-PAGE": "Website",
            "CEP": "CEP",
            "UF": "UF",
            "DDD": "DDD",
            "DDI": "DDI",
        }
        for source in fields:
            highlights.append(
                f"{literal(labels.get(source.name, label(source.name)))}: {literal(source.text)}"
            )
            used.add(source.path)
        entries.append(
            {"name": pt if profile.language == "pt" else en, "highlights": highlights}
        )
    return entries, used


def _birth_connection(
    entry: Entry, output: dict, profile: Profile, issues: list[Issue]
) -> set[str]:
    used = set()

    def take(name):
        source = entry.find(name)
        if source:
            used.add(source.path)
            return source.text
        return ""

    birth_date = take("DATA-NASCIMENTO")
    if birth_date:
        try:
            if not re.fullmatch(r"\d{8}", birth_date):
                raise ValueError
            date = datetime.strptime(birth_date, "%d%m%Y")
            birth_date = date.strftime(
                "%d/%m/%Y" if profile.language == "pt" else "%Y-%m-%d"
            )
        except ValueError:
            issues.append(
                Issue(
                    "invalid-date",
                    entry.find("DATA-NASCIMENTO").path,
                    "Data de nascimento inválida; exibida como texto original.",
                )
            )
    city, state, country = (
        take("CIDADE-NASCIMENTO"),
        take("UF-NASCIMENTO"),
        take("PAIS-DE-NASCIMENTO"),
    )
    place = ", ".join(
        p for p in ("/".join(p for p in (city, state) if p), country) if p
    )
    if birth_date or place:
        prefix = (
            ("Nascimento" if birth_date else "Naturalidade")
            if profile.language == "pt"
            else ("Born" if birth_date else "Place of birth")
        )
        output.setdefault("custom_connections", []).append(
            {
                "fontawesome_icon": "calendar-days" if birth_date else "location-dot",
                "placeholder": literal(
                    prefix + ": " + " — ".join(p for p in (birth_date, place) if p)
                ),
                "url": None,
            }
        )
    return used


def _profile(
    entry: Entry, output: dict, profile: Profile, issues: list[Issue]
) -> set[str]:
    used = set()
    name = entry.find("NOME-COMPLETO")
    if name:
        used.add(name.path)
    if not profile.full:
        used.update(_birth_connection(entry, output, profile, issues))
    sections = output["sections"]
    if profile.category_selection("lattes.endereco") is True:
        addresses, address_fields = _addresses(entry, profile)
        if addresses:
            title = literal(profile.section_title("lattes.endereco"))
            sections[title] = addresses
            used.update(address_fields)
    native = any(category_names(s) for s in profile.include)
    if native:
        info = entry.find("OUTRAS-INFORMACOES-RELEVANTES")
        if info:
            title = profile.section_title("lattes.outras-informacoes")
            sections[literal(title)] = [literal(info.text)]
            used.add(info.path)
    for key, names in {
        "email": ("E-MAIL", "ELETRONICO"),
        "website": ("HOME-PAGE",),
    }.items():
        if profile.category_selection("lattes.endereco") is True:
            continue
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
    content = []
    if summary:
        content.append(literal(summary.text))
        used.add(summary.path)
    if "details" not in profile.hide_fields:
        content.extend(_details(entry, used))
    if content:
        sections[literal(profile.section_title("profile"))] = content
    return used


def _category_sections(
    output: dict, selection: Selection, profile: Profile, rendered: dict[str, dict]
) -> dict:
    """Regroup selected records once; overlapping categories never copy entries."""
    groups = defaultdict(list)
    originals = {}
    for entry in selection.entries:
        if entry.id not in rendered:
            continue
        section = entry.section if profile.full else presentation_section(entry)
        category = presentation_category(entry, profile.include)
        if entry.section == "publications.conference" and not profile.full:
            for subtype in ("full", "abstracts"):
                groups.setdefault((category, "publications.conference." + subtype), [])
        key = (category, section)
        groups[key].append(rendered[entry.id])
        originals.setdefault(key, entry)
    blocks = []
    profile_entry = next((e for e in selection.entries if e.section == "profile"), None)
    if profile_entry:
        for category, title in (
            ("", literal(profile.section_title("profile"))),
            ("lattes.endereco", literal(profile.section_title("lattes.endereco"))),
            (
                "lattes.outras-informacoes",
                literal(profile.section_title("lattes.outras-informacoes")),
            ),
        ):
            if title in output:
                blocks.append(
                    (category, "profile", title, output[title], profile_entry)
                )
    for (category, section), values in groups.items():
        if not values:
            continue
        title = profile.section_title(section)
        if category:
            prefix = profile.section_title(category)
            title = (
                prefix
                if CATEGORIES[category].sections == (section,)
                else f"{prefix} — {title}"
            )
        blocks.append(
            (category, section, literal(title), values, originals[(category, section)])
        )

    def rank(block):
        category, section, _, _, original = block
        for i, selector in enumerate(profile.order + profile.include):
            if category_names(selector):
                if category and category in category_names(selector):
                    return i
                if not category and matches_selector(original, selector):
                    return i
            elif (not category or i < len(profile.order)) and matches_prefix(
                section, selector
            ):
                return i
        return len(profile.order) + len(profile.include)

    sections = {}
    for _, _, title, values, _ in sorted(blocks, key=rank):
        if title in sections:
            raise CVError(f"Título de seção repetido: {title}.")
        sections[title] = values
    return sections


def _registration_details(
    entry: Entry, profile: Profile, issues: list[Issue]
) -> tuple[list[str], set[str], set[str]]:
    """Render selected registration fields once, independent of the display category."""
    definitions = {
        "INSTITUICAO-DEPOSITO-REGISTRO": (
            "show_registration_institution",
            "Instituição de registro",
            "Registration institution",
        ),
        "CODIGO-DO-REGISTRO-OU-PATENTE": (
            "show_registration_number",
            "Número do registro",
            "Registration number",
        ),
        "DATA-PEDIDO-DE-DEPOSITO": (
            "show_deposit_date",
            "Data de depósito",
            "Filing date",
        ),
        "DATA-DE-CONCESSAO": ("show_grant_date", "Data da concessão", "Grant date"),
    }
    groups = defaultdict(dict)
    handled = set()
    for source in entry.fields:
        if source.tag == "REGISTRO-OU-PATENTE" and source.name in definitions:
            handled.add(source.path)
            groups[source.path.rsplit("/", 1)[0]][source.name] = source
    lines, used = [], set()
    for group in groups.values():
        for name, (option, pt, en) in definitions.items():
            source = group.get(name)
            if not source or not profile.section_option("lattes.patentes", option):
                continue
            value = source.text
            if name.startswith("DATA-"):
                try:
                    if not re.fullmatch(r"\d{8}", value):
                        raise ValueError
                    date = datetime.strptime(value, "%d%m%Y")
                    value = date.strftime(
                        "%d/%m/%Y" if profile.language == "pt" else "%Y-%m-%d"
                    )
                except ValueError:
                    issues.append(
                        Issue(
                            "invalid-date",
                            source.path,
                            "Data de registro inválida; exibida como texto original.",
                        )
                    )
            lines.append(literal(f"{pt if profile.language == 'pt' else en}: {value}"))
            used.add(source.path)
    return lines, used, handled


def _report(
    cv: Curriculum,
    selection: Selection,
    visible: dict[str, list[SourceField]],
    used: set[str],
    issues: list[Issue],
    profile: Profile,
    presentation_excluded: set[str] | None = None,
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
        elif source.path in used and status == "administrative":
            status = "exported"
        elif status in {"content", "unknown"}:
            if source.path in used:
                status = "exported"
            elif owners[source.path] and not owners[source.path] & selected_ids:
                status = "excluded"
                reason = "entry-filter"
            elif status == "content":
                if not source.text:
                    status = "empty"
                elif source.path in (presentation_excluded or ()):
                    status = "excluded"
                    reason = "presentation"
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


def export_data(
    cv: Curriculum, profile: Profile, *, design: dict | None = None
) -> tuple[dict, dict]:
    selection = select(cv, profile)
    active_design = design if design is not None else load_theme(profile.theme).design
    description_template = (
        active_design.get("templates", {})
        .get("normal_entry", {})
        .get("main_column", "")
    )
    titles = {}
    for section in dict.fromkeys(entry.section for entry in selection.entries):
        title = literal(profile.section_title(section))
        if title in titles:
            raise CVError(
                f"Título de seção repetido: {profile.section_title(section)} ({titles[title]} e {section})."
            )
        titles[title] = section
    issues = cv.issues + selection.issues
    institutions = _institution_details(cv, profile) if not profile.full else {}
    output = {"name": literal(cv.name), "sections": {}}
    name_field = next(entry for entry in cv.entries if entry.section == "profile").find(
        "NOME-COMPLETO"
    )
    used = {name_field.path}
    presentation_excluded = set()
    visible = {entry.id: visible_fields(entry, profile) for entry in selection.entries}
    owner_id = next(
        (
            f.text
            for f in cv.fields
            if f.tag == "CURRICULO-VITAE" and f.name == "NUMERO-IDENTIFICADOR"
        ),
        "",
    )
    self_authors = (
        {
            entry.id: _self_author(entry, owner_id, cv.name)
            for entry in selection.entries
        }
        if profile.authors.get("highlight_self", True)
        else {}
    )
    groups = defaultdict(list)
    rendered_by_id = {}
    for entry in selection.entries:
        sources = visible[entry.id]
        if not sources and not (entry.section in SECTION_OPTIONS and not profile.full):
            continue
        # Administrative author order participates in rendering but is never displayed.
        order = [f for f in entry.fields if f.name == "ORDEM-DE-AUTORIA"]
        view = replace(entry, fields=sources + order)
        if entry.id in profile.header_links:
            if {"contact", "links"} & set(
                profile.hide_fields
            ) or not profile.section_option(entry.section, "show_links"):
                presentation_excluded.update(f.path for f in sources)
                continue
            consumed = _header_link(view, output, profile)
            if consumed:
                used.update(consumed)
                presentation_excluded.update(
                    f.path for f in sources if f.path not in consumed
                )
                continue
        if entry.section == "profile":
            used.update(_profile(view, output, profile, issues))
        else:
            groups[entry.section].append(view)
    for section, entries in groups.items():
        concise_articles = section == "publications.articles" and not profile.full
        author_lists = [
            ([], set())
            if not profile.full
            and "show_authors" in SECTION_OPTIONS.get(section, {})
            and not profile.section_option(section, "show_authors")
            else _authors(entry, issues, profile, self_authors.get(entry.id))
            for entry in entries
        ]
        if concise_articles:
            # RenderCV accepts an empty author list; missing authors need no layout change.
            kind = "publication"
        else:
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
                    level="DEBUG",
                )
            )
        rendered = []
        for entry, (authors, author_fields) in zip(entries, author_lists):
            registration_lines, registration_used, registration_fields = (
                ([], set(), set())
                if profile.full
                else _registration_details(entry, profile, issues)
            )
            author_excluded = {
                f.path
                for f in entry.fields
                if f.tag == "AUTORES"
                and f.name in {"NOME-COMPLETO-DO-AUTOR", "NOME-PARA-CITACAO"}
                and f.path not in author_fields
                and (
                    profile.authors.get("et_al", False)
                    or profile.authors.get("use_informed_citation", not profile.full)
                )
            }
            presentation_excluded.update(author_excluded)
            view = replace(
                entry,
                fields=[
                    f
                    for f in entry.fields
                    if f.path not in registration_fields | author_excluded
                ],
            )
            result, consumed = _render_entry(
                view, kind, authors, author_fields, profile, issues, institutions
            )
            if "description" in result and not re.search(
                r"\bDESCRIPTION\b", description_template
            ):
                # External themes that do not use the extra field retain its content.
                result["summary"] = "\n".join(
                    s for s in (result.get("summary"), result.pop("description")) if s
                )
            if registration_lines:
                result["summary"] = "\n".join(
                    s for s in (result.get("summary"), *registration_lines) if s
                )
            consumed.update(registration_used)
            presentation_excluded.update(registration_fields - registration_used)
            rendered.append(result)
            rendered_by_id[entry.id] = result
            used.update(consumed)
            if section in SECTION_OPTIONS and not profile.full:
                presentation_excluded.update(
                    source.path
                    for source in visible[entry.id]
                    if source.path not in consumed
                )
        title = literal(profile.section_title(section))
        if title in output["sections"]:
            raise CVError(f"Título de seção repetido: {title}.")
        output["sections"][title] = rendered
    # Honor profile order including the profile section itself.
    labels = [
        literal(profile.section_title(entry.section)) for entry in selection.entries
    ]
    for title in list(output["sections"]):
        if title not in labels:
            # Additional profile pieces follow the profile's position.
            profile_title = literal(profile.section_title("profile"))
            position = labels.index(profile_title) + 1 if profile_title in labels else 0
            labels.insert(position, title)
    output["sections"] = {
        name: output["sections"][name]
        for name in dict.fromkeys(labels)
        if name in output["sections"]
    }
    if any(category_names(s) for s in profile.include) or (
        not profile.full
        and any(presentation_section(e) != e.section for e in selection.entries)
    ):
        output["sections"] = _category_sections(
            output["sections"], selection, profile, rendered_by_id
        )
    report = _report(
        cv, selection, visible, used, issues, profile, presentation_excluded
    )
    unmapped = report["counts"].get("unknown", 0) + report["counts"].get("unmapped", 0)
    if profile.full and unmapped and not profile.allow_unmapped:
        raise CVError(
            f"Modo completo bloqueado: {unmapped} campos/elementos não mapeados. "
            "Consulte inspect --json; use --allow-unmapped para aceitar as omissões registradas no relatório."
        )
    data = {
        "cv": output,
        "design": active_design,
        "locale": {"language": "portuguese" if profile.language == "pt" else "english"},
    }
    return data, report
