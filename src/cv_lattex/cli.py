"""Command-line interface; use --help for commands and examples."""

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from importlib.metadata import version
from importlib.resources import as_file, files
from pathlib import Path

import yaml

from cv_lattex.backend import render_pdf, rendercv_version
from cv_lattex.lattes import read_lattes
from cv_lattex.models import CVError, catalog
from cv_lattex.output import check_outputs, write_outputs
from cv_lattex.rendering import export_data, label
from cv_lattex.sections import describe_sections, matching_sections
from cv_lattex.selection import FIELD_GROUPS, THEMES, load_profile
from cv_lattex.theme import BUNDLED_THEMES, load_theme

PRESETS = {
    "academico": "Cobertura ampla, bio, título do trabalho e orientação",
    "essencial": "Bio, formação, experiência e principais seções de produção",
    "resumido": "Menos seções, sem bio e sem listas de autores",
}


def inspection(cv, sections: list[str] | None = None) -> dict:
    names = {name for prefix in sections or [] for name in matching_sections(prefix)}
    entries = [entry for entry in cv.entries if not names or entry.section in names]
    return {
        "name": cv.name,
        "sections": dict(Counter(entry.section for entry in entries)),
        "entries": [
            {
                "id": entry.id,
                "section": entry.section,
                "type": entry.tag,
                "title": label(entry.tag)
                if entry.section == "education" and not entry.title_field()
                else entry.title(),
                "year": entry.year,
                "path": entry.path,
            }
            for entry in entries
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
    theme = commands.add_parser(
        "theme",
        help="copiar um tema para personalização",
        description="Copia design, templates e fontes para uma nova pasta.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Temas do cv-lattex:\n"
        + "\n".join(
            f"  {name:<12} {description}"
            for name, description in BUNDLED_THEMES.items()
        )
        + "\n\nExemplo:\n  cv-lattex theme garamond -o meu-tema\n"
        "  cv-lattex render curriculo.xml -o cv.pdf --theme meu-tema/design.yaml",
    )
    theme.add_argument("name", choices=(*THEMES, *BUNDLED_THEMES), help="tema inicial")
    theme.add_argument(
        "-o", "--output", required=True, type=Path, help="nova pasta do tema"
    )
    profile = commands.add_parser(
        "profile",
        help="copiar um preset para um perfil YAML editável",
        description="Copia um preset para um perfil YAML editável.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Presets:\n"
        + "\n".join(
            f"  {name:<10}  {description}" for name, description in PRESETS.items()
        )
        + "\n\nExemplo:\n  cv-lattex profile essencial -o meu.profile.yaml\n"
        "\nEdite o arquivo e use-o em export/render com --profile.\n"
        "Os presets não limitam anos, quantidade de registros ou páginas.",
    )
    profile.add_argument("preset", choices=PRESETS, help="perfil inicial")
    profile.add_argument(
        "-o", "--output", type=Path, help="arquivo YAML (padrão: stdout)"
    )
    profile.add_argument(
        "--force", action="store_true", help="substituir arquivo existente"
    )
    sections = commands.add_parser(
        "sections",
        help="listar seções e opções de perfil",
        description="Lista seções e opções de perfil.",
    )
    sections.add_argument(
        "section",
        nargs="?",
        help="seção ou prefixo (ex.: education, publications)",
    )
    inspect = commands.add_parser(
        "inspect", help="listar seções, IDs e campos desconhecidos"
    )
    inspect.add_argument("input", type=Path, help="XML ou ZIP exportado do Lattes")
    inspect.add_argument(
        "--section",
        action="append",
        help="filtrar registros exibidos por seção ou prefixo; repetível (campos e avisos continuam globais)",
    )
    inspect.add_argument(
        "--member", help="nome exato do XML dentro de um ZIP com vários XMLs"
    )
    inspect.add_argument(
        "--json", action="store_true", help="mostrar inventário em JSON"
    )
    conversion = argparse.ArgumentParser(
        add_help=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Exemplos:
  cv-lattex inspect curriculo.zip
  cv-lattex sections education
  cv-lattex export curriculo.xml -o cv.yaml --include education --include publications
  cv-lattex export curriculo.xml -o completo.yaml --full
  cv-lattex profile essencial -o perfil.yaml
  cv-lattex export curriculo.zip -o cv.yaml --profile perfil.yaml

Sem --profile, usa o preset academico. --full usa a exportação completa sem preset.
Um perfil explícito substitui o preset; as opções da CLI substituem suas chaves.

Perfil YAML:
  include: [profile, education, publications]
  exclude: [publications.press]
  order: [education, publications, profile]
  section_years:
    publications: {since: 2020, until: 2026}
  hide_fields: [contact, advisors, thesis]
  language: pt
  theme: classic
  authors:
    name_case: original
    highlight_self: true

Autores (todas as seções):
  authors.name_case        original | upper | title  (padrão: original)
    original  preservar grafia
    upper     tudo em maiúsculas
    title     inicial de cada palavra maiúscula, inclusive Da e De
  authors.highlight_self  true | false              (padrão: true)
    Negrito por ID CNPq; sem ID comparável, por nome completo exato e único.

O perfil também aceita include_ids, exclude_ids, since, until, full,
allow_unmapped, sections, sort (year_desc ou source) e unknown_year (keep ou exclude).
Consulte cv-lattex sections SEÇÃO para os ajustes disponíveis.
Listas da CLI usam opções repetidas. Seções aceitam prefixos como publications;
exclusões prevalecem. O nome permanece no cabeçalho mesmo ao selecionar só registros.
IDs vêm de inspect e podem mudar se o registro for editado ou ganhar duplicatas.
include_ids restringe todos os registros aos IDs listados; exclude_ids remove só os indicados.
header_links move IDs selecionados de technical.web para links no cabeçalho.
O ano do registro prioriza publicação/conclusão; sem ano, o filtro mantém o registro
e emite aviso por padrão. --full inclui o conteúdo conhecido, com dados privados,
metadados administrativos e variantes de outro idioma discriminados no relatório.
Em inglês, utiliza a tradução disponível no XML e conserva o original quando faltar.
Dados privados (documentos pessoais, endereço residencial etc.) não são exportados.
Afastamentos são incluídos somente com --include leave ou seleção explícita do ID.
As seções com apresentação enxuta conservam seu contexto principal; --full inclui os detalhes conhecidos.
hide_fields: [details] omite os detalhes genéricos das demais seções.
""",
    )
    conversion.add_argument("input", type=Path, help="XML ou ZIP exportado do Lattes")
    conversion.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="arquivo de saída (.yaml em export; .pdf em render)",
    )
    conversion.add_argument(
        "--report", type=Path, help="relatório JSON (padrão: saída.report.json)"
    )
    conversion.add_argument("--member", help="nome exato do XML dentro do ZIP")
    conversion.add_argument(
        "--profile",
        type=Path,
        help="perfil YAML (padrão: preset academico; exceto --full)",
    )
    for name, description in {
        "include": "incluir seção ou prefixo (substitui a lista do perfil)",
        "exclude": "excluir seção ou prefixo",
        "include-id": "incluir somente registros com estes IDs",
        "exclude-id": "excluir registro por ID",
        "order": "priorizar seção na ordem de apresentação",
        "hide-field": "ocultar atributo XML ou grupo: " + ", ".join(FIELD_GROUPS),
    }.items():
        conversion.add_argument(
            f"--{name}", action="append", help=description + "; repetível"
        )
    conversion.add_argument("--since", type=int, help="ano inicial, inclusive")
    conversion.add_argument("--until", type=int, help="ano final, inclusive")
    conversion.add_argument(
        "--unknown-year",
        choices=("keep", "exclude"),
        help="tratamento de registros sem ano durante filtros",
    )
    conversion.add_argument(
        "--sort",
        choices=("year_desc", "source"),
        help="ordem dos registros dentro de cada seção",
    )
    conversion.add_argument(
        "--language", choices=("pt", "en"), help="idioma (padrão: pt)"
    )
    conversion.add_argument(
        "--theme",
        metavar="NOME_OU_YAML",
        help="tema disponível ou design.yaml externo (padrão: classic; veja theme --help)",
    )
    conversion.add_argument(
        "--full",
        action="store_true",
        default=None,
        help="incluir todo o conteúdo conhecido; incompatível com filtros",
    )
    conversion.add_argument(
        "--allow-unmapped",
        action="store_true",
        default=None,
        help="aceitar omissões de campos desconhecidos no modo completo",
    )
    conversion.add_argument(
        "--force",
        action="store_true",
        help="substituir saídas existentes, protegendo entrada e perfil",
    )
    commands.add_parser(
        "export",
        parents=[conversion],
        help="exportar YAML para RenderCV e relatório de cobertura",
        description="Gera YAML editável para RenderCV 2.8 e um relatório JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=conversion.epilog,
    )
    render = commands.add_parser(
        "render",
        parents=[conversion],
        help="gerar PDF com um tema do RenderCV",
        description="Gera PDF, YAML editável e relatório JSON com o mesmo nome base.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Exemplos de PDF:
  cv-lattex render curriculo.xml -o cv.pdf --theme moderncv --include education
  cv-lattex render curriculo.zip -o completo.pdf --full
  cv-lattex render curriculo.xml -o cv.pdf --profile perfil.yaml
  cv-lattex render curriculo.xml -o cv.pdf --theme garamond
  cv-lattex render curriculo.xml -o cv.pdf --theme meu-tema/design.yaml

A primeira compilação precisa de internet para obter pacotes do Typst.
Para alterar o YAML gerado e compilar novamente: rendercv render cv.yaml.

"""
        + conversion.epilog,
    )
    render.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="limite de compilação em segundos (padrão: 120)",
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
    profile_sources = [arguments.profile] if arguments.profile else []
    if arguments.profile is None and not arguments.full:
        source = files("cv_lattex").joinpath("presets", "academico.yaml")
        with as_file(source) as path:
            profile = load_profile(path, overrides)
            profile_sources.append(path)
    else:
        profile = load_profile(arguments.profile, overrides)
    theme = load_theme(profile.theme)
    data, report = export_data(cv, profile, design=theme.design)
    is_pdf = arguments.command == "render"
    if is_pdf and arguments.output.suffix.lower() != ".pdf":
        raise CVError("A saída de render deve ter a extensão .pdf.")
    yaml_path = arguments.output.with_suffix(".yaml") if is_pdf else arguments.output
    report_path = arguments.report or arguments.output.with_suffix(".report.json")
    protected = [arguments.input] + profile_sources + theme.sources
    paths = [yaml_path, report_path] + ([arguments.output] if is_pdf else [])
    asset_paths = [yaml_path.parent.resolve() / name for name in theme.assets]
    check_outputs(paths, protected=protected + asset_paths, force=arguments.force)
    assets = theme.output_assets(yaml_path.parent)
    check_outputs(
        paths + [path for path, _ in assets],
        protected=protected,
        force=arguments.force,
        create_parents=True,
    )
    yaml_text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)
    contents = [(yaml_path, yaml_text)]
    if is_pdf:
        contents.append(
            (
                arguments.output,
                render_pdf(yaml_text, timeout=arguments.timeout, assets=theme.assets),
            )
        )
        report["renderer"] = {
            "name": "RenderCV",
            "version": rendercv_version(),
            "theme": profile.theme,
            "base_theme": theme.design["theme"],
        }
    contents.append(
        (report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    )
    contents.extend(assets)
    write_outputs(
        contents, protected=protected, force=arguments.force, create_parents=True
    )
    if is_pdf:
        print(f"PDF: {arguments.output}")
    print(f"YAML: {yaml_path}\nRelatório: {report_path}")
    if theme.assets:
        print(f"Arquivos do tema: {yaml_path.parent} (templates e fontes)")
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
        if arguments.command == "theme":
            target = arguments.output
            if target.exists() or target.is_symlink():
                raise CVError(
                    f"A pasta do tema já existe: {target}. Escolha uma nova pasta."
                )
            if not target.parent.is_dir():
                raise CVError(f"A pasta de destino não existe: {target.parent}.")
            theme = load_theme(arguments.name)
            contents = [
                (
                    target / "design.yaml",
                    yaml.safe_dump(
                        {"design": theme.design}, allow_unicode=True, sort_keys=False
                    ),
                ),
                *theme.output_assets(target),
            ]
            write_outputs(contents, protected=theme.sources, create_parents=True)
            print(f"Tema: {target / 'design.yaml'}")
            return 0
        if arguments.command == "profile":
            source = files("cv_lattex").joinpath("presets", arguments.preset + ".yaml")
            text = source.read_text("utf-8")
            if arguments.output:
                with as_file(source) as path:
                    write_outputs(
                        [(arguments.output, text)],
                        protected=[path],
                        force=arguments.force,
                    )
                print(f"Perfil: {arguments.output}")
            else:
                print(text, end="")
            return 0
        if arguments.command == "sections":
            print(describe_sections(arguments.section))
            return 0
        cv = read_lattes(arguments.input, member=arguments.member)
        if arguments.command in {"export", "render"}:
            _export(arguments, cv)
            return 0
        result = inspection(cv, arguments.section)
        if arguments.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(cv.name)
            for section, count in result["sections"].items():
                print(f"\n{section} — {catalog()['sections'][section]['pt']} ({count})")
                for entry in result["entries"]:
                    if entry["section"] == section:
                        title = entry["title"]
                        if section == "education" and title != label(entry["type"]):
                            title = f"{label(entry['type'])} — {title}"
                        year = f" ({entry['year']})" if entry["year"] else ""
                        print(f"  {entry['id']}  {title}{year}")
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
