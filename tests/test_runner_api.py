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


def test_git_commit_falls_back_to_the_image_build_commit(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from zerodrop import runner

    # A container image has no .git: the commit it was built from comes from the environment.
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("ZERODROP_GIT_COMMIT", "abc123def4567890")
    assert runner.git_commit() == "abc123def456"
    monkeypatch.delenv("ZERODROP_GIT_COMMIT")
    assert runner.git_commit() == ""


def test_api_run_detail_carries_the_neatlogs_trace_id(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from zerodrop import telemetry

    app = create_app(db_path=str(tmp_path / "api.db"), default_planner="oracle")
    with TestClient(app) as client:

        def finished(scenario_id: str) -> dict:  # type: ignore[type-arg]
            deadline = time.monotonic() + 60
            started = client.post("/api/runs", json={"scenario_id": scenario_id})
            while started.status_code == 409 and time.monotonic() < deadline:
                time.sleep(0.1)  # the previous run's worker thread is still winding down
                started = client.post("/api/runs", json={"scenario_id": scenario_id})
            run_id = started.json()["run_id"]
            while time.monotonic() < deadline:
                detail = client.get(f"/api/runs/{run_id}").json()
                if detail["status"] in {"SUCCESS", "PARTIAL_SUCCESS", "FAILED", "WAITING_FOR_APPROVAL"}:
                    return detail
                time.sleep(0.1)
            raise AssertionError("run did not finish")

        assert finished("S01-clean")["trace_id"] is None  # tracing off: nothing to link
        monkeypatch.setattr(telemetry, "current_trace_id", lambda: "cd" * 16)
        assert finished("S01-clean")["trace_id"] == "cd" * 16


# --- planner modes ----------------------------------------------------------------------------


def _settings(**overrides):  # type: ignore[no-untyped-def]
    from zerodrop.config import Settings

    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_gemini_mode_builds_the_planner_on_the_gemini_model(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from zerodrop.agent.planner import ClaudePlanner
    from zerodrop.runner import make_planner, planner_model

    built: list[str] = []

    class Backend:
        def __init__(self, api_key: str, **_: object) -> None:
            built.append(api_key)

    monkeypatch.setattr("zerodrop.agent.gemini.GeminiBackend", Backend)
    settings = _settings(zerodrop_gemini_key="synthetic-gemini-key", zerodrop_anthropic_key=None)
    planner = make_planner("gemini", settings)
    assert isinstance(planner, ClaudePlanner) and planner.llm.model == "gemini-3.8-flash"
    assert built == ["synthetic-gemini-key"]  # the Anthropic key is not needed
    assert planner_model("gemini", settings) == "gemini-3.8-flash"
    assert planner_model("claude", settings) == "claude-opus-5-5"
    assert planner_model("oracle", settings) is None


def test_model_planners_need_their_own_key_and_unknown_modes_are_refused() -> None:
    from zerodrop.agent.llm import LLMConfigError
    from zerodrop.runner import make_planner

    no_keys = _settings(zerodrop_gemini_key=None, zerodrop_anthropic_key=None)
    with pytest.raises(LLMConfigError, match="ZERODROP_GEMINI_KEY"):
        make_planner("gemini", no_keys)
    with pytest.raises(LLMConfigError, match="ZERODROP_ANTHROPIC_KEY"):
        make_planner("claude", no_keys)
    with pytest.raises(ValueError, match="gemnii"):
        make_planner("gemnii", no_keys)  # type: ignore[arg-type]  # used to fall through to Claude


def test_a_gemini_run_without_a_key_fails_before_any_run_exists() -> None:
    from zerodrop.agent.llm import LLMConfigError

    no_key = _settings(zerodrop_gemini_key=None)
    with pytest.raises(LLMConfigError, match="ZERODROP_GEMINI_KEY"):
        run_scenario(get_scenario("S01-clean"), "gemini", base_settings=no_key)


def test_outcomes_and_eval_summaries_record_the_planner_and_its_model(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from zerodrop import cli, runner
    from zerodrop.agent.fake import FakePlanner

    # the oracle fake stands in for the model; only the bookkeeping of mode and model id is under test
    monkeypatch.setattr(runner, "make_planner", lambda mode, settings: FakePlanner("oracle"))
    outcome = run_scenario(get_scenario("S01-clean"), "gemini", base_settings=_settings())
    assert (outcome.planner, outcome.model) == ("gemini", "gemini-3.8-flash")
    summary = cli.summarize([outcome], "gemini", "", "abc")
    assert (summary["planner"], summary["model"]) == ("gemini", "gemini-3.8-flash")
    assert "planner=gemini model=gemini-3.8-flash" in cli.render_markdown(summary, [outcome])
    oracle = run_scenario(get_scenario("S01-clean"), "oracle")
    assert oracle.model is None and cli.summarize([oracle], "oracle", "", "abc")["model"] is None
