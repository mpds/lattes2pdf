"""Exercise an installed wheel outside the checkout, with fictional input."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import venv
from pathlib import Path


def check(wheel: Path, fixture: Path) -> None:
    wheel, fixture = wheel.resolve(), fixture.resolve()
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    with tempfile.TemporaryDirectory(prefix="lattes2pdf-distribution-") as directory:
        root = Path(directory)
        venv.EnvBuilder(with_pip=True).create(root / "venv")
        python = root / "venv/bin/python"
        cli = root / "venv/bin/lattes2pdf"
        rendercv = root / "venv/bin/rendercv"
        work = root / "work"
        work.mkdir()

        def run(*args: str | Path) -> str:
            result = subprocess.run(
                [str(arg) for arg in args],
                cwd=work,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=300,
            )
            if result.returncode:
                raise RuntimeError(result.stdout)
            return result.stdout

        print(run(python, "-m", "pip", "install", str(wheel)), flush=True)
        print(run(python, "-m", "pip", "check"), flush=True)
        run(
            python,
            "-I",
            "-c",
            "from pathlib import Path; import lattes2pdf; "
            "assert 'site-packages' in Path(lattes2pdf.__file__).parts",
        )
        shutil.copyfile(fixture, work / "curriculo.xml")
        print(run(cli, "--version"), flush=True)
        inventory = json.loads(run(cli, "inspect", "curriculo.xml", "--json"))
        article = next(
            e["id"]
            for e in inventory["entries"]
            if e["section"] == "publications.articles"
        )
        run(cli, "profile", "academico", "-o", "profile.yaml")
        for name in ("default", "explicit", "full", "moderncv", "garamond", "external"):
            (work / name).mkdir()
        run(cli, "export", "curriculo.xml", "-o", "default/cv.yaml")
        run(
            cli,
            "export",
            "curriculo.xml",
            "--profile",
            "profile.yaml",
            "-o",
            "explicit/cv.yaml",
        )
        assert (work / "default/cv.yaml").read_bytes() == (
            work / "explicit/cv.yaml"
        ).read_bytes()
        run(cli, "export", "curriculo.xml", "--full", "-o", "full/cv.yaml")
        assert (work / "full/cv.yaml").read_bytes() != (
            work / "default/cv.yaml"
        ).read_bytes()
        for theme in ("moderncv", "garamond"):
            run(
                cli,
                "render",
                "curriculo.xml",
                "--theme",
                theme,
                "-o",
                f"{theme}/cv.pdf",
            )
        run(cli, "theme", "garamond", "-o", "editable-theme")
        run(
            cli,
            "render",
            "curriculo.xml",
            "--theme",
            "editable-theme/design.yaml",
            "-o",
            "external/cv.pdf",
        )
        shutil.rmtree(work / "editable-theme")
        run(
            python,
            "-c",
            "from pathlib import Path; import yaml; p=Path('external/cv.yaml'); "
            "data=yaml.safe_load(p.read_text()); data['cv']['name']='Pessoa Editada'; "
            "p.write_text(yaml.safe_dump(data,allow_unicode=True,sort_keys=False))",
        )
        run(
            rendercv,
            "render",
            "external/cv.yaml",
            "--pdf-path",
            "edited.pdf",
            "-nomd",
            "-nopng",
        )
        run(
            cli,
            "export",
            "curriculo.xml",
            "--exclude-id",
            article,
            "-o",
            "selected.yaml",
        )
        report = json.loads((work / "selected.report.json").read_text())
        assert (
            next(e for e in report["entries"] if e["id"] == article)["status"]
            == "excluded"
        )
        for name in (
            "moderncv/cv.pdf",
            "garamond/cv.pdf",
            "external/cv.pdf",
            "external/edited.pdf",
        ):
            pdf = (work / name).read_bytes()
            assert pdf.startswith(b"%PDF") and len(pdf) > 1000, name
        assert (work / "external/fonts/OFL.txt").is_file()
        assert (work / "external/classic/entries/PublicationEntry.j2.typ").is_file()
        print(
            "Installed wheel: CLI, profiles, selection, themes and standalone RenderCV passed."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    check(args.wheel, args.fixture)
