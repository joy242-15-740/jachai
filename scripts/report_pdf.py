"""Build docs/report.pdf from docs/report.md: `make report-pdf`.

Markdown -> HTML (python-markdown) -> PDF (headless Google Chrome, A4). The text
and numbers come only from docs/report.md; this script adds layout only.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CSS = """
@page { size: A4; margin: 14mm 15mm; }
body { font-family: -apple-system, "Segoe UI", "Noto Sans Bengali", sans-serif;
       font-size: 9.6pt; line-height: 1.38; color: #1f2933; }
h1 { font-size: 15pt; margin: 0 0 4px; }
h2 { font-size: 11pt; margin: 10px 0 3px; color: #0b6e4f; }
p, li { margin: 3px 0; }
ul, ol { padding-left: 16px; margin: 3px 0; }
table { border-collapse: collapse; width: 100%; font-size: 8.6pt; margin: 4px 0; }
th, td { border: 1px solid #d9dee3; padding: 2px 5px; text-align: left; }
th { background: #f0f4f2; }
code { font-size: 8.6pt; }
a { color: #0b6e4f; text-decoration: none; }
"""


def main() -> None:
    md = (ROOT / "docs" / "report.md").read_text(encoding="utf-8")
    body = markdown.markdown(md, extensions=["tables"])
    head = f"<meta charset='utf-8'><style>{CSS}</style>"
    html = f"<!doctype html><html><head>{head}</head><body>{body}</body></html>"
    out = ROOT / "docs" / "report.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "report.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run(
            [
                CHROME,
                "--headless",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={out}",
                page.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
    pages = out.read_bytes().count(b"/Type /Page") - out.read_bytes().count(b"/Type /Pages")
    print(f"Wrote {out} ({pages} pages)")
    if pages > 3:
        sys.exit(f"report is {pages} pages; the limit is 3")


if __name__ == "__main__":
    main()
