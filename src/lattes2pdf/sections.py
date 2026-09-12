"""Section options and their focused, offline CLI reference."""

from lattes2pdf.models import CVError, catalog

SECTION_OPTIONS = {
    "education": {
        "show_thesis": (False, "Título do trabalho"),
        "show_advisors": (False, "Orientação e coorientação"),
    },
    "publications.articles": {
        "show_authors": (True, "Autores"),
        "show_links": (True, "DOI ou endereço do artigo"),
        "show_details": (False, "Volume, fascículo, série e páginas"),
    },
    "supervision.completed": {
        "show_students": (True, "Nomes dos orientados"),
        "show_institution": (True, "Instituição e curso"),
    },
    "supervision.ongoing": {
        "show_students": (True, "Nomes dos orientandos"),
        "show_institution": (True, "Instituição e curso"),
    },
    "research.projects": {
        "show_members": (True, "Integrantes e responsável"),
        "show_description": (False, "Descrição do projeto"),
    },
    "languages": {"show_proficiency": (True, "Leitura, fala, escrita e compreensão")},
    "events": {
        "show_event_type": (True, "Tipo do evento e participação"),
        "show_links": (True, "DOI ou endereço do trabalho"),
    },
    **{
        name: {"show_institution": (True, "Instituição e unidade")}
        for name in (
            "activities.internships",
            "activities.extension",
            "activities.other",
            "activities.committees",
        )
    },
    **{
        name: {
            "show_authors": (False, "Autores"),
            "show_links": (True, "DOI ou endereço do trabalho"),
        }
        for name in ("technical.events", "technical.broadcasts", "technical.web")
    },
}


def matching_sections(prefix: str) -> list[str]:
    names = [
        name
        for name in catalog()["sections"]
        if name == prefix or name.startswith(prefix + ".")
    ]
    if not names:
        raise CVError(f"Seção desconhecida: {prefix}. Consulte lattes2pdf sections.")
    return names


def validate_options(sections: dict) -> None:
    if not isinstance(sections, dict):
        raise CVError("sections deve associar identificadores de seções a opções.")
    for name, options in sections.items():
        if name not in catalog()["sections"]:
            raise CVError(
                f"Seção desconhecida em sections: {name}. Use um identificador exato de lattes2pdf sections."
            )
        allowed = {"title"} | set(SECTION_OPTIONS.get(name, {}))
        if not isinstance(options, dict) or set(options) - allowed:
            raise CVError(
                f"Opções inválidas em sections.{name}. Consulte lattes2pdf sections {name}."
            )
        for key, value in options.items():
            if key == "title":
                if (
                    not isinstance(value, str)
                    or not value.strip()
                    or "\n" in value
                    or "\r" in value
                ):
                    raise CVError(
                        f"sections.{name}.title deve ser texto não vazio em uma linha."
                    )
            elif type(value) is not bool:
                raise CVError(f"sections.{name}.{key} deve ser true ou false.")


def describe_sections(prefix: str | None = None) -> str:
    definitions = catalog()["sections"]
    if prefix is None:
        groups = {}
        for name in definitions:
            groups.setdefault(name.split(".")[0], []).append(name)
        rows = [
            (
                name,
                definitions[name]["pt"]
                if name in definitions
                else f"{len(children)} subseções",
            )
            for name, children in groups.items()
        ]
    else:
        rows = [(name, definitions[name]["pt"]) for name in matching_sections(prefix)]

    width = max(len(name) for name, _ in rows)
    usage = "usage: lattes2pdf sections [-h] [section]"
    lines = [
        usage,
        "",
        "Seções:",
        *(f"  {name:<{width}}  {title}" for name, title in rows),
    ]
    if prefix not in definitions:
        return "\n".join(lines)

    lines = [
        usage,
        "",
        f"{prefix}  {definitions[prefix]['pt']}",
        "",
        f"Perfil YAML: sections.{prefix}",
    ]
    options = [("title", "texto", "Título da seção (padrão: original)")]
    for key, (default, description) in SECTION_OPTIONS.get(prefix, {}).items():
        options.append(
            (key, "true|false", f"{description} (padrão: {str(default).lower()})")
        )
    width = max(13, *(len(key) for key, _, _ in options))
    lines.extend(
        f"  {key:<{width}}  {kind:<10}  {description}"
        for key, kind, description in options
    )
    return "\n".join(lines)
