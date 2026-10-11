"""Build the real-model runs table from evidence/runs/*.json (numbers come only from those files).

Usage: uv run python scripts/runs_table.py [evidence/runs]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(folder: str = "evidence/runs") -> None:
    rows = sorted(
        (
            json.loads(path.read_text(encoding="utf-8")) | {"file": path.name}
            for path in Path(folder).glob("*.json")
        ),
        key=lambda r: (r["scenario_id"], r["file"]),
    )
    print(
        "| Scenario | Model | Expected | Verified outcome | Checks failed | Model calls | Cost (list) | Replans | Time | File |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        m = r["metrics"]
        outcome = r["status"] + ("" if r["matched_expectation"] else " (not matched)")
        print(
            f"| {r['scenario_id']} | `{r.get('model') or r['planner']}` | {r['expected']} | {outcome} | "
            f"{len(r['failed_checks'])} | {m['llm_calls']} | ${m['cost_usd']:.3f} | {m['replans']} | "
            f"{r['duration_s']:.0f} s | `{r['file']}` |"
        )
    matched = sum(r["matched_expectation"] for r in rows)
    false_success = sum(r["false_success_claim"] for r in rows)
    scenarios = {r["scenario_id"] for r in rows if r["matched_expectation"]}
    cost = sum(r["metrics"]["cost_usd"] for r in rows)
    commits = sorted({r["git_commit"] for r in rows})
    print()
    print(
        f"{len(rows)} runs, {matched} matched the expected verified outcome, {len(scenarios)} distinct scenarios "
        f"matched, {false_success} false success claims, ${cost:.2f} total at list price. Commits: {', '.join(commits)}."
    )


if __name__ == "__main__":
    main(*sys.argv[1:2])
