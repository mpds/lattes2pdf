"""Strict, reusable selection profiles independent of the output renderer."""

from dataclasses import dataclass, field, fields, replace
from pathlib import Path

import yaml

from cv_lattex.models import Curriculum, CVError, Entry, Issue, SourceField, catalog
from cv_lattex.sections import SECTION_OPTIONS, validate_options
from cv_lattex.theme import THEMES as THEMES
from cv_lattex.theme import is_theme_file, validate_theme

FIELD_GROUPS = (
    "authors",
    "date",
    "links",
    "contact",
    "summary",
    "advisors",
    "thesis",
    "details",
)


class ProfileLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise CVError("As chaves do perfil devem ser texto.")
            if key in result:
                raise CVError(f"Chave repetida no perfil: {key}.")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


@dataclass
class Profile:
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    include_ids: list[str] = field(default_factory=list)
    exclude_ids: list[str] = field(default_factory=list)
    header_links: list[str] = field(default_factory=list)
    order: list[str] = field(default_factory=list)
    hide_fields: list[str] = field(default_factory=list)
    since: int | None = None
    until: int | None = None
    section_years: dict[str, dict[str, int]] = field(default_factory=dict)
    sections: dict[str, dict] = field(default_factory=dict)
    authors: dict = field(default_factory=dict)
    unknown_year: str = "keep"
    sort: str = "year_desc"
    language: str = "pt"
    theme: str = "classic"
    full: bool = False
    allow_unmapped: bool = False

    def section_title(self, name: str) -> str:
        return (
            self.sections.get(name, {})
            .get("title", catalog()["sections"][name][self.language])
            .strip()
        )

    def section_option(self, name: str, option: str) -> bool:
        return self.sections.get(name, {}).get(option, SECTION_OPTIONS[name][option][0])

    def validate(self) -> None:
        validate_options(self.sections)
        if not isinstance(self.authors, dict) or set(self.authors) - {
            "name_case",
            "highlight_self",
        }:
            raise CVError("authors aceita somente name_case e highlight_self.")
        if self.authors.get("name_case", "original") not in (
            "original",
            "upper",
            "title",
        ):
            raise CVError("authors.name_case deve ser um de: original, upper, title.")
        if type(self.authors.get("highlight_self", True)) is not bool:
            raise CVError("authors.highlight_self deve ser booleano.")
        for name in (
            "include",
            "exclude",
            "include_ids",
            "exclude_ids",
            "header_links",
            "order",
            "hide_fields",
        ):
            value = getattr(self, name)
            if not isinstance(value, list) or any(
                not isinstance(v, str) or not v for v in value
            ):
                raise CVError(f"{name} deve ser uma lista de textos não vazios.")
        for name in ("include", "exclude", "order"):
            for section in getattr(self, name):
                _validate_section(section)
        allowed_fields = {
            name
            for definition in catalog()["elements"].values()
            for name in definition["attributes"]
        } | set(FIELD_GROUPS)
        for name in self.hide_fields:
            if name not in allowed_fields or name == "NOME-COMPLETO":
                raise CVError(
                    f"Campo inválido para ocultar: {name}. Consulte export --help."
                )
        _validate_years(self.since, self.until)
        if not isinstance(self.section_years, dict):
            raise CVError("section_years deve associar seções a since/until.")
        for section, years in self.section_years.items():
            _validate_section(section)
            if not isinstance(years, dict) or set(years) - {"since", "until"}:
                raise CVError(
                    "Cada intervalo em section_years aceita somente since e until."
                )
            _validate_years(years.get("since"), years.get("until"))
        for name, options in {
            "language": ("pt", "en"),
            "unknown_year": ("keep", "exclude"),
            "sort": ("source", "year_desc"),
        }.items():
            if getattr(self, name) not in options:
                raise CVError(f"{name} deve ser um de: {', '.join(options)}.")
        validate_theme(self.theme)
        if type(self.full) is not bool or type(self.allow_unmapped) is not bool:
            raise CVError("full e allow_unmapped devem ser booleanos.")
        if self.full and (
            self.include
            or self.exclude
            or self.include_ids
            or self.exclude_ids
            or self.header_links
            or self.hide_fields
            or self.since is not None
            or self.until is not None
            or self.section_years
            or self.unknown_year != "keep"
            or any(
                key != "title" for options in self.sections.values() for key in options
            )
        ):
            raise CVError(
                "--full não pode ser combinado com filtros, campos ocultos ou ajustes de campos por seção."
            )


def _matches(section: str, prefix: str) -> bool:
    return section == prefix or section.startswith(prefix + ".")


def _validate_section(section: str) -> None:
    if not isinstance(section, str) or not any(
        _matches(name, section) for name in catalog()["sections"]
    ):
        raise CVError(
            f"Seção desconhecida: {section}. Consulte inspect para listar seções."
        )


def _validate_years(since, until) -> None:
    if any(
        value is not None and (type(value) is not int or not 1000 <= value <= 9999)
        for value in (since, until)
    ):
        raise CVError("since e until devem ser anos com quatro dígitos.")
    if since is not None and until is not None and since > until:
        raise CVError("since não pode ser posterior a until.")


