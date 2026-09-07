"""Section options and their focused, offline CLI reference."""

from cv_lattex.models import CVError, catalog

EDUCATION_OPTIONS = {
    "show_thesis": (False, "Título do trabalho"),
    "show_advisors": (False, "Orientação e coorientação"),
}


def matching_sections(prefix: str) -> list[str]:
    names = [
        name
        for name in catalog()["sections"]
        if name == prefix or name.startswith(prefix + ".")
    ]
    if not names:
        raise CVError(f"Seção desconhecida: {prefix}. Consulte cv-lattex sections.")
    return names


def validate_options(sections: dict) -> None:
    if not isinstance(sections, dict):
        raise CVError("sections deve associar identificadores de seções a opções.")
    for name, options in sections.items():
        if name not in catalog()["sections"]:
            raise CVError(
                f"Seção desconhecida em sections: {name}. Use um identificador exato de cv-lattex sections."
            )
        allowed = {"title"} | (set(EDUCATION_OPTIONS) if name == "education" else set())
        if not isinstance(options, dict) or set(options) - allowed:
            raise CVError(
                f"Opções inválidas em sections.{name}. Consulte cv-lattex sections {name}."
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
    usage = "usage: cv-lattex sections [-h] [section]"
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
    if prefix == "education":
        for key, (default, description) in EDUCATION_OPTIONS.items():
            options.append(
                (key, "true|false", f"{description} (padrão: {str(default).lower()})")
            )
    lines.extend(
        f"  {key:<13}  {kind:<10}  {description}" for key, kind, description in options
    )
    return "\n".join(lines)
