"""Build the static site served by GitHub Pages from docs/ (https://eartherai.github.io/zerodrop/).

- /            the dashboard in replay mode: recorded real runs, no server, no model calls
- /evidence/   EVIDENCE.md as a page, with the key Neatlogs captures on top
- /video/      the demo video

    uv run python scripts/build_site.py

Needs Node (the UI build and `npx marked`). docs/ also holds the project's Markdown documents;
this script only touches index.html, 404.html, .nojekyll, assets/, evidence/ and video/.
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
BASE = "/zerodrop/"
REPO = "https://github.com/Eartherai/zerodrop"
RAW = "https://raw.githubusercontent.com/Eartherai/zerodrop/main"
SHOTS = [
    ("20-neatlogs-incidents-board-three-raised.png", "Neatlogs raised three incidents from our traces"),
    (
        "21-neatlogs-incident-false-success-resolved-full-report.png",
        "The critical incident: root cause, evidence, recommended action",
    ),
    ("18-neatlogs-before-false-success-flagged.png", "Before: 182 records written, false success claim true"),
    ("19-neatlogs-after-early-check-stops-the-run.png", "After: the early check stops the run at 28 records"),
    (
        "23-neatlogs-false-success-detector-flagged-spans.png",
        "The detector Neatlogs AI suggested, flagging real-model runs",
    ),
    ("22-neatlogs-incidents-board-three-resolved.png", "All three incidents resolved"),
]
PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZeroDrop evidence</title>
<style>
:root {{ --bg: #f6f4ee; --fg: #17201c; --muted: #5d6a63; --line: #d8d3c4; --panel: #fffdf7; --accent: #1f6f5c; --bad: #b3261e; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #10161a; --fg: #e8ecea; --muted: #9aa8a1; --line: #2a343a; --panel: #161e23; --accent: #5fd0b0; --bad: #ff8a80; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.6 "IBM Plex Sans", system-ui, sans-serif; }}
header, main {{ max-width: 1040px; margin: 0 auto; padding: 0 16px; }}
header {{ padding-top: 28px; }}
nav {{ display: flex; flex-wrap: wrap; gap: 8px 20px; font-size: 15px; }}
a {{ color: var(--accent); }}
h1 {{ font-size: 34px; line-height: 1.15; margin: 18px 0 6px; }}
h2 {{ font-size: 24px; margin: 44px 0 10px; padding-top: 14px; border-top: 1px solid var(--line); }}
.lede {{ color: var(--muted); max-width: 70ch; }}
.shots {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; margin: 24px 0 8px; }}
figure {{ margin: 0; background: var(--panel); border: 1px solid var(--line); }}
figure img {{ display: block; width: 100%; height: 220px; object-fit: cover; object-position: top; background: #fff; }}
figcaption {{ padding: 10px 12px; font-size: 14px; }}
video {{ width: 100%; max-width: 860px; display: block; margin: 12px 0; background: #000; }}
.scroll {{ overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14.5px; margin: 14px 0; background: var(--panel); }}
th, td {{ border: 1px solid var(--line); padding: 7px 10px; text-align: left; vertical-align: top; }}
th {{ font-weight: 600; }}
code {{ font: 13px/1.4 "IBM Plex Mono", ui-monospace, monospace; background: color-mix(in srgb, var(--line) 45%, transparent); padding: 1px 4px; overflow-wrap: anywhere; }}
footer {{ max-width: 1040px; margin: 48px auto 40px; padding: 0 16px; color: var(--muted); font-size: 14px; }}
</style>
</head>
<body>
<header>
<nav><a href="{base}">Dashboard (replay of real runs)</a><a href="{base}evidence/">Evidence</a><a href="{base}video/zerodrop-demo.mp4">Demo video</a><a href="{repo}">Repository</a><a href="{cfo}">cfo.ai plan</a><a href="https://entire.io/et/hackathone/hackathon">Entire</a></nav>
<h1>ZeroDrop: evidence</h1>
<p class="lede">The migration agent that proves nothing was lost. This page is <a href="{repo}/blob/main/EVIDENCE.md">EVIDENCE.md</a> from the repository, with the key Neatlogs captures on top. Every number comes from a saved result file.</p>
<video controls preload="metadata" poster="{base}video/poster.jpg" src="{base}video/zerodrop-demo.mp4"></video>
<div class="shots">
{shots}
</div>
</header>
<main>
{body}
</main>
<footer>Built during neatHack 2026 by team Tokenmaxing. Source: <a href="{repo}">{repo}</a></footer>
</body>
</html>
"""


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    return subprocess.run(cmd, cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def build_dashboard(out: Path) -> None:
    env = {**os.environ, "VITE_MOCK": "1"}
    run(["npx", "vite", "build", f"--base={BASE}", "--outDir", str(out), "--emptyOutDir"], ROOT / "ui", env)


def evidence_html(cfo_url: str) -> str:
    body = run(["npx", "--yes", "marked", "-i", str(ROOT / "EVIDENCE.md")], ROOT)
    body = re.sub(r"<h1>.*?</h1>", "", body, count=1, flags=re.S)
    body = re.sub(r'href="(?!https?://|#)([^"]+)"', lambda m: f'href="{REPO}/blob/main/{m.group(1)}"', body)
    body = body.replace("<table>", '<div class="scroll"><table>').replace("</table>", "</table></div>")
    shots = "\n".join(
        f'<figure><a href="{RAW}/evidence/screenshots/{name}"><img loading="lazy" src="{RAW}/evidence/screenshots/{name}" '
        f'alt="{html.escape(caption)}"></a><figcaption>{html.escape(caption)}</figcaption></figure>'
        for name, caption in SHOTS
    )
    return PAGE.format(base=BASE, repo=REPO, cfo=cfo_url, shots=shots, body=body)


def main() -> None:
    cfo_url = (ROOT / "evidence" / "cfo-share-link.txt").read_text(encoding="utf-8").strip()
    with tempfile.TemporaryDirectory() as tmp:
        built = Path(tmp) / "site"
        build_dashboard(built)
        shutil.rmtree(DOCS / "assets", ignore_errors=True)
        shutil.copytree(built / "assets", DOCS / "assets")
        shutil.copy2(built / "index.html", DOCS / "index.html")
        shutil.copy2(built / "index.html", DOCS / "404.html")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    (DOCS / "evidence").mkdir(exist_ok=True)
    (DOCS / "evidence" / "index.html").write_text(evidence_html(cfo_url), encoding="utf-8")
    (DOCS / "video").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "evidence" / "video" / "zerodrop-demo.mp4", DOCS / "video" / "zerodrop-demo.mp4")
    shutil.copy2(ROOT / "evidence" / "video" / "poster.jpg", DOCS / "video" / "poster.jpg")
    print("site written to docs/: index.html, assets/, evidence/index.html, video/zerodrop-demo.mp4")


if __name__ == "__main__":
    main()
