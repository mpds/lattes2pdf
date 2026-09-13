"""Bounded, memory-only browser adapters over the unchanged CLI core."""

import copy
import io
import json
import stat
import struct
import zipfile
import zlib
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path, PurePosixPath
from xml.parsers import expat

import yaml
from rendercv.renderer.templater.templater import render_full_template
from rendercv.schema.rendercv_model_builder import (
    build_rendercv_model_from_commented_map,
)

from lattes2pdf.categories import CATEGORIES
from lattes2pdf.lattes import read_lattes
from lattes2pdf.models import CVError
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import load_profile
from lattes2pdf.theme import THEMES

MAX_BYTES = 25 * 1024 * 1024
MAX_PROFILE = 65536
DOCUMENT = Path("/document")
PRESETS = ("resumido", "ampliado", "completo")
_document = None
_archive_bytes = None


def _preset(name):
    if name not in PRESETS:
        raise CVError("Modelo inválido.")
    return load_profile(files("lattes2pdf").joinpath("presets", name + ".yaml"))


def catalog_data():
    return json.dumps(
        {
            "categories": [
                {"key": key, "label": value.pt} for key, value in CATEGORIES.items()
            ],
            "presets": {
                name: [key for key in _preset(name).include if key in CATEGORIES]
                for name in PRESETS
            },
            "themes": THEMES,
        },
        ensure_ascii=False,
    )


def _error_advanced():
    raise CVError(
        "Esta configuração contém opções avançadas. Utilize-a na CLI do lattes2pdf."
    )


def _profile(settings):
    if not isinstance(settings, dict) or set(settings) != {
        "model",
        "basis",
        "categories",
        "theme",
        "bibliography",
        "informed",
        "etAl",
        "professional",
        "production",
        "language",
    }:
        raise CVError("Configuração inválida.")
    if settings["model"] not in (*PRESETS, "personalizado"):
        raise CVError("Modelo inválido.")
    basis = (
        settings["basis"] if settings["model"] == "personalizado" else settings["model"]
    )
    profile = _preset(basis)
    if settings["model"] == "personalizado":
        selected = settings["categories"]
        if (
            not isinstance(selected, list)
            or not selected
            or any(key not in CATEGORIES for key in selected)
            or len(set(selected)) != len(selected)
        ):
            raise CVError("Selecione ao menos uma categoria válida.")
        profile.include = ["profile", *(key for key in CATEGORIES if key in selected)]
    if settings["theme"] not in THEMES:
        raise CVError("Selecione um dos nove temas disponíveis.")
    profile.theme = settings["theme"]
    profile.language = settings["language"]
    if settings["bibliography"] not in ("abnt", "chicago"):
        raise CVError("Selecione ABNT ou Chicago.")
    profile.bibliography_style = settings["bibliography"]
    profile.authors["use_informed_citation"] = settings["informed"]
    profile.authors["et_al"] = settings["etAl"]
    profile.periods = {
        group: {} if settings[key] is None else {"since": settings[key]}
        for group, key in [
            ("professional", "professional"),
            ("production", "production"),
        ]
    }
    profile.validate()
    return profile


def export_profile(settings):
    profile = _profile(settings)
    data = asdict(profile)
    # Only the supported surface and fixed preset presentation defaults travel.
    supported = (
        "include",
        "hide_fields",
        "sections",
        "authors",
        "periods",
        "bibliography_style",
        "theme",
        "language",
    )
    return yaml.safe_dump(
        {key: data[key] for key in supported}, allow_unicode=True, sort_keys=False
    )


