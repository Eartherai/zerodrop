"""Build a before/after comparison table from saved `zerodrop eval` JSON files.

Usage: uv run python scripts/compare_evals.py evidence/eval/A.json evidence/eval/B.json [...]
Prints Markdown. Numbers come only from the files; nothing is typed by hand.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(paths: list[str]) -> None:
    runs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in paths]
    labels = [f"{r['summary']['label'] or r['summary']['planner']} (`{r['summary']['git_commit']}`)" for r in runs]
    print("| Metric | " + " | ".join(labels) + " |")
    print("|---|" + "---|" * len(runs))
    for key, title in [
        ("scenarios", "Scenarios"),
        ("matched_expected_outcome", "Matched expected verified outcome"),
        ("verified_success", "Verified SUCCESS"),
        ("false_success_claims", "False success claims"),
        ("crash_resumes", "Crash + resume runs"),
        ("llm_calls", "LLM calls"),
        ("llm_cost_usd", "LLM cost (USD)"),
        ("median_duration_s", "Median duration (s)"),
    ]:
        print(f"| {title} | " + " | ".join(str(r["summary"].get(key)) for r in runs) + " |")
    print()
    ids = [o["scenario_id"] for o in runs[0]["outcomes"]]
    print("| Scenario | " + " | ".join(labels) + " |")
    print("|---|" + "---|" * len(runs))
    for sid in ids:
        cells = []
        for r in runs:
            o = next((x for x in r["outcomes"] if x["scenario_id"] == sid), None)
            cells.append("-" if o is None else f"{o['status']} ({o['duration_s']:.1f} s)")
        print(f"| {sid} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main(sys.argv[1:])
