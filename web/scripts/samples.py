"""Generate all theme thumbnails from one fictitious fixture, locally."""

import subprocess
from importlib.resources import files
from pathlib import Path

import yaml

from lattes2pdf.backend import render_pdf
from lattes2pdf.lattes import read_lattes
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import load_profile
from lattes2pdf.theme import THEMES

WEB = Path(__file__).resolve().parents[1]
OUTPUT = WEB / ".cache/samples"
OUTPUT.mkdir(parents=True, exist_ok=True)
cv = read_lattes(WEB.parent / "tests/fixtures/academic.xml")
for theme in THEMES:
    profile = load_profile(files("lattes2pdf").joinpath("presets/resumido.yaml"))
    profile.theme = theme
    data, _ = export_data(cv, profile)
    path = OUTPUT / f"{theme}.pdf"
    path.write_bytes(
        render_pdf(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    )
    subprocess.run(
        [
            "pdftoppm",
            "-r",
            "85",
            "-png",
            "-singlefile",
            str(path),
            str(path.with_suffix("")),
        ],
        check=True,
    )
print("Nine fictitious thumbnails generated in web/.cache/samples")
