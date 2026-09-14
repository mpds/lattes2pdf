"""Compare captured production-browser results with independent native CLI output."""

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from PIL import Image, ImageChops
from pypdf import PdfReader

from lattes2pdf.backend import render_pdf
from lattes2pdf.lattes import read_lattes
from lattes2pdf.rendering import export_data
from lattes2pdf.selection import load_profile

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / ".local/browser-app-evidence/parity"
CASES = json.loads((EVIDENCE / "cases.json").read_text())
long_only = "--long-only" in sys.argv
if long_only:
    CASES = [case for case in CASES if case["fixture"] == "long-adversarial.xml"]
results = json.loads((EVIDENCE / "results.json").read_text()) if long_only else []
for case in CASES:
    key = case["key"]
    profile = load_profile(EVIDENCE / f"{key}.profile.yaml")
    source = (
        ROOT
        / (
            "web/tests/fixtures"
            if case["fixture"] == "long-adversarial.xml"
            else "tests/fixtures"
        )
        / case["fixture"]
    )
    data, report = export_data(read_lattes(source), profile)
    if profile.theme == "moderncv":
        data["design"].setdefault("typography", {})["font_family"] = "XCharter"
    assert yaml.safe_load((EVIDENCE / f"{key}.yaml").read_text()) == data, key + " YAML"
    browser_report = json.loads((EVIDENCE / f"{key}.report.json").read_text())
    assert {k: v for k, v in browser_report.items() if k != "renderer"} == report, (
        key + " coverage"
    )
    native = EVIDENCE / f"{key}.native.pdf"
    native.write_bytes(
        render_pdf(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    )
    readers = [PdfReader(EVIDENCE / f"{key}.pdf"), PdfReader(native)]
    assert len(readers[0].pages) == len(readers[1].pages), key + " pages"
    for first, second in zip(readers[0].pages, readers[1].pages):
        assert first.mediabox == second.mediabox
        assert re.sub(r"\s+", "", first.extract_text()) == re.sub(
            r"\s+", "", second.extract_text()
        ), key + " text"
    if case["fixture"] == "long-adversarial.xml":
        literal = "\n".join(page.extract_text() for page in readers[0].pages)
        assert literal.count("#read(") == 14, key + " literal text"
    for reader in readers:
        root = reader.trailer["/Root"]
        assert "/OpenAction" not in root and "/AA" not in root
        assert not root.get("/Names", {}).get("/EmbeddedFiles")
        assert not root.get("/Names", {}).get("/JavaScript")
        for page in reader.pages:
            assert "/AA" not in page
            for ref in page.get("/Annots", []):
                annotation = ref.get_object()
                assert "/AA" not in annotation
                action = annotation.get("/A")
                if action:
                    assert action.get("/S") == "/URI", (key, action)
                    assert urlsplit(action.get("/URI", "")).scheme in {
                        "https",
                        "http",
                        "mailto",
                        "tel",
                    }, (key, action)
    for kind, path in [("browser", EVIDENCE / f"{key}.pdf"), ("native", native)]:
        subprocess.run(
            [
                "pdftoppm",
                "-r",
                "100",
                "-png",
                str(path),
                str(EVIDENCE / f"{key}-{kind}"),
            ],
            check=True,
        )
    pixels = []
    for browser_png in sorted(EVIDENCE.glob(f"{key}-browser-*.png")):
        native_png = browser_png.with_name(
            browser_png.name.replace("-browser-", "-native-")
        )
        first = Image.open(browser_png).convert("RGB")
        second = Image.open(native_png).convert("RGB")
        assert first.size == second.size
        diff = ImageChops.difference(first, second)
        changed = sum(pixel != (0, 0, 0) for pixel in diff.get_flattened_data())
        ratio = changed / (first.width * first.height)
        assert ratio <= 0.0005, (key, "visual difference", ratio)
        pixels.append(
            {"page": browser_png.name, "different_pixels": changed, "ratio": ratio}
        )
    results.append(
        dict(
            case=key,
            pages=len(readers[0].pages),
            pixels=pixels,
            yaml=True,
            report=True,
            text=True,
            safe_actions=True,
        )
    )
    print(
        "PARITY",
        key,
        "pages",
        len(readers[0].pages),
        "changed pixels",
        sum(p["different_pixels"] for p in pixels),
        flush=True,
    )
(EVIDENCE / "results.json").write_text(json.dumps(results, indent=2) + "\n")
