"""Build the real-model runs table from evidence/runs/*.json (numbers come only from those files).

Usage: uv run python scripts/runs_table.py [evidence/runs]
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HEADER = (
    "| Scenario | Model | Commit | Expected | Verified outcome | Agent's own claim | Model calls | "
    "Cost (list) | Time | File |"
)


def main(folder: str = "evidence/runs") -> None:
    rows = sorted(
        (
            json.loads(path.read_text(encoding="utf-8")) | {"file": path.name}
            for path in Path(folder).glob("*.json")
        ),
        key=lambda r: (r["scenario_id"], r["file"]),
    )
    print(HEADER)
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        m = r["metrics"]
        outcome = r["status"] + ("" if r["matched_expectation"] else " (not matched)")
        claim = (r.get("agent_claimed_status") or "-") + (
            " (**false success**)" if r["false_success_claim"] else ""
        )
        print(
            f"| {r['scenario_id']} | `{r.get('model') or r['planner']}` | `{r['git_commit'][:7]}` | "
            f"{r['expected']} | {outcome} | {claim} | {m['llm_calls']} | ${m['cost_usd']:.3f} | "
            f"{r['duration_s']:.0f} s | `{r['file']}` |"
        )
    matched = [r for r in rows if r["matched_expectation"]]
    false_success = [r for r in rows if r["false_success_claim"]]
    halted = [r for r in rows if not r["matched_expectation"] and not r["false_success_claim"]]
    costs = sorted(r["metrics"]["cost_usd"] for r in matched)
    print()
    print(
        f"{len(rows)} runs. {len(matched)} matched the expected verified outcome, covering "
        f"{len({r['scenario_id'] for r in matched})} distinct scenarios. {len(false_success)} ended in a false "
        f"success claim that the verifier caught. {len(halted)} halted without one. "
        f"Model cost of a matched run at list price: median ${statistics.median(costs):.3f}, "
        f"range ${costs[0]:.3f} to ${costs[-1]:.3f}. All runs together: "
        f"${sum(r['metrics']['cost_usd'] for r in rows):.2f}."
    )


if __name__ == "__main__":
    main(*sys.argv[1:2])
