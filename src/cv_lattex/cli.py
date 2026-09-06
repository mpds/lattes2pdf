"""Command-line interface; use --help for commands and examples."""

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

import yaml

from cv_lattex.lattes import read_lattes
from cv_lattex.models import CVError, catalog
from cv_lattex.output import write_outputs
from cv_lattex.rendering import export_data
from cv_lattex.selection import FIELD_GROUPS, THEMES, load_profile


def inspection(cv) -> dict:
    return {
        "name": cv.name,
        "sections": dict(Counter(entry.section for entry in cv.entries)),
        "entries": [
            {
                "id": entry.id,
                "section": entry.section,
                "title": entry.title(),
                "year": entry.year,
                "path": entry.path,
            }
            for entry in cv.entries
        ],
        "fields": dict(Counter(field.disposition for field in cv.fields)),
        "issues": [asdict(issue) for issue in cv.issues],
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Selecione e converta um currículo Lattes."
    )
    root.add_argument(
        "--version", action="version", version=f"%(prog)s {version('cv-lattex')}"
    )
    commands = root.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser(
        "inspect", help="listar seções, IDs e campos desconhecidos"
    )
    inspect.add_argument("input", type=Path, help="XML ou ZIP exportado do Lattes")
    inspect.add_argument(
        "--member", help="nome exato do XML dentro de um ZIP com vários XMLs"
    )
    inspect.add_argument(
        "--json", action="store_true", help="mostrar inventário em JSON"
    )
    export = commands.add_parser(
        "export",
        help="exportar YAML para RenderCV e relatório de cobertura",
        description="Gera YAML editável para RenderCV 2.8 e um relatório JSON, sem compilar PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Exemplos:
  cv-lattex inspect curriculo.zip
  cv-lattex export curriculo.xml -o cv.yaml --include education --include publications
  cv-lattex export curriculo.xml -o completo.yaml --full
  cv-lattex export curriculo.zip -o cv.yaml --profile perfil.yaml

Perfil YAML (as opções da CLI substituem as opções correspondentes do perfil):
  include: [profile, education, publications]
  exclude: [publications.press]
  order: [education, publications, profile]
  section_years:
    publications: {since: 2020, until: 2026}
  hide_fields: [contact, advisors, thesis]
  language: pt
  theme: classic

O perfil também aceita include_ids, exclude_ids, since, until, full,
allow_unmapped, sort (year_desc ou source) e unknown_year (keep ou exclude).
Listas da CLI usam opções repetidas. Seções aceitam prefixos como publications;
exclusões prevalecem. O nome permanece no cabeçalho mesmo ao selecionar só registros.
IDs vêm de inspect e podem mudar se o registro for editado ou ganhar duplicatas.
O ano do registro prioriza publicação/conclusão; sem ano, o filtro mantém o registro
e emite aviso por padrão. --full inclui o conteúdo conhecido, com dados privados,
metadados administrativos e variantes de outro idioma discriminados no relatório.
Em inglês, utiliza a tradução disponível no XML e conserva o original quando faltar.
Dados privados (documentos pessoais, endereço residencial etc.) não são exportados.
Campos conhecidos sem correspondência direta são apresentados como detalhes.
""",
    )
    export.add_argument("input", type=Path, help="XML ou ZIP exportado do Lattes")
    export.add_argument(
        "-o", "--output", required=True, type=Path, help="arquivo YAML de saída"
    )
    export.add_argument(
        "--report", type=Path, help="relatório JSON (padrão: saída.report.json)"
    )
    export.add_argument("--member", help="nome exato do XML dentro do ZIP")
    export.add_argument("--profile", type=Path, help="perfil de seleção em YAML")
    for name, description in {
        "include": "incluir seção ou prefixo (padrão: todas)",
        "exclude": "excluir seção ou prefixo",
        "include-id": "incluir somente registros com estes IDs",
        "exclude-id": "excluir registro por ID",
        "order": "priorizar seção na ordem de apresentação",
        "hide-field": "ocultar atributo XML ou grupo: " + ", ".join(FIELD_GROUPS),
    }.items():
        export.add_argument(
            f"--{name}", action="append", help=description + "; repetível"
        )
    export.add_argument("--since", type=int, help="ano inicial, inclusive")
    export.add_argument("--until", type=int, help="ano final, inclusive")
    export.add_argument(
        "--unknown-year",
        choices=("keep", "exclude"),
        help="tratamento de registros sem ano durante filtros",
    )
    export.add_argument(
        "--sort",
        choices=("year_desc", "source"),
        help="ordem dos registros dentro de cada seção",
    )
    export.add_argument("--language", choices=("pt", "en"), help="idioma (padrão: pt)")
    export.add_argument(
        "--theme", choices=THEMES, help="tema do RenderCV (padrão: classic)"
    )
    export.add_argument(
        "--full",
        action="store_true",
        default=None,
        help="incluir todo o conteúdo conhecido; incompatível com filtros",
    )
    export.add_argument(
        "--allow-unmapped",
        action="store_true",
        default=None,
        help="aceitar omissões de campos desconhecidos no modo completo",
    )
    export.add_argument(
        "--force",
        action="store_true",
        help="substituir saídas existentes, protegendo entrada e perfil",
    )
    return root


def _export(arguments, cv) -> None:
    overrides = {
        name: getattr(arguments, name)
        for name in (
            "include",
            "exclude",
            "order",
            "since",
            "until",
            "unknown_year",
            "sort",
            "language",
            "theme",
            "full",
            "allow_unmapped",
        )
    }
    overrides.update(
        include_ids=arguments.include_id,
        exclude_ids=arguments.exclude_id,
        hide_fields=arguments.hide_field,
    )
    profile = load_profile(arguments.profile, overrides)
    data, report = export_data(cv, profile)
    report_path = arguments.report or arguments.output.with_suffix(".report.json")
    protected = [arguments.input] + ([arguments.profile] if arguments.profile else [])
    write_outputs(
        [
            (
                arguments.output,
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100),
            ),
            (report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
        ],
        protected=protected,
        force=arguments.force,
    )
    print(f"YAML: {arguments.output}\nRelatório: {report_path}")
    omissions = report["counts"].get("unknown", 0) + report["counts"].get("unmapped", 0)
    if omissions:
        print(
            f"Aviso: {omissions} campos/elementos não mapeados; consulte o relatório.",
            file=sys.stderr,
        )
    if report["issues"]:
        print(f"Avisos no relatório: {len(report['issues'])}.", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        cv = read_lattes(arguments.input, member=arguments.member)
        if arguments.command == "export":
            _export(arguments, cv)
            return 0
        result = inspection(cv)
        if arguments.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(cv.name)
            for section, count in result["sections"].items():
                print(f"\n{section} — {catalog()['sections'][section]['pt']} ({count})")
                for entry in result["entries"]:
                    if entry["section"] == section:
                        print(f"  {entry['id']}  {entry['title']}")
            for issue in cv.issues:
                print(
                    f"Aviso [{issue.code}] {issue.path}: {issue.message}",
                    file=sys.stderr,
                )
        return 0
    except (CVError, OSError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
