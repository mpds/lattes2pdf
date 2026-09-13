"""Section options and their focused, offline CLI reference."""

from lattes2pdf.categories import CATEGORIES, category_names, matches_prefix
from lattes2pdf.models import CVError, catalog

SECTION_OPTIONS = {
    "profile": {
        "show_birth_date": (False, "Data de nascimento no cabeçalho"),
        "show_birth_place": (False, "Local de nascimento no cabeçalho"),
    },
    "education": {
        "show_thesis": (False, "Título do trabalho"),
        "show_advisors": (False, "Orientação e coorientação"),
        "show_scholarship": (True, "Bolsa e agência financiadora"),
    },
    "awards": {"show_institution": (True, "Entidade promotora")},
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


def _option_lines(name: str, *, show_title: bool = True) -> list[str]:
    options = (
        [("title", "texto", "Título da seção (padrão: original)")] if show_title else []
    )
    for key, (default, description) in SECTION_OPTIONS.get(name, {}).items():
        options.append(
            (key, "true|false", f"{description} (padrão: {str(default).lower()})")
        )
    if not options:
        return []
    width = max(13, *(len(key) for key, _, _ in options))
    return [f"Perfil YAML: sections.{name}"] + [
        f"  {key:<{width}}  {kind:<10}  {description}"
        for key, kind, description in options
    ]


def _category_lines(name: str) -> list[str]:
    category = CATEGORIES[name]
    definitions = catalog()["sections"]
    lines = [f"{name} — {category.pt}"]
    if category.predicate:
        lines.extend(
            [
                "",
                "Esta categoria seleciona apenas os registros que atendem ao seu critério nos grupos abaixo.",
            ]
        )
    elif name == "lattes.endereco":
        lines.extend(
            [
                "",
                "Seleciona os endereços profissional, residencial e eletrônico do perfil.",
            ]
        )
    elif name == "lattes.outras-informacoes":
        lines.extend(
            ["", "Seleciona somente as outras informações relevantes do perfil."]
        )
    if category.separate or name == "lattes.outras-informacoes":
        lines.extend(["", f"Título da categoria: sections.{name}.title."])
    lines.extend(["", "Grupos relacionados:"])
    for section in category.sections:
        if section in definitions:
            lines.extend(["", f"  {section} — {definitions[section]['pt']}"])
            lines.extend(
                "    " + line
                for line in _option_lines(
                    section,
                    show_title=not category.separate
                    and name != "lattes.outras-informacoes",
                )
            )
        else:
            lines.extend(
                [
                    "",
                    f"  {section} — {len(matching_sections(section))} grupos",
                    f"    Ver grupos e ajustes: lattes2pdf sections {section}",
                ]
            )
    lines.extend(
        [
            "",
            "Em export/render, --include GRUPO e --exclude GRUPO atuam sobre o grupo inteiro.",
            f"Ver registros e IDs: lattes2pdf inspect curriculo.xml --section {name}",
        ]
    )
    return lines


def describe_sections(prefix: str | None = None) -> str:
    lines = ["usage: lattes2pdf sections [-h] [section]", ""]
    if prefix is None or prefix == "lattes":
        width = max(len(name) for name in CATEGORIES)
        lines.append("Categorias do Lattes:")
        lines.extend(
            f"  {name:<{width}}  {category.pt}" for name, category in CATEGORIES.items()
        )
        lines.extend(
            [
                "",
                "Grupos e ajustes de uma categoria: lattes2pdf sections lattes.formacao",
                "Dados de identificação e nascimento: lattes2pdf sections profile",
                "Em export/render, use --include CATEGORIA ou --exclude CATEGORIA.",
                "lattes seleciona todas as categorias; cada registro aparece uma vez.",
            ]
        )
    elif prefix in CATEGORIES:
        lines.extend(_category_lines(prefix))
    else:
        definitions = catalog()["sections"]
        names = matching_sections(prefix)
        if prefix in definitions:
            lines.extend([f"{prefix}  {definitions[prefix]['pt']}", ""])
            lines.extend(_option_lines(prefix))
        else:
            width = max(len(name) for name in names)
            lines.append("Grupos:")
            lines.extend(
                f"  {name:<{width}}  {definitions[name]['pt']}" for name in names
            )
            lines.extend(["", "Ajustes de um grupo: lattes2pdf sections GRUPO"])
    return "\n".join(lines)