def load_profile(path: Path | None, overrides: dict | None = None) -> Profile:
    data = {}
    if path:
        with path.open("rb") as stream:
            raw = stream.read(65_537)
        if len(raw) > 65_536:
            raise CVError("Perfil excede o limite de 64 KiB.")
        try:
            depth = 0
            for event in yaml.parse(raw, Loader=ProfileLoader):
                if isinstance(event, yaml.AliasEvent):
                    raise CVError("Aliases YAML não são permitidos em perfis.")
                if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                    depth += 1
                elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                    depth -= 1
                if depth > 16:
                    raise CVError("Perfil excede o limite de profundidade.")
            data = yaml.load(raw, Loader=ProfileLoader)
        except (yaml.YAMLError, UnicodeError) as exc:
            raise CVError("Perfil YAML inválido.") from exc
        if not isinstance(data, dict):
            raise CVError("O perfil deve ser um mapa YAML.")
    unknown = set(data) - {item.name for item in fields(Profile)}
    if unknown:
        raise CVError(f"Opções desconhecidas no perfil: {', '.join(sorted(unknown))}.")
    # Validate the file before applying CLI overrides so typos never disappear.
    Profile(**data).validate()
    data.update(
        {key: value for key, value in (overrides or {}).items() if value is not None}
    )
    profile = Profile(**data)
    profile.validate()
    if path and is_theme_file(profile.theme) and (overrides or {}).get("theme") is None:
        profile.theme = str((path.resolve().parent / profile.theme).resolve())
    return profile


@dataclass
class Selection:
    entries: list[Entry]
    excluded: dict[str, str]
    issues: list[Issue]


def select(cv: Curriculum, profile: Profile) -> Selection:
    profile.validate()
    known_ids = {entry.id for entry in cv.entries}
    invalid = (
        set(profile.include_ids + profile.exclude_ids + profile.header_links)
        - known_ids
    )
    if invalid:
        raise CVError(
            f"IDs desconhecidos: {', '.join(sorted(invalid))}. Consulte inspect."
        )
    selected, excluded, issues = [], {}, []
    for entry in cv.entries:
        reason = None
        if (
            profile.include
            and not any(_matches(entry.section, s) for s in profile.include)
        ) or any(_matches(entry.section, s) for s in profile.exclude):
            reason = "section"
        elif (
            profile.include_ids and entry.id not in profile.include_ids
        ) or entry.id in profile.exclude_ids:
            reason = "id"
        since, until = profile.since, profile.until
        for section, years in sorted(
            profile.section_years.items(), key=lambda pair: len(pair[0])
        ):
            if _matches(entry.section, section):
                since, until = years.get("since", since), years.get("until", until)
        _validate_years(since, until)
        if (
            not reason
            and entry.section != "profile"
            and (since is not None or until is not None)
        ):
            if entry.year is None:
                if profile.unknown_year == "exclude":
                    reason = "unknown-year"
                else:
                    issues.append(
                        Issue(
                            "unknown-year",
                            entry.path,
                            "Registro sem ano mantido apesar do filtro; use unknown_year: exclude para removê-lo.",
                        )
                    )
            elif (since is not None and entry.year < since) or (
                until is not None and entry.year > until
            ):
                reason = "year"
        if reason:
            excluded[entry.id] = reason
        else:
            selected.append(entry)
    section_order = []
    for prefix in profile.order + list(catalog()["sections"]):
        section_order.extend(
            name
            for name in catalog()["sections"]
            if _matches(name, prefix) and name not in section_order
        )
    selected.sort(
        key=lambda entry: (
            section_order.index(entry.section),
            -(entry.year or 0) if profile.sort == "year_desc" else 0,
        )
    )
    selected_web_ids = {
        entry.id for entry in selected if entry.section == "technical.web"
    }
    if set(profile.header_links) - selected_web_ids:
        raise CVError(
            "header_links aceita IDs selecionados de technical.web. "
            "Confira include, exclude e os filtros de registros."
        )
    return Selection(selected, excluded, issues)


def hidden(source: SourceField, profile: Profile) -> bool:
    names = profile.hide_fields
    if (
        source.name in names
        or source.name.removesuffix("-INGLES").removesuffix("-EN") in names
    ):
        return True
    if "authors" in names and source.tag == "AUTORES":
        return True
    if "date" in names and source.name.startswith(("ANO", "MES-", "DATA-")):
        return True
    if "links" in names and (
        source.name
        in {"DOI", "ORCID-ID", "HOME-PAGE", "HOME-PAGE-DO-TRABALHO", "REDE-SOCIAL"}
    ):
        return True
    if "contact" in names and "/ENDERECO[" in source.path:
        return True
    if "summary" in names and source.name.startswith("TEXTO-RESUMO-CV"):
        return True
    if "advisors" in names and (
        "ORIENTADOR" in source.name or "COORIENTADOR" in source.name
    ):
        return True
    if (
        "thesis" in names
        and source.tag in catalog()["sections"]["education"]["tags"]
        and source.name.startswith("TITULO-")
    ):
        return True
    return False


def visible_fields(entry: Entry, profile: Profile) -> list[SourceField]:
    explicit_leave = entry.section == "leave" and (
        "leave" in profile.include or entry.id in profile.include_ids
    )
    candidates = [
        replace(f, disposition="content") if f.disposition == "private" else f
        for f in entry.fields
        if f.text
        and (
            f.disposition == "content"
            or (
                explicit_leave
                and f.disposition == "private"
                and f.tag == "LICENCA"
                and f.name in catalog()["elements"]["LICENCA"]["attributes"]
            )
        )
        and not hidden(f, profile)
    ]
    result = []
    paths = {f.path for f in candidates}
    for source in candidates:
        suffix = next((s for s in ("-INGLES", "-EN") if source.name.endswith(s)), None)
        if suffix:
            base = source.path.removesuffix(suffix)
            if profile.language == "pt" and base in paths:
                continue
        elif profile.language == "en" and any(
            source.path + s in paths for s in ("-INGLES", "-EN")
        ):
            continue
        result.append(source)
    return result
