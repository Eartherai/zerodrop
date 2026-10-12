"""Export one finished run from a ledger database as a dashboard recording.

The static demo site (GitHub Pages) has no server. It replays recordings: the events, mappings
and report of real runs, read from the ledger exactly as the API serves them.

    uv run python scripts/export_recording.py --db runs/zerodrop.db --run run_aa73127580bb \
        --id real-chaos --title "Everything goes wrong (real run, Gemini)" \
        --description "..." --out ui/src/mock/recordings/real-chaos.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from zerodrop.api import create_app
from zerodrop.ledger import Ledger

COUNT_KEYS = ("total", "written", "quarantined", "pending")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--id", required=True, help="recording id shown as the scenario id")
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    ledger = Ledger(args.db)
    record = ledger.get_run(args.run)
    if record is None:
        raise SystemExit(f"run {args.run} is not in {args.db}")
    events = [e.model_dump(mode="json") for e in ledger.events_since(args.run)]
    with TestClient(create_app(db_path=args.db, default_planner="oracle")) as client:
        summary = client.get(f"/api/runs/{args.run}").json()
        mappings = client.get(f"/api/runs/{args.run}/mappings").json()
        report = client.get(f"/api/runs/{args.run}/report")
    summary["scenario_id"] = args.id
    summary["created_at"] = events[0]["ts"]
    summary["commit"] = None  # the commit of the export is not the commit of the run
    summary["counts"] = {e: {k: c.get(k, 0) for k in COUNT_KEYS} for e, c in summary["counts"].items()}
    recording = {
        "scenario": {"id": args.id, "title": args.title, "description": args.description},
        "fault_plan": {
            "seed": 0,
            "rules": [],
            "note": "recorded run; the fault plan is in scenarios/scenarios.yaml",
        },
        "summary": summary,
        "events": events,
        "mappings": mappings,
        "report": report.json() if report.status_code == 200 else None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(recording, indent=1) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(events)} events, {len(mappings)} mappings, status {summary['status']}")


if __name__ == "__main__":
    main()
