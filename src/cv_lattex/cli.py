"""Command-line interface; use --help for commands and examples."""

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from cv_lattex.lattes import read_lattes
from cv_lattex.models import CVError, catalog


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
    return root


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        cv = read_lattes(arguments.input, member=arguments.member)
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
