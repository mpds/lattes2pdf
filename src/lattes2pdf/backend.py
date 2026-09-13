"""Compile generated YAML through RenderCV's public CLI in a private directory."""

import os
import subprocess
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from lattes2pdf.models import CVError


def rendercv_version() -> str:
    try:
        installed = version("rendercv")
    except PackageNotFoundError as exc:
        raise CVError(
            'RenderCV não está instalado. Execute: python -m pip install "rendercv[full]>=2.8,<2.9".',
            code="renderer-unavailable",
        ) from exc
    if installed.split(".")[:2] != ["2", "8"]:
        raise CVError(
            f"RenderCV {installed} não é suportado; instale rendercv[full]>=2.8,<2.9.",
            code="renderer-unavailable",
        )
    return installed


def render_pdf(
    yaml_text: str, *, timeout: int = 120, assets: dict[Path, bytes] | None = None
) -> bytes:
    rendercv_version()
    if timeout <= 0:
        raise CVError("O tempo limite deve ser maior que zero.")
    with tempfile.TemporaryDirectory(prefix="lattes2pdf-") as directory:
        root = Path(directory)
        for relative, content in (assets or {}).items():
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or len(relative.parts) < 2
            ):
                raise CVError("Caminho de arquivo do tema inválido.")
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (root / "input.yaml").write_text(yaml_text, encoding="utf-8")
        command = [
            sys.executable,
            "-m",
            "rendercv",
            "render",
            "input.yaml",
            "--pdf-path",
            "output.pdf",
            "--typst-path",
            "output.typ",
            "--dont-generate-markdown",
            "--dont-generate-html",
            "--dont-generate-png",
        ]
        try:
            result = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                timeout=timeout,
                env={**os.environ, "NO_COLOR": "1", "COLUMNS": "120"},
            )
        except subprocess.TimeoutExpired as exc:
            raise CVError(
                f"RenderCV excedeu o limite de {timeout} segundos; aumente --timeout.",
                code="renderer-timeout",
            ) from exc
        output = root / "output.pdf"
        if result.returncode or not output.is_file():
            diagnostics = (
                (result.stdout + result.stderr)
                .decode("utf-8", errors="replace")
                .strip()
            )
            if "failed to download package" in diagnostics:
                raise CVError(
                    "RenderCV não conseguiu baixar uma dependência do Typst. "
                    "A primeira compilação precisa de acesso a packages.typst.org; tente novamente com acesso à rede.",
                    code="renderer-download-failed",
                    details=diagnostics,
                )
            raise CVError(
                "RenderCV não gerou o PDF. Confira o YAML e o tema; use --log-level DEBUG para ver os detalhes.",
                code="renderer-failed",
                details=diagnostics or "Nenhum diagnóstico retornado.",
            )
        data = output.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise CVError(
                "RenderCV retornou um arquivo que não é PDF.",
                code="renderer-invalid-output",
            )
        return data
