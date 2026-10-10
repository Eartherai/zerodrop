"""Dashboard API (docs/UI.md): start scenario runs, stream their events, show verified results.

Public demo mode (``zerodrop.public_mode``, env prefix ``ZERODROP_PUBLIC_``) adds guard rails
for an internet-facing deployment: without the access code only oracle runs ($0) may start,
runs per hour are capped, Claude runs stop at a spend cap, and error details are reduced to
one line. ``GET /api/meta`` reports the policy (never the access code).
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import traceback
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from zerodrop import public_mode, telemetry
from zerodrop.ledger import Ledger
from zerodrop.models import TERMINAL_STATUSES, RunEvent
from zerodrop.public_mode import ACCESS_CODE_HEADER, PublicSettings, Refusal
from zerodrop.runner import git_commit, run_scenario
from zerodrop.scenarios import get_scenario, load_scenarios

UI_DIST = Path(__file__).resolve().parents[2] / "ui" / "dist"
SSE_POLL_S = 0.25
SSE_PING_S = 15.0
PLANNERS = ("oracle", "naive", "claude")

logger = logging.getLogger(__name__)


class StartRun(BaseModel):
    scenario_id: str
    planner: str | None = None


class _Runs:
    """Background run threads; one run at a time keeps the demo predictable."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active: threading.Thread | None = None
        self.errors: dict[str, str] = {}


def _trace_id(ledger: Ledger, run_id: str) -> str | None:
    """Neatlogs trace id of the run's latest invocation (the engine logs it as an event), if traced."""
    ids = [e.data["neatlogs_trace_id"] for e in ledger.events_since(run_id) if "neatlogs_trace_id" in e.data]
    return ids[-1] if ids else None


def _spend_used_usd(ledger: Ledger) -> float:
    """Cumulative LLM cost over every run in the ledger (runs.cost_usd).

    The ledger has no aggregate method; one SUM query avoids loading every run and its report.
    """
    rows = ledger._query("SELECT COALESCE(SUM(cost_usd), 0) FROM runs")
    return float(rows[0][0])


def _http(refusal: Refusal) -> HTTPException:
    return HTTPException(refusal.status, refusal.detail, headers=refusal.headers or None)


