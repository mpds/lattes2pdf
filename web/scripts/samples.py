"""Build fictitious theme previews with the browser's typography."""

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from lattes2pdf.backend import render_pdf
from lattes2pdf.lattes import read_lattes
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import load_profile
from lattes2pdf.theme import THEMES

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB / "python"))
from browser_design import apply_browser_typography  # noqa: E402

OUTPUT = WEB / ".cache/samples"
OUTPUT.mkdir(parents=True, exist_ok=True)
with TemporaryDirectory(prefix="lattes2pdf-samples-") as temporary:
    for theme in THEMES:
        path = WEB.parent / "examples/pdfs" / f"{theme}.pdf"
        if theme == "moderncv":
            profile = load_profile(WEB.parent / "examples/profile.yaml")
            profile.theme = theme
            data, _ = export_data(
                read_lattes(WEB.parent / "examples/curriculo.xml"), profile
            )
            apply_browser_typography(data["design"])
            path = Path(temporary) / f"{theme}.pdf"
            path.write_bytes(
                render_pdf(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
            )
        subprocess.run(
            [
                "pdftoppm",
                "-scale-to",
                "960",
                "-png",
                "-singlefile",
                str(path),
                str(OUTPUT / theme),
            ],
            check=True,
        )
print("Nine fictitious thumbnails generated in web/.cache/samples")
