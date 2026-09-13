"""Loopback-only static production preview, with no extra runtime headers."""

import argparse
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "dist"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_head(self):
        if not self.path.startswith("/lattes2pdf/"):
            self.send_error(404)
            return None
        self.path = self.path.removeprefix("/lattes2pdf")
        return super().send_head()

    def log_message(self, *_args):
        pass


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    if not (ROOT / "index.html").is_file():
        raise SystemExit("Run npm run build first.")
    with ThreadingHTTPServer(("127.0.0.1", 4173), Handler) as server:
        print(
            f"Static preview: http://127.0.0.1:4173/lattes2pdf/ (PID {os.getpid()}; Ctrl+C to stop)",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
