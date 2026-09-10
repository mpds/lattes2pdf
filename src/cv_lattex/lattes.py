"""Bounded XML/ZIP input and loss-aware extraction of Lattes records."""

from __future__ import annotations

import hashlib
import re
import stat
import unicodedata
import zipfile
import zlib
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from cv_lattex.models import Curriculum, CVError, Entry, Issue, SourceField, catalog

MAX_BYTES = 25 * 1024 * 1024
PRIVATE_NAMES = {
    "CPF",
    "NUMERO-DO-PASSAPORTE",
    "NUMERO-IDENTIDADE",
    "ORGAO-EMISSOR",
    "UF-ORGAO-EMISSOR",
    "DATA-DE-EMISSAO",
    "FORMATO-DATA-DE-EMISSAO",
    "NOME-DO-PAI",
    "NOME-DA-MAE",
    "DATA-NASCIMENTO",
    "PAIS-DE-NASCIMENTO",
    "UF-NASCIMENTO",
    "CIDADE-NASCIMENTO",
    "FORMATO-DATA-DE-NASCIMENTO",
    "SEXO",
    "RACA-OU-COR",
    "PCD",
    "DATA-FALECIMENTO",
    "NOME-DO-ARQUIVO-DE-FOTO",
}
ADMIN_NAMES = {
    "PERMISSAO-DE-DIVULGACAO",
    "STATUS-OASISBR",
    "ID-OASIS",
    "STA_VALIDACAO_DOI",
    "ORDEM-DE-AUTORIA",
    "ORDEM-DE-INTEGRACAO",
    "NUMERO-ID-CNPQ",
    "NRO-ID-CNPQ",
    "FLAG-RELEVANCIA",
    "FLAG-DIVULGACAO-CIENTIFICA",
}
YEAR_NAMES = (
    "ANO",
    "ANO-DO-ARTIGO",
    "ANO-DO-TEXTO",
    "ANO-DO-TRABALHO",
    "ANO-DA-OBRA",
    "ANO-DE-REALIZACAO",
    "ANO-DESENVOLVIMENTO",
    "ANO-DA-PREMIACAO",
    "ANO-SOLICITACAO",
    "ANO-DE-CONCLUSAO",
    "ANO-FIM",
    "ANO-DE-OBTENCAO-DO-TITULO",
    "ANO-DE-INICIO",
    "ANO-INICIO",
)


def _bounded_read(stream, limit: int) -> bytes:
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise CVError(f"Arquivo excede o limite de {limit} bytes.")
    return data


def _source_bytes(path: Path, member: str | None, limit: int) -> bytes:
    if not zipfile.is_zipfile(path):
        if member:
            raise CVError("--member só pode ser usado com ZIP.")
        with path.open("rb") as stream:
            return _bounded_read(stream, limit)
    if path.stat().st_size > limit:
        raise CVError(f"ZIP excede o limite de {limit} bytes.")
    try:
        with zipfile.ZipFile(path) as archive:
            items = archive.infolist()
            if len(items) > 1000:
                raise CVError("ZIP contém mais de 1000 arquivos.")
            names = [item.filename for item in items]
            if len(set(names)) != len(names):
                raise CVError("ZIP contém nomes de arquivo duplicados.")
            for item in items:
                name = PurePosixPath(item.filename)
                if (
                    name.is_absolute()
                    or ".." in name.parts
                    or "\\" in item.filename
                    or ":" in item.filename
                    or stat.S_ISLNK(item.external_attr >> 16)
                ):
                    raise CVError("ZIP contém caminho inseguro ou link simbólico.")
            candidates = [
                item
                for item in items
                if not item.is_dir() and item.filename.lower().endswith(".xml")
            ]
            if member:
                candidates = [item for item in candidates if item.filename == member]
            if len(candidates) != 1:
                raise CVError(
                    "Escolha um único XML do ZIP com --member. "
                    f"XMLs disponíveis: {', '.join(item.filename for item in items if item.filename.lower().endswith('.xml')) or 'nenhum'}."
                )
            item = candidates[0]
            if item.flag_bits & 1:
                raise CVError("ZIP protegido por senha não é suportado.")
            if item.file_size > limit:
                raise CVError(f"XML descompactado excede o limite de {limit} bytes.")
            with archive.open(item) as stream:
                return _bounded_read(stream, limit)
    except (
        zipfile.BadZipFile,
        RuntimeError,
        NotImplementedError,
        EOFError,
        zlib.error,
    ) as exc:
        raise CVError("Não foi possível ler o ZIP.") from exc


def _disposition(tag: str, name: str, known: bool, private: bool, auxiliary: bool):
    if private or name in PRIVATE_NAMES:
        return "private"
    if not known:
        return "unknown"
    if (
        auxiliary
        or tag == "CURRICULO-VITAE"
        or name in ADMIN_NAMES
        or name.startswith(
            (
                "SEQUENCIA-",
                "CODIGO-INSTITUICAO",
                "CODIGO-CURSO",
                "CODIGO-ORGAO",
                "CODIGO-UNIDADE",
            )
        )
    ):
        return "administrative"
    return "content"


def _digest(values) -> str:
    normalized = "\x1f".join(
        unicodedata.normalize("NFC", str(value)).strip().casefold() for value in values
    )
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]


