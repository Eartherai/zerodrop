"""Run the agent three times with scripted planners and check what the independent verifier says.

No model, no keys, no network outside the local sandbox: these are the runs a reader can repeat in
a few seconds, and CI repeats them on every push. They do not measure a model; the real-model
results are the saved files that scripts/verify_numbers.py checks.

1. A deliberately wrong mapping with the first-batch check off: the agent claims SUCCESS and the
   verifier says FAILED (a false success claim).
2. The same mapping with the first-batch check on: the run stops early and reports FAILED itself.
3. The "everything goes wrong" scenario with the correct mapping: rate limits, a timeout after a
   write that landed, an API change mid-run; the verifier says SUCCESS.

    uv run python scripts/ci_keyless_runs.py [--markdown]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

RUNS = [
    {
        "title": "wrong mapping, first-batch check off",
        "scenario": "S01-clean",
        "planner": "naive",
        "env": {"EARLY_CHECK": "false"},
        "expect": {"agent_claimed_status": "SUCCESS", "status": "FAILED", "false_success_claim": True},
        "records_written": 182,
    },
    {
        "title": "wrong mapping, first-batch check on",
        "scenario": "S01-clean",
        "planner": "naive",
        "env": {"EARLY_CHECK": "true"},
        "expect": {"agent_claimed_status": "FAILED", "status": "FAILED", "false_success_claim": False},
        "records_written": 28,
    },
    {
        "title": "everything goes wrong, correct mapping",
        "scenario": "S16-demo-chaos",
        "planner": "oracle",
        "env": {},
        "expect": {"agent_claimed_status": "SUCCESS", "status": "SUCCESS", "false_success_claim": False},
        "records_written": None,
    },
]


def run(scenario: str, planner: str, env: dict[str, str]) -> dict:
    done = subprocess.run(
        ["zerodrop", "run", scenario, "--planner", planner],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        check=False,
    )
    if done.returncode != 0:
        raise SystemExit(f"zerodrop run {scenario} exited {done.returncode}:\n{done.stderr[-2000:]}")
    # The command prints its event log, then the outcome as one JSON object.
    start = done.stdout.rindex("\n{\n") + 1
    return json.loads(done.stdout[start:])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    rows, failed = [], False
    for spec in RUNS:
        outcome = run(spec["scenario"], spec["planner"], spec["env"])
        written = outcome["metrics"]["records_written"]
        ok = all(outcome[key] == value for key, value in spec["expect"].items())
        if spec["records_written"] is not None:
            ok = ok and written == spec["records_written"]
        failed = failed or not ok
        rows.append(
            [
                spec["title"],
                f"{spec['scenario']}, {spec['planner']} planner",
                outcome["agent_claimed_status"],
                outcome["status"],
                "yes" if outcome["false_success_claim"] else "no",
                str(written),
                "as expected" if ok else "NOT AS EXPECTED",
            ]
        )
    header = ["run", "scenario", "agent said", "verifier said", "false success claim", "records written", ""]
    if args.markdown:
        print("\n### Three runs with scripted planners (no model, no keys)\n")
        print("| " + " | ".join(header) + " |")
        print("|" + "---|" * len(header))
        for row in rows:
            print("| " + " | ".join(row) + " |")
    else:
        widths = [max(len(header[i]), *(len(row[i]) for row in rows)) for i in range(len(header))]
        for row in [header, *rows]:
            print("  ".join(row[i].ljust(widths[i]) for i in range(len(header))).rstrip())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
