"""Integration tests: scenarios load, the runner reaches verified outcomes, the API streams events."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from zerodrop.api import create_app
from zerodrop.models import RunStatus
from zerodrop.runner import run_scenario
from zerodrop.scenarios import get_scenario, load_scenarios


def test_all_scenarios_load_with_unique_ids() -> None:
    scenarios = load_scenarios()
    assert len(scenarios) == 20
    assert len({s.id for s in scenarios}) == 20
    assert any("demo" in s.tags for s in scenarios)


@pytest.mark.slow
def test_oracle_planner_reaches_verified_success() -> None:
    outcome = run_scenario(get_scenario("S01-clean"), "oracle", sleep=lambda _: None)
    assert outcome.status == RunStatus.SUCCESS
    assert outcome.matched_expectation and not outcome.false_success_claim
    assert outcome.failed_checks == []


@pytest.mark.slow
def test_naive_planner_is_caught_by_the_verifier() -> None:
    outcome = run_scenario(get_scenario("S01-clean"), "naive", sleep=lambda _: None)
    assert outcome.agent_claimed_status == RunStatus.SUCCESS
    assert outcome.status == RunStatus.FAILED
    assert outcome.false_success_claim
    assert any(c.startswith("money_by_currency") for c in outcome.failed_checks)


@pytest.mark.slow
def test_crash_scenario_resumes_without_duplicates() -> None:
    outcome = run_scenario(get_scenario("S09-crash-resume"), "oracle", sleep=lambda _: None)
    assert outcome.crashed_and_resumed
    assert outcome.status == RunStatus.SUCCESS


@pytest.mark.slow
def test_api_runs_a_scenario_and_streams_events(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(db_path=str(tmp_path / "api.db"), default_planner="oracle")
    with TestClient(app) as client:
        ids = [s["id"] for s in client.get("/api/scenarios").json()]
        assert "S07-schema-flip" in ids
        run_id = client.post("/api/runs", json={"scenario_id": "S07-schema-flip"}).json()["run_id"]
        deadline = time.monotonic() + 60
        status = None
        while time.monotonic() < deadline:
            status = client.get(f"/api/runs/{run_id}").json()["status"]
            if status in {"SUCCESS", "PARTIAL_SUCCESS", "FAILED", "WAITING_FOR_APPROVAL"}:
                break
            time.sleep(0.2)
        assert status == "SUCCESS"
        body = client.get(f"/api/runs/{run_id}/events").text
        events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
        kinds = {e["kind"] for e in events}
        assert {"state", "plan", "batch", "verify"} <= kinds
        assert client.get(f"/api/runs/{run_id}/report").json()["status"] == "SUCCESS"
        mappings = client.get(f"/api/runs/{run_id}/mappings").json()
        assert any(m["entity"] == "subscriptions" and m["version"] >= 2 for m in mappings)
        assert client.post("/api/runs", json={"scenario_id": "nope"}).status_code == 404


@pytest.mark.slow
def test_rate_limit_storm_longer_than_the_attempt_budget_still_succeeds() -> None:
    """Regression (found by the S03 eval run): 429s with Retry-After are waits, not failures.

    Six consecutive 429s used to exhaust max_attempts_per_request (6) and halt the run.
    """
    from zerodrop.models import FaultPlan, FaultRule

    scenario = get_scenario("S03-rate-limit-storm").model_copy(
        update={
            "fault_plan": FaultPlan(
                rules=[FaultRule(kind="rate_limit", after_requests=1, count=9, retry_after_s=0.01)]
            )
        }
    )
    outcome = run_scenario(scenario, "oracle", sleep=lambda _: None)
    assert outcome.status == RunStatus.SUCCESS, outcome.failed_checks
    assert sum(1 for f in outcome.faults_fired if f.get("kind") == "rate_limit") == 9