def _identify(entries: list[Entry], issues: list[Issue]) -> None:
    collisions = defaultdict(list)
    for entry in entries:
        year = entry.find(*YEAR_NAMES)
        if year:
            if re.fullmatch(r"[1-9]\d{3}", year.text):
                entry.year = int(year.text)
            else:
                issues.append(
                    Issue(
                        "invalid-year",
                        year.path,
                        "Ano inválido; valor original preservado.",
                    )
                )
        doi = entry.find("DOI")
        title = entry.title_field()
        institution = entry.find("NOME-INSTITUICAO", "NOME-INSTITUICAO-EMPRESA")
        if doi:
            identity = [doi.text.removeprefix("https://doi.org/")]
        elif title:
            identity = [
                entry.tag,
                title.text,
                entry.year or "",
                institution.text if institution else "",
            ]
        else:
            identity = [
                entry.tag,
                *sorted(
                    f"{f.name}={f.text}"
                    for f in entry.fields
                    if f.text and f.disposition == "content"
                ),
            ]
        entry.id = f"{entry.section}:{_digest(identity)}"
        collisions[entry.id].append(entry)
    for group in collisions.values():
        if len(group) < 2:
            continue
        seen = Counter()
        for entry in group:
            fingerprint = _digest(
                sorted(
                    f"{f.tag}/{f.name}={f.text}"
                    for f in entry.fields
                    if f.text and f.disposition == "content"
                )
            )
            seen[fingerprint] += 1
            entry.id += f"-{fingerprint}"
            if seen[fingerprint] > 1:
                entry.id += f"-{seen[fingerprint]}"
            issues.append(
                Issue(
                    "duplicate-identity",
                    entry.path,
                    "Identidade repetida; registros mantidos com IDs distintos.",
                )
            )


def read_lattes(
    path: str | Path, *, member: str | None = None, max_bytes: int = MAX_BYTES
) -> Curriculum:
    raw = _source_bytes(Path(path), member, max_bytes)
    try:
        root = ElementTree.fromstring(
            raw, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except DefusedXmlException as exc:
        raise CVError("XML com DTD ou entidades não é permitido.") from exc
    except (ParseError, LookupError) as exc:
        raise CVError("XML malformado ou com codificação inválida.") from exc
    if root.tag.startswith("{"):
        raise CVError("Namespace XML não suportado; a fonte foi mantida intacta.")
    if root.tag != "CURRICULO-VITAE":
        raise CVError("O elemento raiz deve ser CURRICULO-VITAE.")
    if len(root.findall("DADOS-GERAIS")) != 1:
        raise CVError("O XML deve conter um único bloco DADOS-GERAIS.")

    vocabulary = catalog()["elements"]
    sections = {
        tag: name
        for name, definition in catalog()["sections"].items()
        for tag in definition["tags"]
    }
    cv = Curriculum(raw, [], [], [])
    stack = [(root, "/CURRICULO-VITAE[1]", True, None, False, False, (), 0)]
    node_count = 0
    while stack:
        node, path, known, owner, private, auxiliary, context, depth = stack.pop()
        node_count += 1
        if node_count > 200_000 or depth > 128:
            raise CVError("XML excede o limite de elementos ou de profundidade.")
        definition = vocabulary.get(node.tag, {}) if known else {}
        private = private or node.tag in {"ENDERECO-RESIDENCIAL", "LICENCAS"}
        auxiliary = auxiliary or node.tag in {
            "INFORMACOES-ADICIONAIS-INSTITUICOES",
            "INFORMACOES-ADICIONAIS-CURSOS",
        }
        if known and node.tag in sections:
            owner = Entry(sections[node.tag], node.tag, path, list(context))
            cv.entries.append(owner)
        if not known:
            cv.issues.append(
                Issue(
                    "unknown-element", path, "Elemento não reconhecido neste contexto."
                )
            )

        values = [
            (name, value, f"{path}/@{name}", name in definition.get("attributes", []))
            for name, value in node.attrib.items()
        ]
        if node.text and node.text.strip():
            values.append(
                ("#text", node.text, f"{path}/#text", definition.get("text", False))
            )
        if not known and not values:
            values.append(("#element", "", path, False))
        local_fields = []
        for name, value, source_path, recognized in values:
            status = _disposition(node.tag, name, recognized, private, auxiliary)
            source = SourceField(source_path, node.tag, name, value, status)
            local_fields.append(source)
            cv.fields.append(source)
            if owner:
                owner.fields.append(source)
            if status == "unknown" and name not in {"#element"}:
                cv.issues.append(
                    Issue("unknown-field", source_path, "Campo não reconhecido.")
                )
        if node.tag == "ATUACAO-PROFISSIONAL" and known:
            context = tuple(f for f in local_fields if f.name == "NOME-INSTITUICAO")
        counts = Counter()
        children = []
        for child in node:
            counts[child.tag] += 1
            child_path = f"{path}/{child.tag}[{counts[child.tag]}]"
            children.append(
                (
                    child,
                    child_path,
                    child.tag in definition.get("children", []),
                    owner,
                    private,
                    auxiliary,
                    context,
                    depth + 1,
                )
            )
            if child.tail and child.tail.strip():
                source = SourceField(
                    f"{child_path}/#tail", node.tag, "#text", child.tail, "unknown"
                )
                cv.fields.append(source)
                if owner:
                    owner.fields.append(source)
                cv.issues.append(
                    Issue(
                        "unknown-text", source.path, "Texto fora de um campo conhecido."
                    )
                )
        stack.extend(reversed(children))

    # An institution alone is context when its appointments are separate records.
    cv.entries = [
        entry
        for entry in cv.entries
        if not (
            entry.tag == "ATUACAO-PROFISSIONAL"
            and any(
                other.path.startswith(entry.path + "/VINCULOS[") for other in cv.entries
            )
            and all(
                f.disposition == "administrative"
                or f.name == "NOME-INSTITUICAO"
                or not f.text
                for f in entry.fields
            )
        )
    ]
    _identify(cv.entries, cv.issues)
    if not cv.name:
        raise CVError("O XML não contém NOME-COMPLETO em DADOS-GERAIS.")
    return cv
