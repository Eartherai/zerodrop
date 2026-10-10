"""Public demo mode: access code, hourly run limit, Claude spend cap, /api/meta, no secret leaks.

No test here calls a model: rules are exercised with a fake runner that records the planner it
was given and writes a finished run to the ledger; spend-cap tests write fake costs into the
ledger. One slow test runs a real oracle scenario end to end through the public API.
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from zerodrop.api import create_app
from zerodrop.ledger import Ledger
from zerodrop.models import RunStatus
from zerodrop.public_mode import (
    ACCESS_CODE_HEADER,
    PublicSettings,
    access_code_matches,
    check_budget,
    effective_planner,
)

CODE = "synthetic-access-code-0123456789"  # test value only
ENV_NAMES = (
    "ZERODROP_PUBLIC_ENABLED",
    "ZERODROP_PUBLIC_ACCESS_CODE",
    "ZERODROP_PUBLIC_SPEND_CAP_USD",
    "ZERODROP_PUBLIC_MAX_RUNS_PER_HOUR",
)
TERMINAL = {"SUCCESS", "PARTIAL_SUCCESS", "FAILED", "WAITING_FOR_APPROVAL"}


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def public(**overrides: Any) -> PublicSettings:
    values: dict[str, Any] = {
        "enabled": True,
        "access_code": CODE,
        "spend_cap_usd": 5.0,
        "max_runs_per_hour": 12,
    }
    values.update(overrides)
    return PublicSettings(_env_file=None, **values)  # type: ignore[call-arg]


class FakeRunner:
    """Stands in for run_scenario: records the planner, writes one finished run, never calls a model."""

    def __init__(self, fail: str | None = None) -> None:
        self.planners: list[str] = []
        self.fail = fail  # None, "before_start" or "after_start"

    def __call__(self, scenario: Any, planner: str, *, ledger: Ledger, on_event: Any) -> None:
        self.planners.append(planner)
        if self.fail == "before_start":
            raise RuntimeError("sandbox did not start")
        run_id = ledger.create_run(scenario.goal, scenario=scenario.id)
        on_event(
            ledger.append_event(run_id, "state", f"run created: {scenario.goal}", state=RunStatus.CREATED)
        )
        if self.fail == "after_start":
            raise RuntimeError("engine stopped unexpectedly")
        ledger.set_status(run_id, RunStatus.SUCCESS)


def seed_runs(db_path: Path, *, count: int, at: float, cost_usd: float = 0.0) -> None:
    """Write finished runs created at `at` (epoch seconds), each with a fake LLM cost."""
    with Ledger(db_path, clock=lambda: at) as ledger:
        for _ in range(count):
            run_id = ledger.create_run("seeded run", scenario="S01-clean")
            ledger.set_status(run_id, RunStatus.SUCCESS)
            if cost_usd:
                ledger.set_llm_usage(run_id, calls=3, cost_usd=cost_usd)


def post_run(client: TestClient, *, planner: str | None = None, code: str | None = None) -> Any:
    """POST /api/runs; retries while the previous (instant) fake run thread is still finishing."""
    body: dict[str, str] = {"scenario_id": "S01-clean"}
    if planner is not None:
        body["planner"] = planner
    headers = {ACCESS_CODE_HEADER: code} if code is not None else {}
    deadline = time.monotonic() + 10
    while True:
        response = client.post("/api/runs", json=body, headers=headers)
        if response.status_code != 409 or time.monotonic() > deadline:
            return response
        time.sleep(0.02)


LONG_AGO = time.time() - 2 * 86400  # outside any rate-limit window


# --- settings ---------------------------------------------------------------------------------


def test_settings_defaults_are_safe() -> None:
    s = PublicSettings(_env_file=None)  # type: ignore[call-arg]
    assert s.enabled is False
    assert s.access_code is None
    assert s.spend_cap_usd == 5.0
    assert s.max_runs_per_hour == 12


def test_settings_read_the_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZERODROP_PUBLIC_ENABLED", "true")
    monkeypatch.setenv("ZERODROP_PUBLIC_ACCESS_CODE", CODE)
    monkeypatch.setenv("ZERODROP_PUBLIC_SPEND_CAP_USD", "2.5")
    monkeypatch.setenv("ZERODROP_PUBLIC_MAX_RUNS_PER_HOUR", "3")
    s = PublicSettings(_env_file=None)  # type: ignore[call-arg]
    assert (s.enabled, s.spend_cap_usd, s.max_runs_per_hour) == (True, 2.5, 3)
    assert s.access_code is not None and s.access_code.get_secret_value() == CODE
    assert CODE not in repr(s) and CODE not in str(s)


def test_short_access_code_is_rejected_without_echoing_it() -> None:
    with pytest.raises(ValidationError) as info:
        public(access_code="short-code-1")
    assert "short-code-1" not in str(info.value)
    assert "at least 16 characters" in str(info.value)


def test_blank_access_code_means_unset() -> None:
    assert public(access_code="   ").access_code is None


def test_negative_limits_are_rejected() -> None:
    with pytest.raises(ValidationError):
        public(spend_cap_usd=-1)
    with pytest.raises(ValidationError):
        public(max_runs_per_hour=-1)


# --- pure policy helpers ----------------------------------------------------------------------


def test_access_code_comparison() -> None:
    s = public()
    assert access_code_matches(s, CODE)
    assert not access_code_matches(s, CODE + "x")
    assert not access_code_matches(s, CODE[:-1])
    assert not access_code_matches(s, "")
    assert not access_code_matches(s, None)
    assert not access_code_matches(public(access_code=None), CODE)


def test_requests_without_a_planner_get_oracle_in_public_mode() -> None:
    assert effective_planner(None, "claude", public()) == "oracle"
    assert effective_planner(None, "claude", public(enabled=False)) == "claude"
    assert effective_planner("claude", "oracle", public()) == "claude"


def test_retry_after_counts_from_the_limit_th_newest_run() -> None:
    now = 1_700_000_000.0
    refusal = check_budget(
        public(max_runs_per_hour=2),
        "oracle",
        spend_used_usd=0.0,
        recent_run_times=[now - 30, now - 10, now - 20, now - 4000],
        now=now,
    )
    assert refusal is not None and refusal.status == 429
    assert refusal.headers["Retry-After"] == str(math.ceil(3600 - 20))


# --- /api/meta --------------------------------------------------------------------------------


def test_meta_in_private_mode(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "z.db"), default_planner="claude", public=public(enabled=False))
    with TestClient(app) as client:
        assert client.get("/api/meta").json() == {
            "public_mode": False,
            "claude_runs_allowed": True,
            "spend_used_usd": 0.0,
            "spend_cap_usd": None,
            "default_planner": "claude",
        }


def test_meta_in_public_mode_reports_policy_without_secrets(tmp_path: Path) -> None:
    seed_runs(tmp_path / "z.db", count=2, at=LONG_AGO, cost_usd=0.75)
    app = create_app(str(tmp_path / "z.db"), default_planner="claude", public=public())
    with TestClient(app) as client:
        response = client.get("/api/meta", headers={ACCESS_CODE_HEADER: CODE})
        assert response.json() == {
            "public_mode": True,
            "claude_runs_allowed": True,
            "spend_used_usd": 1.5,
            "spend_cap_usd": 5.0,
            "default_planner": "oracle",
        }
        assert CODE not in response.text


def test_meta_says_claude_is_off_without_an_access_code(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "z.db"), public=public(access_code=None))
    with TestClient(app) as client:
        assert client.get("/api/meta").json()["claude_runs_allowed"] is False


# --- access code ------------------------------------------------------------------------------


def test_without_the_access_code_only_oracle_runs_start(tmp_path: Path) -> None:
    runner = FakeRunner()
    app = create_app(str(tmp_path / "z.db"), default_planner="claude", public=public(), runner=runner)
    with TestClient(app) as client:
        for planner, code in [("claude", None), ("claude", "wrong-code-wrong-code"), ("naive", None)]:
            response = post_run(client, planner=planner, code=code)
            assert response.status_code == 403, planner
            assert ACCESS_CODE_HEADER in response.json()["detail"]
            assert "oracle" in response.json()["detail"]
        assert post_run(client, planner="oracle").status_code == 200
        assert (
            post_run(client).status_code == 200
        )  # no planner: oracle, even though the server default is claude
        assert post_run(client, planner="bogus").status_code == 422
    assert runner.planners == ["oracle", "oracle"]


def test_claude_runs_start_with_the_access_code(tmp_path: Path) -> None:
    runner = FakeRunner()
    app = create_app(str(tmp_path / "z.db"), public=public(), runner=runner)
    with TestClient(app) as client:
        assert post_run(client, planner="claude", code=CODE).status_code == 200
        lower = client.post(
            "/api/runs",
            json={"scenario_id": "S01-clean", "planner": "naive"},
            headers={ACCESS_CODE_HEADER.lower(): CODE},
        )
        if lower.status_code == 409:  # the previous instant run was still finishing
            lower = post_run(client, planner="naive", code=CODE)
        assert lower.status_code == 200
    assert runner.planners == ["claude", "naive"]


def test_claude_is_off_when_no_access_code_is_configured(tmp_path: Path) -> None:
    runner = FakeRunner()
    app = create_app(str(tmp_path / "z.db"), public=public(access_code=None), runner=runner)
    with TestClient(app) as client:
        response = post_run(client, planner="claude", code=CODE)
        assert response.status_code == 403
        assert "turned off" in response.json()["detail"]
    assert runner.planners == []


def test_access_code_is_never_logged_or_returned(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    seed_runs(tmp_path / "z.db", count=1, at=LONG_AGO, cost_usd=5.0)
    app = create_app(str(tmp_path / "z.db"), public=public(), runner=FakeRunner())
    texts: list[str] = []
    with TestClient(app) as client:
        texts.append(client.get("/api/meta").text)
        texts.append(post_run(client, planner="claude", code=CODE).text)  # 402: over the cap
        texts.append(post_run(client, planner="claude", code=CODE[:-1] + "!").text)  # 403
        oracle = post_run(client, planner="oracle")
        texts.append(oracle.text)
        texts.append(client.get(f"/api/runs/{oracle.json()['run_id']}").text)
        texts.append(client.get("/openapi.json").text)
    assert "public mode on" in caplog.text
    for text in [*texts, caplog.text]:
        assert CODE not in text
        assert CODE[:-1] not in text


# --- spend cap --------------------------------------------------------------------------------


def test_spend_cap_refuses_claude_runs_with_402(tmp_path: Path) -> None:
    seed_runs(tmp_path / "z.db", count=2, at=LONG_AGO, cost_usd=2.75)  # $5.50 recorded
    runner = FakeRunner()
    app = create_app(str(tmp_path / "z.db"), public=public(), runner=runner)
    with TestClient(app) as client:
        response = post_run(client, planner="claude", code=CODE)
        assert response.status_code == 402
        detail = response.json()["detail"]
        assert "spend cap reached" in detail and "$5.50 of $5.00" in detail and "oracle" in detail
        assert post_run(client, planner="oracle").status_code == 200
        meta = client.get("/api/meta").json()
        assert meta["spend_used_usd"] == 5.5 and meta["claude_runs_allowed"] is False
    assert runner.planners == ["oracle"]


def test_spend_cap_is_reached_at_exactly_the_cap(tmp_path: Path) -> None:
    seed_runs(tmp_path / "z.db", count=1, at=LONG_AGO, cost_usd=5.0)
    app = create_app(str(tmp_path / "z.db"), public=public(), runner=FakeRunner())
    with TestClient(app) as client:
        assert post_run(client, planner="claude", code=CODE).status_code == 402


def test_claude_runs_are_allowed_below_the_cap(tmp_path: Path) -> None:
    seed_runs(tmp_path / "z.db", count=1, at=LONG_AGO, cost_usd=4.99)
    runner = FakeRunner()
    app = create_app(str(tmp_path / "z.db"), public=public(), runner=runner)
    with TestClient(app) as client:
        assert post_run(client, planner="claude", code=CODE).status_code == 200
    assert runner.planners == ["claude"]


# --- hourly run limit -------------------------------------------------------------------------


def test_hourly_run_limit_applies_to_every_run(tmp_path: Path) -> None:
    runner = FakeRunner()
    app = create_app(str(tmp_path / "z.db"), public=public(max_runs_per_hour=3), runner=runner)
    with TestClient(app) as client:
        for planner, code in [("oracle", None), (None, None), ("claude", CODE)]:
            assert post_run(client, planner=planner, code=code).status_code == 200
        for planner, code in [("oracle", None), ("claude", CODE)]:
            response = post_run(client, planner=planner, code=code)
            assert response.status_code == 429
            assert "3 runs per hour" in response.json()["detail"]
            assert 1 <= int(response.headers["Retry-After"]) <= 3600
    assert runner.planners == ["oracle", "oracle", "claude"]


def test_rate_window_is_rolling_and_survives_a_restart(tmp_path: Path) -> None:
    t0 = 1_700_000_000.0
    seed_runs(tmp_path / "z.db", count=3, at=t0)  # written before this app (process) existed
    now = [t0 + 3599.5]
    app = create_app(
        str(tmp_path / "z.db"), public=public(max_runs_per_hour=3), runner=FakeRunner(), clock=lambda: now[0]
    )
    with TestClient(app) as client:
        response = post_run(client)
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "1"
        now[0] = t0 + 3600.5
        assert post_run(client).status_code == 200


def test_zero_runs_per_hour_turns_run_starts_off(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "z.db"), public=public(max_runs_per_hour=0), runner=FakeRunner())
    with TestClient(app) as client:
        response = post_run(client)
        assert response.status_code == 403
        assert "turned off" in response.json()["detail"]


def test_private_mode_enforces_none_of_the_public_rules(tmp_path: Path) -> None:
    seed_runs(tmp_path / "z.db", count=20, at=time.time(), cost_usd=1.0)  # 20 recent runs, $20 recorded
    runner = FakeRunner()
    app = create_app(str(tmp_path / "z.db"), public=public(enabled=False), runner=runner)
    with TestClient(app) as client:
        assert post_run(client, planner="naive").status_code == 200
        assert post_run(client, planner="claude").status_code == 200
    assert runner.planners == ["naive", "claude"]


# --- error details and static files -----------------------------------------------------------


def test_public_mode_shows_one_line_errors_instead_of_tracebacks(tmp_path: Path) -> None:
    app = create_app(str(tmp_path / "z.db"), public=public(), runner=FakeRunner(fail="before_start"))
    with TestClient(app) as client:
        response = post_run(client)
        assert response.status_code == 500
        assert response.json()["detail"] == "RuntimeError: sandbox did not start"

    app = create_app(str(tmp_path / "y.db"), public=public(), runner=FakeRunner(fail="after_start"))
    with TestClient(app) as client:
        run_id = post_run(client).json()["run_id"]
        deadline = time.monotonic() + 10
        error = None
        while error is None and time.monotonic() < deadline:
            error = client.get(f"/api/runs/{run_id}").json()["error"]
            time.sleep(0.02)
        assert error == "RuntimeError: engine stopped unexpectedly"


def test_private_mode_keeps_full_tracebacks(tmp_path: Path) -> None:
    app = create_app(
        str(tmp_path / "z.db"), public=public(enabled=False), runner=FakeRunner(fail="before_start")
    )
    with TestClient(app) as client:
        detail = post_run(client).json()["detail"]
        assert detail.startswith("Traceback") and "sandbox did not start" in detail


def test_ui_route_does_not_serve_files_outside_ui_dist(tmp_path: Path) -> None:
    dist = tmp_path / "ui" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("INDEX", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("JS", encoding="utf-8")
    (dist / "favicon.svg").write_text("SVG", encoding="utf-8")
    (tmp_path / "ui" / "secret.txt").write_text("OUTSIDE", encoding="utf-8")
    app = create_app(str(tmp_path / "z.db"), public=public(), ui_dist=dist)
    with TestClient(app) as client:
        for path in ["/..%2Fsecret.txt", "/%2E%2E%2Fsecret.txt", "/..%2F..%2Fui%2Fsecret.txt"]:
            response = client.get(path)
            assert response.status_code == 200 and response.text == "INDEX", path
        # Under /assets, Starlette's StaticFiles refuses the traversal itself (404).
        assert "OUTSIDE" not in client.get("/assets%2F..%2F..%2Fsecret.txt").text
        assert client.get("/").text == "INDEX"
        assert client.get("/favicon.svg").text == "SVG"
        assert client.get("/assets/app.js").text == "JS"
        assert client.get("/runs/some-client-route").text == "INDEX"


# --- end to end -------------------------------------------------------------------------------


@pytest.mark.slow
def test_public_mode_runs_a_real_oracle_scenario_end_to_end(tmp_path: Path) -> None:
    """The docs/UI.md contract works unchanged in public mode for an anonymous visitor."""
    app = create_app(str(tmp_path / "z.db"), default_planner="oracle", public=public(max_runs_per_hour=2))
    with TestClient(app) as client:
        response = client.post("/api/runs", json={"scenario_id": "S01-clean"})  # what the UI sends
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        deadline = time.monotonic() + 60
        status = None
        while time.monotonic() < deadline:
            status = client.get(f"/api/runs/{run_id}").json()["status"]
            if status in TERMINAL:
                break
            time.sleep(0.2)
        assert status == "SUCCESS"
        body = client.get(f"/api/runs/{run_id}/events").text
        kinds = {json.loads(line[6:])["kind"] for line in body.splitlines() if line.startswith("data: ")}
        assert {"state", "plan", "batch", "verify"} <= kinds
        assert client.get(f"/api/runs/{run_id}/report").json()["status"] == "SUCCESS"
        run = client.get(f"/api/runs/{run_id}").json()
        assert run["llm"] == {"calls": 0, "cost_usd": 0.0}
        assert any(r["run_id"] == run_id for r in client.get("/api/runs").json())
        assert client.get("/api/meta").json()["spend_used_usd"] == 0.0
