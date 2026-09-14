"""Rasterize the existing, fictitious example PDFs for the theme gallery."""

import subprocess
from pathlib import Path

from lattes2pdf.theme import THEMES

WEB = Path(__file__).resolve().parents[1]
OUTPUT = WEB / ".cache/samples"
OUTPUT.mkdir(parents=True, exist_ok=True)
for theme in THEMES:
    path = WEB.parent / "examples/pdfs" / f"{theme}.pdf"
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
