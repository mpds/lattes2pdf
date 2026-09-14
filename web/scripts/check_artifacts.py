"""Check only the intended static files and current Python distributions."""

import gzip
import hashlib
import json
import tarfile
import tomllib
import zipfile
from pathlib import Path

from lattes2pdf.theme import THEMES

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "web/dist"
GENERATED = DIST / "generated"
manifest = json.loads((GENERATED / "manifest.json").read_text())
expected = {"manifest.json", *(asset["path"] for asset in manifest["assets"])}
actual = {
    path.relative_to(GENERATED).as_posix()
    for path in GENERATED.rglob("*")
    if path.is_file()
}
assert actual == expected, (actual - expected, expected - actual)
assert not any(
    "fontin" in path.lower()
    and Path(path).suffix in {".otf", ".ttf", ".woff", ".woff2"}
    for path in actual
), "Fontin must not be distributed in the browser bundle"
for asset in manifest["assets"]:
    raw = (GENERATED / asset["path"]).read_bytes()
    assert len(raw) == asset["size"]
    assert hashlib.sha256(raw).hexdigest() == asset["sha256"], asset["path"]

assert {p.stem for p in (GENERATED / "themes").iterdir()} == set(THEMES)
for name in [
    "logo-horizontal-with-text-transparent-bg.png",
    "logo-without-text-transparent-bg.png",
]:
    assert (GENERATED / "brand" / name).read_bytes() == (
        ROOT / "assets" / name
    ).read_bytes()
source = {
    p.relative_to(ROOT / "src").as_posix(): p.read_bytes()
    for p in (ROOT / "src/lattes2pdf").rglob("*")
    if p.is_file() and p.suffix in {".py", ".yaml", ".json"}
}
source.update({p.name: p.read_bytes() for p in (ROOT / "web/python").glob("*.py")})
with zipfile.ZipFile(GENERATED / "application.zip") as archive:
    assert set(archive.namelist()) == set(source)
    assert all(archive.read(name) == content for name, content in source.items())
for path in DIST.rglob("*"):
    if not path.is_file() or path.is_relative_to(GENERATED):
        continue
    assert path in {DIST / "index.html", DIST / "sitemap.xml"} or (
        path.parent == DIST / "assets" and path.suffix in {".js", ".css"}
    ), path

version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
artifacts = [
    ROOT / f"dist/lattes2pdf-{version}-py3-none-any.whl",
    ROOT / f"dist/lattes2pdf-{version}.tar.gz",
]
for path in artifacts:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    else:
        with tarfile.open(path) as archive:
            names = archive.getnames()
    for name in names:
        assert not set(Path(name).parts) & {
            ".local",
            "web",
            ".git",
            ".DS_Store",
            ".venv",
            "node_modules",
        }, name
        assert not name.endswith((".pdf", ".zip")), name

files = [p for p in DIST.rglob("*") if p.is_file()]
report = dict(
    static_files=len(files),
    runtime_assets=len(manifest["assets"]),
    uncompressed_bytes=sum(p.stat().st_size for p in files),
    estimated_gzip_bytes=sum(
        len(gzip.compress(p.read_bytes(), mtime=0)) for p in files
    ),
    application_matches_source=True,
    python_distributions=[p.name for p in artifacts],
    unexpected_files=[],
)
output = ROOT / ".local/browser-app-evidence/artifact-audit.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
