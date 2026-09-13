"""Reference composition inspired by the Lattes ABNT and Chicago RTF exports."""

import re
from datetime import datetime

from lattes2pdf.lattes import YEAR_NAMES
from lattes2pdf.models import Entry, catalog
from lattes2pdf.selection import Profile
from lattes2pdf.text import literal


def is_production(entry: Entry) -> bool:
    return (
        entry.section.startswith(("publications.", "technical."))
        or entry.section == "artistic"
    )


def sentence(value: str) -> str:
    # Do not produce doubled stops after abbreviations such as "et al.".
    plain = value.rstrip("*")
    terminated = plain.endswith((".", "?", "!")) or re.search(
        r"\\u\{(?:2e|3f|21)\}\"\)$", plain
    )
    return value if not value or terminated else value + "."


def format_reference(
    entry: Entry, authors: list[str], profile: Profile
) -> tuple[str, set[str]]:
    used = set()
    chicago = profile.bibliography_style == "chicago"
    english = profile.language == "en"
    details = "details" not in profile.hide_fields
    if entry.section == "publications.articles":
        details = details and profile.section_option(entry.section, "show_details")

    def take(*names: str) -> str:
        source = entry.find(*names, language=profile.language)
        if not source:
            return ""
        used.add(source.path)
        return literal(source.text)

    def detail(*names: str) -> str:
        return take(*names) if details else ""

    source_title = entry.title_field(profile.language)
    title = (
        take(source_title.name)
        if source_title
        else catalog()["sections"][entry.section][profile.language]
    )
    # Registration dates are supplementary; the year of the production stays primary.
    year_source = entry.find(*YEAR_NAMES)
    year = take(year_source.name) if year_source else ""
    # A semicolon immediately after a Typst expression terminates the expression
    # instead of printing. Encode separators following highlighted/escaped names.
    byline = "".join(
        author
        + (
            ('#text("\\u{3b}") ' if author.endswith(("**", ")")) else "; ")
            if index < len(authors) - 1
            else ""
        )
        for index, author in enumerate(authors)
    )
    prefix = [sentence(byline)] if byline else []
    if chicago and year:
        prefix.append(sentence(year))

    first, last = detail("PAGINA-INICIAL"), detail("PAGINA-FINAL")
    pages = (
        first + ("-" + last if last and first != last else "")
        if first
        else (("ending at " if english else "final ") + last if last else "")
    )
    section = entry.section
    edition = (
        detail("NUMERO-DA-EDICAO-REVISAO")
        if section in {"publications.books", "publications.chapters"}
        else ""
    )
    periodical = section in {
        "publications.articles",
        "publications.accepted",
        "publications.press",
    }
    publisher = detail("NOME-DA-EDITORA") if not periodical else ""
    city = detail("CIDADE-DA-EDITORA", "LOCAL-DE-PUBLICACAO") if not periodical else ""
    imprint = ": ".join(v for v in (city, publisher) if v)
    volume = detail("VOLUME")
    issue = detail("FASCICULO")
    series = detail("SERIE", "NUMERO-DA-SERIE")
    numbering = ", ".join(
        v
        for v in (
            f"v. {volume}" if volume else "",
            f"{'no.' if english else 'n.'} {issue}" if issue else "",
            f"{'series' if english else 'série'} {series}" if series else "",
        )
        if v
    )
    in_word = "In " if chicago else "In: "
    section = entry.section
    body = [sentence(title)]
    tail = []
    if section in {
        "publications.articles",
        "publications.accepted",
        "publications.press",
    }:
        venue = take("TITULO-DO-PERIODICO-OU-REVISTA", "TITULO-DO-JORNAL-OU-REVISTA")
        if venue:
            body.append((in_word if chicago else "") + venue)
        tail.extend([numbering, f"p. {pages}" if pages else ""])
        if section == "publications.accepted":
            tail.append(
                "Accepted for publication" if english else "Aceito para publicação"
            )
        date = detail("DATA-DE-PUBLICACAO") if section == "publications.press" else ""
        if date:
            try:
                if re.fullmatch(r"[0-9]{8}", date):
                    date = datetime.strptime(date, "%d%m%Y").strftime("%d/%m/%Y")
            except ValueError:
                pass
            tail.append(
                ("Publication date: " if english else "Data de publicação: ") + date
            )
    elif section == "publications.books":
        if edition:
            body.append(f"{edition} ed.")
        if imprint:
            body.append(imprint)
        total = detail("NUMERO-DE-PAGINAS")
        tail.extend([numbering, f"{total} p." if total else ""])
    elif section == "publications.chapters":
        book = take("TITULO-DO-LIVRO")
        organizers = detail("ORGANIZADORES")
        if book or organizers:
            body.append(in_word + ". ".join(v for v in (organizers, book) if v))
        if edition:
            body.append(f"{edition} ed.")
        if chicago and pages:
            body.append(pages)
        if imprint:
            body.append(imprint)
        tail.extend([numbering, f"p. {pages}" if pages and not chicago else ""])
    elif section == "publications.conference":
        event = take("NOME-DO-EVENTO")
        proceedings = take("TITULO-DOS-ANAIS-OU-PROCEEDINGS")
        event_city = detail("CIDADE-DO-EVENTO")
        event_year = detail("ANO-DE-REALIZACAO")
        event_context = ", ".join(v for v in (event, event_year, event_city) if v)
        if chicago:
            if proceedings or event_context:
                body.append(
                    in_word + ". ".join(v for v in (proceedings, event_context) if v)
                )
        else:
            if event_context:
                body.append(in_word + event_context)
            if proceedings:
                body.append(proceedings)
        if imprint:
            body.append(imprint)
        tail.extend([numbering, f"p. {pages}" if pages else ""])
    else:
        # Other bibliographic, technical and artistic productions keep their
        # source-specific venue and type; no invented journal/publisher fields.
        venue = take(
            "TITULO-DA-PUBLICACAO",
            "NOME-DO-EVENTO",
            "EMISSORA",
            "VEICULO-DE-DIVULGACAO",
        )
        if venue:
            body.append(in_word + venue)
        institution = detail("INSTITUICAO-PROMOTORA", "INSTITUICAO-PROMOTORA-DO-EVENTO")
        place = detail(
            "LOCAL-DA-APRESENTACAO",
            "CIDADE-DA-APRESENTACAO",
            "CIDADE-DO-TRABALHO",
            "CIDADE",
        )
        kind = detail("NATUREZA", "TIPO")
        body.extend(v for v in (institution, place, imprint) if v)
        tail.extend([kind, numbering, f"p. {pages}" if pages else ""])
    if not chicago:
        if section in {
            "publications.books",
            "publications.chapters",
            "publications.conference",
        }:
            tail.insert(0, year)
        else:
            tail.append(year)
    tail = ", ".join(v for v in tail if v)
    if tail and len(body) > 1:
        body[-1] = body[-1] + ", " + tail
    elif tail:
        body.append(tail)
    result = " ".join(prefix + [sentence(part) for part in body if part])
    # Prevent an authorless Chicago year from becoming a Markdown numbered list.
    if re.match(r"^[0-9]+\. ", result):
        result = re.sub(r"^([0-9]+)\.", lambda m: m[1] + '#text("\\u{2e}")', result)
    return result, used