def import_profile(raw):
    raw = bytes(raw)
    if len(raw) > MAX_PROFILE:
        raise CVError("A configuração excede o limite de 64 KiB.")
    DOCUMENT.mkdir(exist_ok=True)
    path = DOCUMENT / "profile.yaml"
    path.write_bytes(raw)
    try:
        profile = load_profile(path)  # Shared bounded, duplicate/alias-safe loader.
        data = yaml.safe_load(raw)
    finally:
        path.unlink(missing_ok=True)
    supported = {
        "include",
        "hide_fields",
        "sections",
        "authors",
        "periods",
        "bibliography_style",
        "theme",
        "language",
    }
    if set(data) - supported or profile.theme not in THEMES:
        _error_advanced()
    if (
        not profile.include
        or profile.include[0] != "profile"
        or any(key not in CATEGORIES for key in profile.include[1:])
    ):
        _error_advanced()
    if len(set(profile.include)) != len(profile.include):
        _error_advanced()
    categories = [key for key in CATEGORIES if key in profile.include]
    if not categories or profile.include != ["profile", *categories]:
        _error_advanced()
    if profile.bibliography_style not in ("abnt", "chicago"):
        _error_advanced()
    if (
        profile.authors.get("name_case", "original") != "original"
        or profile.authors.get("highlight_self", True) is not True
    ):
        _error_advanced()
    for period in profile.periods.values():
        if set(period) - {"since"}:
            _error_advanced()
    basis = None
    # Preserve the fixed presentation defaults of the originating preset.
    for name in PRESETS:
        candidate = _preset(name)
        if (
            profile.hide_fields == candidate.hide_fields
            and profile.sections == candidate.sections
        ):
            basis = name
            if profile.include == candidate.include:
                break
    if basis is None:
        _error_advanced()
    model = next(
        (
            name
            for name in PRESETS
            if profile.include == _preset(name).include
            and profile.sections == _preset(name).sections
        ),
        "personalizado",
    )
    settings = dict(
        model=model,
        basis=basis,
        categories=categories,
        theme=profile.theme,
        bibliography=profile.bibliography_style,
        informed=profile.authors.get("use_informed_citation", True),
        etAl=profile.authors.get("et_al", False),
        professional=profile.periods.get("professional", {}).get("since"),
        production=profile.periods.get("production", {}).get("since"),
        language=profile.language,
    )
    _profile(settings)
    return json.dumps(settings, ensure_ascii=False)


def _preflight_xml(raw):
    parser = expat.ParserCreate()
    depth = count = 0

    def start(_name, _attributes):
        nonlocal depth, count
        depth += 1
        count += 1
        if depth > 129 or count > 200000:
            raise CVError("XML excede o limite de elementos ou de profundidade.")

    def end(_name):
        nonlocal depth
        depth -= 1

    def forbidden(*_args):
        raise CVError("XML com DTD ou entidades não é permitido.")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    try:
        for offset in range(0, len(raw), 65536):
            parser.Parse(raw[offset : offset + 65536], False)
        parser.Parse(b"", True)
    except (expat.ExpatError, LookupError, ValueError) as exc:
        if isinstance(exc, CVError):
            raise
        raise CVError("XML malformado ou com codificação inválida.") from exc


def _zip_members(raw):
    # Count central directory entries before ZipFile allocates ZipInfo objects.
    end = raw.rfind(b"PK\x05\x06", max(0, len(raw) - 65557))
    if end < 0 or end + 22 > len(raw):
        raise CVError("ZIP inválido.")
    disk, directory_disk, disk_entries, count, size, offset, comment = (
        struct.unpack_from("<4H2LH", raw, end + 4)
    )
    if (
        disk
        or directory_disk
        or disk_entries != count
        or count > 1000
        or offset + size > end
        or end + 22 + comment != len(raw)
    ):
        raise CVError("ZIP inválido, dividido em volumes ou com mais de 1000 arquivos.")
    cursor = offset
    actual = 0
    while cursor < offset + size:
        if raw[cursor : cursor + 4] != b"PK\x01\x02" or cursor + 46 > end:
            raise CVError("Diretório ZIP inválido.")
        filename, extra, note = struct.unpack_from("<3H", raw, cursor + 28)
        cursor += 46 + filename + extra + note
        actual += 1
        if actual > 1000:
            raise CVError("ZIP contém mais de 1000 arquivos.")
    if actual != count or cursor != offset + size:
        raise CVError("Diretório ZIP inválido.")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = set()
        members = []
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in item.filename
                or ":" in item.filename
                or stat.S_ISLNK(item.external_attr >> 16)
                or item.filename in names
            ):
                raise CVError(
                    "ZIP contém caminho inseguro, link simbólico ou nome duplicado."
                )
            if item.flag_bits & 1 or item.compress_type not in (
                zipfile.ZIP_STORED,
                zipfile.ZIP_DEFLATED,
            ):
                raise CVError("ZIP com senha ou compressão não suportada.")
            names.add(item.filename)
            if not item.is_dir() and item.filename.lower().endswith(".xml"):
                members.append(item.filename)
        if not members:
            raise CVError("O ZIP não contém um arquivo XML.")
        return members


