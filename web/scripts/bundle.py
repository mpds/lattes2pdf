"""Build an allowlisted, integrity-checked static runtime (no document inputs)."""

import argparse
import hashlib
import io
import json
import shutil
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from lattes2pdf.theme import THEMES

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
OUT = WEB / "public/generated"
CACHE = WEB / ".cache/downloads"
LOCK = WEB / "runtime-lock.json"
PYODIDE = "314.0.6"
PURE = {
    "rendercv": "2.8",
    "rendercv-fonts": "0.5.1",
    "markdown": "3.10.3",
    "phonenumbers": "9.0.39",
    "pydantic-extra-types": "2.11.1",
    "email-validator": "2.3.0",
    "dnspython": "2.8.0",
    "idna": "3.19",
    "defusedxml": "0.7.1",
}
FAMILIES = {
    "Source Sans 3",
    "Gentium Book Plus",
    "Ubuntu",
    "Raleway",
    "XCharter",
    "EB Garamond",
    "Fontin",
    "Lato",
    "Font Awesome 7",
}


def fetch(url):
    with urllib.request.urlopen(url, timeout=90) as response:
        return response.read()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def download(spec):
    target = CACHE / spec["sha256"]
    if not target.exists():
        data = fetch(spec["url"])
        if digest(data) != spec["sha256"]:
            raise ValueError("Dependency checksum mismatch: " + spec["url"])
        target.write_bytes(data)
    data = target.read_bytes()
    if digest(data) != spec["sha256"]:
        raise ValueError("Cached checksum mismatch")
    return data


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--refresh-lock", action="store_true")
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    pyroot = WEB / "node_modules/pyodide"
    pylock = json.loads((pyroot / "pyodide-lock.json").read_text())
    packages = {}

    def add(name):
        name = name.replace("_", "-").lower()
        if name in packages:
            return
        item = pylock["packages"][name]
        packages[name] = item
        for dependency in item["depends"]:
            add(dependency)

    for name in ["pydantic", "pyyaml", "jinja2", "ruamel-yaml"]:
        add(name)
    if args.refresh_lock:
        dependencies = {}
        for name, version in PURE.items():
            meta = json.loads(fetch(f"https://pypi.org/pypi/{name}/{version}/json"))
            wheel = next(
                x for x in meta["urls"] if x["filename"].endswith("none-any.whl")
            )
            dependencies[name] = dict(
                url=wheel["url"],
                sha256=wheel["digests"]["sha256"],
                file=wheel["filename"],
            )
        for name, item in packages.items():
            dependencies[name] = dict(
                url=f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE}/full/{item['file_name']}",
                sha256=item["sha256"],
                file=item["file_name"],
            )
        for name, url in {
            "fontawesome": "https://packages.typst.org/preview/fontawesome-0.6.0.tar.gz",
            "typst-assets": "https://static.crates.io/crates/typst-assets/typst-assets-0.14.2.crate",
        }.items():
            data = fetch(url)
            dependencies[name] = dict(url=url, sha256=digest(data))
            (CACHE / digest(data)).write_bytes(data)
        LOCK.write_text(json.dumps(dependencies, indent=2) + "\n")
    dependencies = json.loads(LOCK.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(OUT)
    OUT.mkdir()
    assets = []

    def put(path, data, kind):
        dest = OUT / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        assets.append(dict(path=path, sha256=digest(data), size=len(data), kind=kind))

    for name in [
        "pyodide.mjs",
        "pyodide.asm.mjs",
        "pyodide.asm.wasm",
        "python_stdlib.zip",
    ]:
        put("pyodide/" + name, (pyroot / name).read_bytes(), "runtime")
    pylock["packages"] = packages
    put("pyodide/pyodide-lock.json", json.dumps(pylock).encode(), "runtime")
    for name, item in packages.items():
        put(
            "pyodide/" + item["file_name"],
            download(dependencies[name]),
            "pyodide-package",
        )
    for name in PURE:
        data = download(dependencies[name])
        with zipfile.ZipFile(io.BytesIO(data)) as wheel:
            if name == "rendercv-fonts":
                put(
                    "licenses/rendercv-fonts.txt",
                    wheel.read("rendercv_fonts-0.5.1.dist-info/licenses/LICENSE"),
                    "license",
                )
                for member in wheel.namelist():
                    parts = Path(member).parts
                    if (
                        len(parts) == 3
                        and parts[0] == "rendercv_fonts"
                        and parts[1] in FAMILIES
                    ):
                        put(
                            "fonts/" + parts[1] + "/" + parts[2],
                            wheel.read(member),
                            "font" if member.endswith((".otf", ".ttf")) else "license",
                        )
            else:
                put("wheels/" + dependencies[name]["file"], data, "wheel")
            if name == "rendercv":
                for member in ["lib.typ", "typst.toml"]:
                    put(
                        "packages/preview/rendercv/0.3.0/" + member,
                        wheel.read("rendercv/renderer/rendercv_typst/" + member),
                        "typst-package",
                    )
    for name in ["fontawesome", "typst-assets"]:
        with tarfile.open(fileobj=io.BytesIO(download(dependencies[name]))) as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                path = Path(member.name)
                if name == "fontawesome" and path.suffix in {".typ", ".toml"}:
                    put(
                        "packages/preview/fontawesome/0.6.0/" + path.as_posix(),
                        archive.extractfile(member).read(),
                        "typst-package",
                    )
                elif name == "fontawesome" and path.name == "LICENSE":
                    put(
                        "licenses/fontawesome.txt",
                        archive.extractfile(member).read(),
                        "license",
                    )
                elif name == "typst-assets" and (
                    ("fonts" in path.parts and path.suffix in {".ttf", ".otf"})
                    or path.name.startswith(("LICENSE", "NOTICE"))
                ):
                    put(
                        "fonts/typst/" + "/".join(path.parts[1:]),
                        archive.extractfile(member).read(),
                        "font" if path.suffix in {".ttf", ".otf"} else "license",
                    )
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((ROOT / "src/lattes2pdf").rglob("*")):
            if path.is_file() and path.suffix in {".py", ".json", ".yaml"}:
                archive.write(path, path.relative_to(ROOT / "src"))
        for path in sorted((WEB / "python").glob("*.py")):
            archive.write(path, path.name)
    put("application.zip", content.getvalue(), "application")
    put(
        "compiler.wasm",
        (
            WEB
            / "node_modules/@myriaddreamin/typst-ts-web-compiler/pkg/typst_ts_web_compiler_bg.wasm"
        ).read_bytes(),
        "compiler",
    )
    for name in [
        "logo-horizontal-with-text-transparent-bg.png",
        "logo-without-text-transparent-bg.png",
        "social-preview.png",
    ]:
        put("brand/" + name, (ROOT / "assets" / name).read_bytes(), "image")
    for theme in THEMES:
        path = WEB / ".cache/samples" / (theme + ".png")
        if not path.is_file():
            raise FileNotFoundError(
                "Generate all nine thumbnails first: python scripts/samples.py"
            )
        put("themes/" + path.name, path.read_bytes(), "image")
    put("licenses/lattes2pdf.txt", (ROOT / "LICENSE").read_bytes(), "license")
    notices = json.loads((WEB / "third-party/index.json").read_text())
    for item in notices["notices"]:
        data = (WEB / "third-party" / item["file"]).read_bytes()
        if digest(data) != item["sha256"]:
            raise ValueError("Third-party notice checksum mismatch: " + item["file"])
        put("licenses/" + item["file"], data, "license")
    put("licenses/index.json", json.dumps(notices, indent=2).encode(), "license")
    (OUT / "manifest.json").write_text(
        json.dumps(
            dict(pyodide=PYODIDE, packages=list(packages), assets=assets),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        f"Bundled {len(assets)} assets, {sum(a['size'] for a in assets) / 1024**2:.1f} MiB"
    )


if __name__ == "__main__":
    main()
