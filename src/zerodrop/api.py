"""Dashboard API (docs/UI.md): start scenario runs, stream their events, show verified results."""

from __future__ import annotations

import asyncio
import json
import threading
import traceback
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from zerodrop import telemetry
from zerodrop.ledger import Ledger
from zerodrop.models import TERMINAL_STATUSES, RunEvent
from zerodrop.runner import git_commit, run_scenario
from zerodrop.scenarios import get_scenario, load_scenarios

UI_DIST = Path(__file__).resolve().parents[2] / "ui" / "dist"
SSE_POLL_S = 0.25
SSE_PING_S = 15.0


class StartRun(BaseModel):
    scenario_id: str
    planner: str | None = None


class _Runs:
    """Background run threads; one run at a time keeps the demo predictable."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active: threading.Thread | None = None
        self.errors: dict[str, str] = {}


def create_app(db_path: str = "runs/zerodrop.db", default_planner: str = "oracle") -> FastAPI:
    ledger = Ledger(db_path)
    runs = _Runs()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await asyncio.to_thread(telemetry.shutdown)
        ledger.close()

    app = FastAPI(title="ZeroDrop", lifespan=lifespan)

    @app.get("/api/scenarios")
    def scenarios() -> list[dict[str, Any]]:
        return [
            {"id": s.id, "title": s.title, "description": s.description, "expect": s.expect, "tags": s.tags}
            for s in load_scenarios()
        ]

    @app.post("/api/runs")
    def start_run(body: StartRun) -> dict[str, str]:
        try:
            scenario = get_scenario(body.scenario_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        planner = body.planner or default_planner
        if planner not in ("oracle", "naive", "claude"):
            raise HTTPException(422, "planner must be oracle, naive or claude")
        with runs.lock:
            if runs.active is not None and runs.active.is_alive():
                raise HTTPException(409, "a run is already in progress")
            started = threading.Event()
            holder: dict[str, str] = {}

            def on_event(event: RunEvent) -> None:
                if "run_id" not in holder:
                    holder["run_id"] = event.run_id
                    started.set()

            def work() -> None:
                try:
                    run_scenario(scenario, planner, ledger=ledger, on_event=on_event)  # type: ignore[arg-type]
                except Exception:  # surfaced through GET /api/runs/{id}
                    key = holder.get("run_id", "pending")
                    runs.errors[key] = traceback.format_exc(limit=5)
                finally:
                    started.set()

            runs.active = threading.Thread(target=work, name=f"run-{scenario.id}", daemon=True)
            runs.active.start()
        started.wait(timeout=30)
        if "run_id" not in holder:
            raise HTTPException(500, runs.errors.get("pending", "run did not start"))
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
            "error": record.error or runs.errors.get(run_id),
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

    if UI_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str) -> FileResponse:
            candidate = UI_DIST / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(UI_DIST / "index.html")

    return app
