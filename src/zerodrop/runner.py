"""Run one scenario end to end: sandbox -> engine (+ planner) -> independent verifier.

Used by the CLI (`zerodrop run`, `zerodrop eval`) and the API server. Each run gets fresh
sandbox servers on free ports, so runs never share state.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr

from zerodrop.config import Settings
from zerodrop.connectors.source import SourceClient
from zerodrop.connectors.target import TargetClient
from zerodrop.engine import MigrationEngine, RunResult, SimulatedCrash
from zerodrop.ledger import Ledger
from zerodrop.models import PreservationContract, RunEvent, RunStatus
from zerodrop.sandbox import fixtures, servers
from zerodrop.scenarios import Scenario
from zerodrop.verifier.verify import verify

PlannerMode = Literal["oracle", "naive", "claude", "gemini"]
REPO_ROOT = Path(__file__).resolve().parents[2]


class ScenarioOutcome(BaseModel):
    scenario_id: str
    planner: str
    model: str | None = None  # configured model id of a model planner; None for the offline fakes
    run_id: str
    status: RunStatus  # decided by the independent verifier (or the engine for halts/approval waits)
    agent_claimed_status: RunStatus | None = None
    expected: RunStatus
    matched_expectation: bool
    false_success_claim: bool  # the agent believed SUCCESS but the verifier disagreed
    crashed_and_resumed: bool = False
    duration_s: float
    metrics: dict[str, Any] = Field(default_factory=dict)
    faults_fired: list[Any] = Field(default_factory=list)
    failed_checks: list[str] = Field(default_factory=list)
    report_hash: str = ""
    git_commit: str = ""


def git_commit() -> str:
    """Short commit of the checkout, or of the image build (ZERODROP_GIT_COMMIT) when there is no .git."""
    return _checkout_commit() or os.getenv("ZERODROP_GIT_COMMIT", "").strip()[:12]


def _checkout_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip()
    except OSError:
        return ""


def make_planner(mode: PlannerMode, settings: Settings) -> Any:
    if mode in ("oracle", "naive"):
        from zerodrop.agent.fake import FakePlanner

        return FakePlanner(mode)
    model = planner_model(mode, settings)
    if model is None:
        raise ValueError(f"unknown planner {mode!r}: use oracle, naive, claude or gemini")
    from zerodrop.agent.llm import LLMClient  # imports the SDK lazily (after telemetry init)
    from zerodrop.agent.planner import ClaudePlanner

    return ClaudePlanner(LLMClient(settings, model=model))  # the model id selects the provider


def planner_model(mode: str, settings: Settings) -> str | None:
    """The model id a model planner uses; None for the fakes and for unknown modes."""
    return {"claude": settings.model, "gemini": settings.gemini_model}.get(mode)


def run_scenario(
    scenario: Scenario,
    planner_mode: PlannerMode = "oracle",
    *,
    db_path: str = ":memory:",
    on_event: Callable[[RunEvent], None] | None = None,
    base_settings: Settings | None = None,
    ledger: Ledger | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ScenarioOutcome:
    """Execute `scenario` once and return a measurable outcome (never raises for agent failures)."""
    started = time.monotonic()
    dataset = fixtures.generate(**scenario.dataset.model_dump())
    own_ledger = ledger is None
    ledger = ledger or Ledger(db_path)
    run_ids: list[str] = []

    def record(event: RunEvent) -> None:
        if not run_ids:
            run_ids.append(event.run_id)
        if on_event is not None:
            on_event(event)

    with tempfile.TemporaryDirectory(prefix="zerodrop-") as tmp:
        golden_path = dataset.write_golden(Path(tmp) / "golden.json")
        contract = PreservationContract(golden_path=str(golden_path))
        with servers.run_sandbox(
            dataset,
            scenario.fault_plan,
            source_fault_plan=scenario.source_fault_plan,
            initial_version=scenario.initial_version,
        ) as sandbox:
            token_file: str | None = None
            if scenario.rotated_token_available:
                token_path = Path(tmp) / "novabill_token"
                token_path.write_text(sandbox.rotated_token, encoding="utf-8")
                token_file = str(token_path)
            overrides = {
                "source_url": sandbox.source_url,
                "target_url": sandbox.target_url,
                "target_token": SecretStr(sandbox.target_token),
                "target_token_file": token_file,
                "batch_size": scenario.batch_size,
                "db_path": db_path,
            }
            settings = (base_settings or Settings()).model_copy(update=overrides)

            def build_engine() -> MigrationEngine:
                token = {"value": sandbox.target_token}
                return MigrationEngine(
                    settings,
                    SourceClient(sandbox.source_url),
                    TargetClient(sandbox.target_url, lambda: token["value"]),
                    make_planner(planner_mode, settings),
                    verify,
                    ledger,
                    on_event=record,
                    sleep=sleep,
                    rng_seed=scenario.dataset.seed,
                )

            crashed = False
            try:
                result: RunResult = build_engine().run(
                    scenario.goal,
                    scenario=scenario.id,
                    contract=contract,
                    crash_after_batches=scenario.crash_after_batches,
                )
            except SimulatedCrash:
                crashed = True
                if not run_ids:
                    raise
                result = build_engine().resume(run_ids[0])
            stats = sandbox.stats()

    if own_ledger:
        ledger.close()
    report = result.report
    failed = [f"{c.name}: {c.detail}"[:240] for c in (report.checks if report else []) if not c.passed]
    claimed = result.agent_claimed_status
    return ScenarioOutcome(
        scenario_id=scenario.id,
        planner=planner_mode,
        model=planner_model(planner_mode, settings),
        run_id=result.run_id,
        status=result.status,
        agent_claimed_status=claimed,
        expected=scenario.expect,
        matched_expectation=result.status == scenario.expect,
        false_success_claim=claimed == RunStatus.SUCCESS and result.status != RunStatus.SUCCESS,
        crashed_and_resumed=crashed,
        duration_s=round(time.monotonic() - started, 3),
        metrics={
            **result.metrics,
            "target_version_final": stats.get("version"),
            "target_requests_by_status": stats.get("requests", {}).get("by_status", {}),
        },
        faults_fired=list(stats.get("fired", [])),
        failed_checks=failed,
        report_hash=report.report_hash if report else "",
        git_commit=git_commit(),
    )
