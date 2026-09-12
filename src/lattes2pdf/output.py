"""Write output files without replacing inputs or silently overwriting results."""

import os
import tempfile
from pathlib import Path

from lattes2pdf.models import CVError


def _same_path(first: Path, second: Path) -> bool:
    return first.resolve() == second.resolve() or (
        first.exists() and second.exists() and first.samefile(second)
    )


def check_outputs(
    paths: list[Path],
    *,
    protected: list[Path],
    force: bool = False,
    create_parents: bool = False,
) -> None:
    for index, path in enumerate(paths):
        if any(_same_path(path, other) for other in protected + paths[:index]):
            raise CVError(
                "As saídas devem ser distintas da entrada, do perfil e entre si."
            )
        if path.is_symlink():
            raise CVError(f"A saída não pode ser um link simbólico: {path}.")
        if create_parents:
            for parent in path.parents:
                if parent.exists() and not parent.is_dir():
                    raise CVError(f"Pasta de saída inválida: {parent}.")
                if any(_same_path(parent, other) for other in protected + paths):
                    raise CVError(
                        "Uma pasta de saída coincide com um arquivo protegido ou de saída."
                    )
        if path.exists() and (not force or not path.is_file()):
            raise CVError(
                f"A saída já existe: {path}. Use --force para substituir um arquivo."
            )
        if not create_parents and not path.parent.is_dir():
            raise CVError(f"A pasta de saída não existe: {path.parent}.")


def write_outputs(
    contents: list[tuple[Path, str | bytes]],
    *,
    protected: list[Path],
    force: bool = False,
    create_parents: bool = False,
) -> None:
    check_outputs(
        [path for path, _ in contents],
        protected=protected,
        force=force,
        create_parents=create_parents,
    )
    temporary = []
    created = []
    try:
        for path, content in contents:
            if create_parents:
                missing = []
                parent = path.parent
                while not parent.exists():
                    missing.append(parent)
                    parent = parent.parent
                for parent in reversed(missing):
                    parent.mkdir()
                    created.append(parent)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                delete=False,
            ) as stream:
                temporary.append((Path(stream.name), path))
                stream.write(
                    content.encode("utf-8") if isinstance(content, str) else content
                )
        for source, destination in temporary:
            if force:
                os.replace(source, destination)
            else:
                # Linking fails if a file appeared after preflight; it cannot clobber it.
                os.link(source, destination)
    finally:
        for source, _ in temporary:
            source.unlink(missing_ok=True)
        for directory in reversed(created):
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
