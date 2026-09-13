"""Section options and their focused, offline CLI reference."""

from lattes2pdf.categories import CATEGORIES, category_names, matches_prefix
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
    if categories := category_names(prefix):
        return [
            name
            for name in catalog()["sections"]
            if any(
                matches_prefix(name, s)
                for c in categories
                for s in CATEGORIES[c].sections
            )
        ]
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
        if name not in catalog()["sections"] and name not in CATEGORIES:
            raise CVError(
                f"Seção desconhecida em sections: {name}. Use um identificador exato de lattes2pdf sections."
            )
        if (
            name in CATEGORIES
            and not CATEGORIES[name].separate
            and name != "lattes.outras-informacoes"
        ):
            raise CVError(
                f"A categoria {name} usa os títulos das seções de origem. "
                f"Configure sections para: {', '.join(CATEGORIES[name].sections)}."
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
    if names := category_names(prefix or ""):
        lines = [
            "usage: lattes2pdf sections [-h] [section]",
            "",
            "Categorias do Lattes:",
        ]
        width = max(len(name) for name in names)
        lines.extend(f"  {name:<{width}}  {CATEGORIES[name].pt}" for name in names)
        lines.extend(
            [
                "",
                "Use estes identificadores em include, exclude e order, junto das seções existentes.",
                "lattes seleciona todas as categorias abaixo; cada registro aparece uma vez.",
                "Endereço: show_address: true|false ou --show-address/--no-show-address.",
                "Citações numéricas e totais de produção não são incluídos no CV.",
            ]
        )
        if prefix in CATEGORIES:
            lines.extend(
                [
                    "",
                    "Seções de origem: " + ", ".join(CATEGORIES[prefix].sections),
                    f"Título personalizado: sections.{prefix}.title."
                    if CATEGORIES[prefix].separate
                    or prefix == "lattes.outras-informacoes"
                    else "Personalize os títulos nas seções de origem.",
                    "A categoria pode selecionar somente um subconjunto dos registros dessas seções.",
                ]
            )
        return "\n".join(lines)
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
        if prefix is None:
            lines.extend(
                ["", "Categorias da exportação Lattes: lattes2pdf sections lattes"]
            )
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
