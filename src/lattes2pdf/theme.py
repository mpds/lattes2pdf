"""Resolve RenderCV designs and the local files that travel with them."""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from lattes2pdf.models import CVError

THEMES = (
    "classic",
    "ember",
    "engineeringclassic",
    "engineeringresumes",
    "harvard",
    "ink",
    "moderncv",
    "opal",
    "sb2nov",
)


def is_theme_file(value: str) -> bool:
    return Path(value).suffix.lower() in {".yaml", ".yml"}


def validate_theme(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or (value not in THEMES and not is_theme_file(value))
    ):
        raise CVError(
            "theme deve ser um tema disponível ou caminho para design.yaml. "
            "Consulte lattes2pdf theme --help."
        )


def default_design(name: str) -> dict:
    return {
        "theme": name,
        "page": {"size": "a4", "show_top_note": False},
        "entries": {"allow_page_break": True},
        "templates": {
            "education_entry": {
                "degree_column": None,
                "main_column": "**DEGREE_WITH_AREA**\nINSTITUTION\nSUMMARY\nHIGHLIGHTS",
            },
            "experience_entry": {
                "main_column": "**POSITION**\nCOMPANY\nSUMMARY\nHIGHLIGHTS",
            },
            "normal_entry": {
                # Keep the optional wrapper whitespace-free so RenderCV removes it
                # entirely when DESCRIPTION is absent. The comment separates tokens.
                "main_column": '**NAME**\nSUMMARY\n#text(size:0.95em)[#set/**/text(fill:rgb("666666"));DESCRIPTION]\nHIGHLIGHTS',
            },
        },
    }


@dataclass
class Theme:
    design: dict
    assets: dict[Path, bytes] = field(default_factory=dict)
    sources: list[Path] = field(default_factory=list)

    def output_assets(self, directory: Path) -> list[tuple[Path, bytes]]:
        root = directory.resolve()
        result = []
        # RenderCV discovers neighboring templates/fonts automatically. Stale files
        # would make the saved YAML render differently from the isolated PDF.
        for folder in dict.fromkeys((self.design["theme"], "fonts")):
            parent = root / folder
            if parent.is_symlink():
                raise CVError(
                    f"Destino do tema não pode ser um link simbólico: {parent}."
                )
            for existing in parent.rglob("*") if parent.is_dir() else []:
                if "__pycache__" in existing.parts:
                    continue
                if existing.is_symlink() or (
                    existing.is_file() and existing.relative_to(root) not in self.assets
                ):
                    raise CVError(
                        f"A pasta de saída contém arquivos de outro tema: {existing}. "
                        "Use uma pasta separada para este tema."
                    )
        for relative, content in self.assets.items():
            target = root / relative
            for path in (target, *target.parents):
                if path == root:
                    break
                if path.is_symlink():
                    raise CVError(
                        f"Destino do tema não pode ser um link simbólico: {path}."
                    )
            if target.is_file() and target.read_bytes() == content:
                continue
            result.append((target, content))
        return result


class DesignLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise CVError("Chave inválida ou repetida no design YAML.")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _load_design(path: Path) -> Theme:
    with path.open("rb") as stream:
        raw = stream.read(65_537)
    if len(raw) > 65_536:
        raise CVError("Design excede o limite de 64 KiB.")
    try:
        depth = 0
        for event in yaml.parse(raw, Loader=DesignLoader):
            if isinstance(event, yaml.AliasEvent):
                raise CVError("Aliases YAML não são permitidos no design.")
            if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                depth += 1
            elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                depth -= 1
            if depth > 16:
                raise CVError("Design excede o limite de profundidade.")
        data = yaml.load(raw, Loader=DesignLoader)
    except (yaml.YAMLError, UnicodeError) as exc:
        raise CVError("Design YAML inválido.") from exc
    if not isinstance(data, dict) or set(data) != {"design"}:
        raise CVError("O arquivo de tema deve conter somente o mapa design.")
    design = data["design"]
    name = design.get("theme") if isinstance(design, dict) else None
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+", name):
        raise CVError(
            "design.theme deve conter um nome de tema com letras minúsculas e dígitos."
        )
    if name not in THEMES and not (path.parent / name).is_dir():
        raise CVError(f"Pasta do tema externo ausente: {path.parent / name}.")
    result = Theme(design, sources=[path.resolve()])
    # Never copy the whole source directory: it may also contain the user's CV.
    for folder in dict.fromkeys((name, "fonts")):
        directory = path.parent / folder
        if directory.is_symlink():
            raise CVError(
                f"A pasta do tema não pode ser um link simbólico: {directory}."
            )
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise CVError(f"Esperada uma pasta do tema: {directory}.")
        for asset in sorted(directory.rglob("*")):
            if asset.is_symlink():
                raise CVError(
                    f"Arquivo do tema não pode ser um link simbólico: {asset}."
                )
            if asset.is_file() and "__pycache__" not in asset.parts:
                result.assets[asset.relative_to(path.parent)] = asset.read_bytes()
                result.sources.append(asset.resolve())
    return result


def load_theme(value: str) -> Theme:
    validate_theme(value)
    if value in THEMES:
        return Theme(default_design(value))
    return _load_design(Path(value))
