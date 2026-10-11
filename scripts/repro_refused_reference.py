"""Reproduce the mistake a real model made in run_ab090e6c2fc6, then let a real model repair it.

The plan is seeded, not planned by the model: correct mappings, except that subscriptions on API
v1 send the price id where the plan code belongs (the mapping the model wrote in that run). The
payloads have the right shape, so the dry run passes and the target refuses every subscription.
Every repair after that is the real model's work.

    uv run python scripts/repro_refused_reference.py --guard on  --json-out evidence/experiments/<name>.json
    uv run python scripts/repro_refused_reference.py --guard off --json-out evidence/experiments/<name>.json

`--guard off` is the control: it turns off the engine's memory of refused reference values, which
is how the engine behaved before that guard existed. Needs ZERODROP_GEMINI_KEY (and GEMINI_MODEL).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from zerodrop import runner, telemetry
from zerodrop.agent.fake import FakePlanner
from zerodrop.config import Settings
from zerodrop.engine import PlannerTools
from zerodrop.models import DiscoveryContext, Entity, FieldMapping, MigrationPlan, TransformOp
from zerodrop.scenarios import get_scenario

SCENARIO = "S01-clean"


class SeededWrongReferencePlanner:
    """Seeded plan with the model's wrong plan_code mapping; repairs come from the real model."""

    def __init__(self, model_planner: Any) -> None:
        self._model = model_planner
        self._seed = FakePlanner("oracle")
        # Shown in the trace and the dashboard, so the seeded plan is never read as the model's.
        self.mode = f"seeded wrong plan_code mapping; repairs by {model_planner.llm.model}"

    @property
    def usage(self) -> Any:
        return self._model.usage

    def bind_tools(self, tools: Any) -> None:
        self._model.bind_tools(tools)

    def plan(self, ctx: DiscoveryContext) -> MigrationPlan:
        plan = self._seed.plan(ctx)
        lookup = TransformOp(op="lookup", table="prices", match_field="lookup_key", return_field="id")
        wrong = FieldMapping(target="plan_code", source="plan_code", ops=[lookup])
        mappings = [
            m.model_copy(update={"fields": [wrong if f.target == "plan_code" else f for f in m.fields]})
            if m.entity is Entity.subscriptions
            else m
            for m in plan.mappings
        ]
        return plan.model_copy(
            update={"mappings": mappings, "notes": "seeded plan: price id sent as plan_code"}
        )

    def repair(self, ctx: Any) -> Any:
        return self._model.repair(ctx)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--guard", choices=["on", "off"], required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    args = parser.parse_args()

    if args.guard == "off":
        PlannerTools.note_refused = lambda self, *a, **k: None  # type: ignore[method-assign]
    build = runner.make_planner
    runner.make_planner = lambda mode, settings: SeededWrongReferencePlanner(build(mode, settings))  # type: ignore[assignment]

    telemetry.init_telemetry(
        "zerodrop-migration", tags=["planner:gemini", "repro:refused-reference", f"guard:{args.guard}"]
    )

    def show(event: Any) -> None:
        entity = f"[{event.entity}] " if event.entity else ""
        print(f"{event.seq:4} {event.kind:9} {entity}{event.message}")

    try:
        outcome = runner.run_scenario(
            get_scenario(SCENARIO), "gemini", on_event=show, base_settings=Settings()
        )
    finally:
        telemetry.shutdown()
    result = outcome.model_dump(mode="json", exclude={"faults_fired"})
    by_status = result["metrics"].get("target_requests_by_status") or {}
    result["experiment"] = {
        "name": "refused-reference repair",
        "guard": args.guard,
        "plan": "seeded (not the model's): subscriptions v1 send the price id as plan_code",
        "repairs": "real model",
        "target_requests_by_status": by_status,
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    keep = ("status", "agent_claimed_status", "false_success_claim", "run_id", "duration_s", "experiment")
    print(json.dumps({k: result[k] for k in keep}, indent=2))


if __name__ == "__main__":
    main()