def load_document(raw, member=None):
    global _document, _archive_bytes
    _document = None
    _archive_bytes = None
    raw = bytes(raw)
    if not raw or len(raw) > MAX_BYTES:
        raise CVError("Selecione um XML ou ZIP de até 25 MiB.")
    try:
        if zipfile.is_zipfile(io.BytesIO(raw)) or raw.startswith(b"PK"):
            members = _zip_members(raw)
            if member is None and len(members) > 1:
                _archive_bytes = raw
                return json.dumps({"members": members}, ensure_ascii=False)
            member = members[0] if member is None else member
            if member not in members:
                raise CVError("Selecione um XML da lista.")
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if archive.getinfo(member).file_size > MAX_BYTES:
                    raise CVError("XML descompactado excede o limite de 25 MiB.")
                with archive.open(member) as stream:
                    raw = stream.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise CVError("XML descompactado excede o limite de 25 MiB.")
        elif member is not None:
            raise CVError("A escolha de XML é válida somente para ZIP.")
        _archive_bytes = None
        _preflight_xml(raw)
        DOCUMENT.mkdir(exist_ok=True)
        path = DOCUMENT / "input.xml"
        path.write_bytes(raw)
        try:
            _document = read_lattes(path)
        finally:
            path.unlink(missing_ok=True)
        return json.dumps({"name": _document.name}, ensure_ascii=False)
    except (
        zipfile.BadZipFile,
        RuntimeError,
        NotImplementedError,
        EOFError,
        zlib.error,
    ) as exc:
        raise CVError(
            "Não foi possível ler o ZIP. Exporte o currículo novamente."
        ) from exc


def choose_member(member):
    if _archive_bytes is None:
        raise CVError("Selecione o arquivo ZIP novamente.")
    return load_document(_archive_bytes, member)


def prepare(settings):
    if _document is None:
        raise CVError("Selecione um currículo antes de gerar o PDF.")
    profile = _profile(settings)
    data, report = export_data(_document, profile)
    # No photo/custom files/remote resource resolver is part of this surface.
    if data["cv"].get("photo"):
        raise CVError("Fotos externas não são suportadas no navegador.")
    model = build_rendercv_model_from_commented_map(
        copy.deepcopy(data), DOCUMENT / "input.yaml"
    )
    typst = render_full_template(model, "typst")
    report["renderer"] = {
        "name": "RenderCV",
        "version": "2.8",
        "theme": profile.theme,
        "compiler": "Typst 0.14.2 (WASM)",
        "execution": "browser",
    }
    return json.dumps(
        dict(
            name=_document.name,
            typst=typst,
            yaml=yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
            report=report,
            empty=not data["cv"]["sections"],
        ),
        ensure_ascii=False,
    )


def call(method, payload):
    """Only parameter data crosses from JS; no source strings contain CV input."""
    try:
        if method == "load":
            return load_document(payload)
        if method == "member":
            return choose_member(payload)
        if method == "profile-import":
            return import_profile(payload)
        if method == "profile-export":
            return json.dumps(export_profile(json.loads(payload)))
        if method == "prepare":
            return prepare(json.loads(payload))
        raise CVError("Operação inválida.")
    except CVError as exc:
        return json.dumps({"error": str(exc), "code": exc.code}, ensure_ascii=False)
