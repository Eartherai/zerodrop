"""Recompute the published numbers from the saved result files, and fail if a document disagrees.

README.md and EVIDENCE.md publish results as tables: a model, a commit, "N of M" scenarios that
ended as expected, the number of false success claims, and in EVIDENCE.md the model calls and the
cost. Every one of those rows should correspond to a result file under evidence/eval/. This
script checks that, row by row, and also recomputes three totals from every saved run:

- runs where the agent claimed SUCCESS and the independent verifier said FAILED, with a real model;
- records written by the two control runs, with the first-batch check off and on;
- the list-price cost of every saved real-model run.

    uv run python scripts/verify_numbers.py             # table on the terminal, exit 1 on a mismatch
    uv run python scripts/verify_numbers.py --markdown  # the same as Markdown (CI job summary)

It reads files only: no model, no keys, no network. Rows it cannot check mechanically (a pass that
the model provider's quota cut short, described in words) are listed as "not checked", never
guessed. CI runs it on every push (.github/workflows/ci.yml).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "evidence" / "eval"
RUN_DIRS = [EVAL_DIR, ROOT / "evidence" / "runs", ROOT / "evidence" / "experiments"]
CONTROL_OFF = ROOT / "evidence" / "experiments" / "early-check-off-naive-S01.json"
CONTROL_ON = ROOT / "evidence" / "experiments" / "early-check-on-naive-S01.json"
DOCS = ["README.md", "EVIDENCE.md"]

COMMIT = re.compile(r"`([0-9a-f]{7})`")
MODEL = re.compile(r"`(gemini-[0-9a-z.\-]+)`")
RESULT = re.compile(r"^\**(\d+) of (\d+)\**$")
SCRIPTED = "scripted"


@dataclass(frozen=True)
class Pass:
    """One evaluation file: one pass over the scenarios on one planner."""

    file: str
    model: str
    commits: frozenset[str]
    scenarios: int
    matched: int
    false_successes: int
    llm_calls: int
    cost_usd: float


@dataclass(frozen=True)
class Line:
    source: str
    claim: str
    published: str
    recomputed: str
    status: str  # ok | MISMATCH | not checked
    file: str = ""


def load_passes() -> list[Pass]:
    passes = []
    for path in sorted(EVAL_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        outcomes, summary = data["outcomes"], data["summary"]
        passes.append(
            Pass(
                file=str(path.relative_to(ROOT)),
                model=summary.get("model") or SCRIPTED,
                commits=frozenset(o["git_commit"][:7] for o in outcomes),
                scenarios=len(outcomes),
                matched=sum(1 for o in outcomes if o["matched_expectation"]),
                false_successes=sum(1 for o in outcomes if o["false_success_claim"]),
                llm_calls=int(summary.get("llm_calls") or 0),
                cost_usd=float(summary.get("llm_cost_usd") or 0.0),
            )
        )
    return passes


def load_runs() -> dict[str, dict]:
    """Every saved run, once per run id (a run can be in a pass file and saved on its own)."""
    runs: dict[str, dict] = {}
    for directory in RUN_DIRS:
        for path in sorted(directory.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for outcome in data.get("outcomes", [data]):
                runs.setdefault(outcome["run_id"], outcome)
    return runs


def cells(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def leading_int(cell: str) -> int | None:
    match = re.match(r"\**(\d+)", cell)
    return int(match.group(1)) if match else None


def check_tables(doc: str, passes: list[Pass]) -> list[Line]:
    """Each table row that names a commit and "N of M" must match a saved pass at that commit."""
    lines = []
    for number, row in enumerate((ROOT / doc).read_text(encoding="utf-8").splitlines(), start=1):
        if not row.startswith("|"):
            continue
        parts = cells(row)
        index = next((i for i, cell in enumerate(parts) if RESULT.match(cell)), None)
        commits = COMMIT.findall(" ".join(parts[: index if index is not None else len(parts)]))
        source = f"{doc}:{number}"
        if index is None:
            if commits and re.search(r"\d+ of the \d+", row):
                lines.append(Line(source, parts[0][:60], "a partial pass, in words", "", "not checked"))
            continue
        if not commits:
            continue
        match = RESULT.match(parts[index])
        assert match is not None
        matched, scenarios = int(match.group(1)), int(match.group(2))
        false_successes = leading_int(parts[index + 1]) if index + 1 < len(parts) else None
        model_match = MODEL.search(" ".join(parts[:index]))
        model = model_match.group(1) if model_match else SCRIPTED
        published = f"{matched} of {scenarios}, {false_successes} false success"
        at_commit = [p for p in passes if p.model == model and commits[0] in p.commits]
        exact = [
            p
            for p in at_commit
            if (p.matched, p.scenarios) == (matched, scenarios) and p.false_successes == false_successes
        ]
        claim = f"{model} at {commits[0]}"
        if not exact:
            found = "; ".join(
                f"{p.matched} of {p.scenarios}, {p.false_successes} false success" for p in at_commit
            )
            lines.append(Line(source, claim, published, found or "no saved pass at this commit", "MISMATCH"))
            continue
        chosen = exact[0]
        lines.append(Line(source, claim, published, published, "ok", chosen.file))
        # EVIDENCE.md also publishes the model calls and the list-price cost of each pass.
        extra = parts[index + 2 : index + 4]
        if len(extra) == 2 and extra[0].isdigit() and extra[1].startswith("$"):
            calls, cost = int(extra[0]), float(extra[1].lstrip("$"))
            same = any(p.llm_calls == calls and abs(p.cost_usd - cost) < 0.00005 for p in exact)
            recomputed = f"{chosen.llm_calls} calls, ${chosen.cost_usd:.4f}"
            lines.append(
                Line(
                    source,
                    f"{claim}: model calls and cost",
                    f"{calls} calls, ${cost:.4f}",
                    recomputed,
                    "ok" if same else "MISMATCH",
                    chosen.file,
                )
            )
    return lines


def stated(doc: str, *needles: str) -> bool:
    text = (ROOT / doc).read_text(encoding="utf-8")
    return all(needle in text for needle in needles)


def check_totals(runs: dict[str, dict]) -> list[Line]:
    real = [run for run in runs.values() if run.get("model")]
    false_successes = sum(1 for run in real if run["false_success_claim"])
    cost = sum(float(run["metrics"].get("cost_usd") or 0.0) for run in real)
    off = json.loads(CONTROL_OFF.read_text(encoding="utf-8"))
    on = json.loads(CONTROL_ON.read_text(encoding="utf-8"))
    written_off, written_on = off["metrics"]["records_written"], on["metrics"]["records_written"]
    control = (
        off["agent_claimed_status"] == "SUCCESS"
        and off["status"] == "FAILED"
        and off["false_success_claim"]
        and on["agent_claimed_status"] == "FAILED"
        and on["status"] == "FAILED"
        and not on["false_success_claim"]
    )
    everywhere = f"{len(real)} saved real-model runs"
    return [
        Line(
            "README.md, EVIDENCE.md",
            "real-model runs where the agent claimed SUCCESS and the verifier said FAILED",
            "7",
            str(false_successes),
            "ok"
            if false_successes == 7
            and stated("README.md", "7 false successes")
            and stated("EVIDENCE.md", "7 real false successes")
            else "MISMATCH",
            everywhere,
        ),
        Line(
            "README.md, EVIDENCE.md",
            "control run, first-batch check off: records written; agent SUCCESS, verifier FAILED",
            "182",
            str(written_off),
            "ok"
            if written_off == 182
            and control
            and stated("README.md", "182 records written")
            and stated("EVIDENCE.md", "182")
            else "MISMATCH",
            str(CONTROL_OFF.relative_to(ROOT)),
        ),
        Line(
            "README.md, EVIDENCE.md",
            "control run, first-batch check on: records written; agent reports FAILED itself",
            "28",
            str(written_on),
            "ok"
            if written_on == 28
            and control
            and stated("README.md", "after 28 records")
            and stated("EVIDENCE.md", "28")
            else "MISMATCH",
            str(CONTROL_ON.relative_to(ROOT)),
        ),
        Line(
            "EVIDENCE.md",
            "list-price cost of every saved real-model run",
            "$4.06",
            f"${cost:.2f}",
            "ok" if f"{cost:.2f}" == "4.06" and stated("EVIDENCE.md", "$4.06") else "MISMATCH",
            everywhere,
        ),
    ]


def render(lines: list[Line], markdown: bool) -> str:
    header = ["where", "claim", "published", "recomputed", "", "from"]
    rows = [
        [line.source, line.claim, line.published, line.recomputed, line.status, line.file] for line in lines
    ]
    if markdown:
        out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
        out += ["| " + " | ".join(row) + " |" for row in rows]
        return "\n".join(out)
    widths = [max(len(header[i]), *(len(row[i]) for row in rows)) for i in range(len(header))]
    out = ["  ".join(header[i].ljust(widths[i]) for i in range(len(header)))]
    out += ["  ".join(row[i].ljust(widths[i]) for i in range(len(header))) for row in rows]
    return "\n".join(line.rstrip() for line in out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--markdown", action="store_true", help="print a Markdown table and summary")
    args = parser.parse_args()
    passes, runs = load_passes(), load_runs()
    lines = [line for doc in DOCS for line in check_tables(doc, passes)] + check_totals(runs)
    bad = [line for line in lines if line.status == "MISMATCH"]
    checked = sum(1 for line in lines if line.status == "ok")
    skipped = sum(1 for line in lines if line.status == "not checked")
    verdict = (
        f"{checked} published figures recomputed from {len(passes)} evaluation files and {len(runs)} saved runs: "
        f"{len(bad)} mismatch(es), {skipped} row(s) described in words and not checked."
    )
    if args.markdown:
        print("### Published numbers, recomputed from the saved result files\n")
        print(verdict + "\n")
    print(render(lines, args.markdown))
    if not args.markdown:
        print("\n" + verdict)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
