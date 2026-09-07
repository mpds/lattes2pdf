"""Compile generated YAML through RenderCV's public CLI in a private directory."""

import os
import subprocess
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from cv_lattex.models import CVError


def rendercv_version() -> str:
    try:
        installed = version("rendercv")
    except PackageNotFoundError as exc:
        raise CVError(
            'RenderCV não está instalado. Execute: python -m pip install "rendercv[full]>=2.8,<2.9".'
        ) from exc
    if installed.split(".")[:2] != ["2", "8"]:
        raise CVError(
            f"RenderCV {installed} não é suportado; instale rendercv[full]>=2.8,<2.9."
        )
    return installed


def render_pdf(yaml_text: str, *, timeout: int = 120) -> bytes:
    rendercv_version()
    if timeout <= 0:
        raise CVError("O tempo limite deve ser maior que zero.")
    with tempfile.TemporaryDirectory(prefix="cv-lattex-") as directory:
        root = Path(directory)
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
                f"RenderCV excedeu o limite de {timeout} segundos; aumente --timeout."
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
                    "A primeira compilação precisa de acesso a packages.typst.org; tente novamente com acesso à rede."
                )
            raise CVError(
                "RenderCV não gerou o PDF.\n"
                + (diagnostics[-6000:] or "Nenhum diagnóstico retornado.")
            )
        data = output.read_bytes()
        if not data.startswith(b"%PDF-"):
            raise CVError("RenderCV retornou um arquivo que não é PDF.")
        return data