def create_app(
    db_path: str = "runs/zerodrop.db",
    default_planner: str = "oracle",
    *,
    public: PublicSettings | None = None,
    runner: Callable[..., Any] = run_scenario,
    clock: Callable[[], float] = time.time,
    ui_dist: Path | None = None,
) -> FastAPI:
    """Build the dashboard app.

    ``public`` defaults to ``PublicSettings()`` (environment / .env). ``runner``, ``clock`` and
    ``ui_dist`` exist for tests: they replace ``run_scenario``, the rate-limit clock and the
    directory of the built UI.
    """
    ledger = Ledger(db_path)
    runs = _Runs()
    public = public if public is not None else PublicSettings()
    if public.enabled:
        logger.warning(
            "public mode on: oracle runs open to everyone; other planners %s; "
            "Claude spend cap $%.2f; at most %d runs per hour",
            "need the access code" if public.access_code is not None else "turned off (no access code set)",
            public.spend_cap_usd,
            public.max_runs_per_hour,
        )

    def shown_error(text: str | None) -> str | None:
        """Tracebacks are useful locally; in public mode only their last line is shown."""
        if text is None or not public.enabled:
            return text
        lines = [line for line in text.strip().splitlines() if line.strip()]
        return lines[-1][:300] if lines else None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await asyncio.to_thread(telemetry.shutdown)
        ledger.close()

    app = FastAPI(title="ZeroDrop", lifespan=lifespan)

    @app.get("/api/meta")
    def meta() -> dict[str, Any]:
        spend = _spend_used_usd(ledger)
        return {
            "public_mode": public.enabled,
            "claude_runs_allowed": public_mode.claude_runs_allowed(public, spend),
            "spend_used_usd": round(spend, 6),
            "spend_cap_usd": public.spend_cap_usd if public.enabled else None,  # null: not enforced
            "default_planner": public_mode.default_planner(default_planner, public),
        }

    @app.get("/api/scenarios")
    def scenarios() -> list[dict[str, Any]]:
        return [
            {"id": s.id, "title": s.title, "description": s.description, "expect": s.expect, "tags": s.tags}
            for s in load_scenarios()
        ]

    @app.post("/api/runs")
    def start_run(
        body: StartRun,
        access_code: Annotated[str | None, Header(alias=ACCESS_CODE_HEADER)] = None,
    ) -> dict[str, str]:
        try:
            scenario = get_scenario(body.scenario_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        planner = public_mode.effective_planner(body.planner, default_planner, public)
        if planner not in PLANNERS:
            raise HTTPException(422, "planner must be oracle, naive or claude")
        refusal = public_mode.check_access(public, planner, access_code)
        if refusal is not None:
            raise _http(refusal)
        with runs.lock:
            if runs.active is not None and runs.active.is_alive():
                raise HTTPException(409, "a run is already in progress")
            if public.enabled:
                limit = public.max_runs_per_hour
                recent = [r.created_at for r in ledger.list_runs(limit=limit)] if limit > 0 else []
                refusal = public_mode.check_budget(
                    public,
                    planner,
                    spend_used_usd=_spend_used_usd(ledger),
                    recent_run_times=recent,
                    now=clock(),
                )
                if refusal is not None:
                    raise _http(refusal)
            started = threading.Event()
            holder: dict[str, str] = {}

            def on_event(event: RunEvent) -> None:
                if "run_id" not in holder:
                    holder["run_id"] = event.run_id
                    started.set()

            def work() -> None:
                try:
                    runner(scenario, planner, ledger=ledger, on_event=on_event)
                except Exception:  # surfaced through GET /api/runs/{id}
                    key = holder.get("run_id", "pending")
                    runs.errors[key] = traceback.format_exc(limit=5)
                finally:
                    started.set()

            runs.active = threading.Thread(target=work, name=f"run-{scenario.id}", daemon=True)
            runs.active.start()
        started.wait(timeout=30)
        if "run_id" not in holder:
            raise HTTPException(500, shown_error(runs.errors.get("pending")) or "run did not start")
        return {"run_id": holder["run_id"]}

    @app.get("/api/runs")
    def list_runs() -> list[dict[str, Any]]:
        return [
            {"run_id": r.run_id, "status": r.status, "scenario_id": r.scenario, "created_at": r.created_at}
            for r in ledger.list_runs(limit=100)
        ]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        record = ledger.get_run(run_id)
        if record is None:
            raise HTTPException(404, "unknown run")
        mapping_versions: dict[str, int] = {}
        for entity in ("customers", "subscriptions", "invoices"):
            latest = ledger.latest_mapping(run_id, entity)
            if latest is not None:
                mapping_versions[entity] = latest.version
        return {
            "run_id": record.run_id,
            "status": record.status,
            "agent_claimed_status": record.agent_claimed_status,
            "goal": record.goal,
            "scenario_id": record.scenario,
            "counts": ledger.counts(run_id),
            "mapping_versions": mapping_versions,
            "llm": {"calls": record.llm_calls, "cost_usd": record.cost_usd},
            "error": record.error or shown_error(runs.errors.get(run_id)),
            "trace_id": _trace_id(ledger, run_id),
            "trace_url": None,
            "commit": git_commit() or None,
        }

    @app.get("/api/runs/{run_id}/report")
    def get_report(run_id: str) -> Any:
        record = ledger.get_run(run_id)
        report = record.report() if record else None
        if report is None:
            raise HTTPException(404, "no report yet")
        return report.model_dump(mode="json")

    @app.get("/api/runs/{run_id}/mappings")
    def get_mappings(run_id: str) -> list[dict[str, Any]]:
        if ledger.get_run(run_id) is None:
            raise HTTPException(404, "unknown run")
        out: list[dict[str, Any]] = []
        for entity in ("customers", "subscriptions", "invoices"):
            for spec in ledger.mapping_history(run_id, entity):
                out.append({"entity": entity, "version": spec.version, "spec": spec.model_dump(mode="json")})
        return out

    @app.get("/api/runs/{run_id}/events")
    async def stream_events(run_id: str, after_seq: int = 0) -> StreamingResponse:
        if ledger.get_run(run_id) is None:
            raise HTTPException(404, "unknown run")

        async def gen() -> AsyncIterator[str]:
            last = after_seq
            idle = 0.0
            while True:
                events = await asyncio.to_thread(ledger.events_since, run_id, last)
                for event in events:
                    last = event.seq
                    yield f"id: {event.seq}\ndata: {json.dumps(event.model_dump(mode='json'))}\n\n"
                    idle = 0.0
                record = await asyncio.to_thread(ledger.get_run, run_id)
                if record is not None and record.status in TERMINAL_STATUSES and not events:
                    return
                await asyncio.sleep(SSE_POLL_S)
                idle += SSE_POLL_S
                if idle >= SSE_PING_S:
                    idle = 0.0
                    yield ": ping\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    dist = ui_dist if ui_dist is not None else UI_DIST
    if dist.is_dir():
        root = dist.resolve()
        if (root / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str) -> FileResponse:
            # Resolve and require the result inside ui/dist: "/..%2F.." must not reach other files
            # (on a server, /proc/self/environ would expose the keys).
            candidate = (root / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
            return FileResponse(root / "index.html")

    return app
