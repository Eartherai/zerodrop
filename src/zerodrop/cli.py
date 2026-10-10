"""ZeroDrop command line: run scenarios, evaluate, serve the sandbox or the dashboard API.

Telemetry is initialised before anything imports the Anthropic SDK.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated

import typer

from zerodrop import telemetry

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)

PlannerOpt = Annotated[
    str, typer.Option("--planner", help="claude (real model), oracle or naive (offline fakes)")
]


def _init(planner: str, scenario: str = "") -> None:
    from zerodrop.runner import git_commit

    tags = [f"planner:{planner}", f"commit:{git_commit()}"]
    if scenario:
        tags.append(f"scenario:{scenario}")
    active = telemetry.init_telemetry("zerodrop-migration", tags=tags)
    typer.echo(f"neatlogs tracing: {'on' if active else 'off (NEATLOGS_API_KEY not set)'}", err=True)


@app.command("scenarios")
def list_scenarios() -> None:
    """List the evaluation scenarios."""
    from zerodrop.scenarios import load_scenarios

    for s in load_scenarios():
        typer.echo(f"{s.id:34} expect={s.expect.value:20} {s.title}")


@app.command("run")
def run(
    scenario_id: str,
    planner: PlannerOpt = "oracle",
    db: Annotated[str, typer.Option(help="SQLite ledger path")] = "runs/zerodrop.db",
    json_out: Annotated[Path | None, typer.Option(help="write the outcome as JSON")] = None,
    quiet: Annotated[bool, typer.Option(help="do not print events")] = False,
) -> None:
    """Run one scenario end to end and print the verified outcome."""
    _init(planner, scenario_id)
    from zerodrop.runner import run_scenario
    from zerodrop.scenarios import get_scenario

    Path(db).parent.mkdir(parents=True, exist_ok=True)

    def show(event) -> None:  # type: ignore[no-untyped-def]
        if not quiet:
            entity = f"[{event.entity}] " if event.entity else ""
            typer.echo(f"{event.seq:4} {event.kind:9} {entity}{event.message}")

    try:
        outcome = run_scenario(get_scenario(scenario_id), planner, db_path=db, on_event=show)  # type: ignore[arg-type]
    finally:
        telemetry.shutdown()
    typer.echo(json.dumps(outcome.model_dump(mode="json", exclude={"faults_fired"}), indent=2))
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(outcome.model_dump_json(indent=2), encoding="utf-8")


@app.command("eval")
def evaluate(
    planner: PlannerOpt = "oracle",
    scenarios: Annotated[str, typer.Option(help="comma-separated ids, or 'all'")] = "all",
    exclude_tags: Annotated[str, typer.Option(help="comma-separated tags to skip, e.g. scale")] = "",
    out_dir: Annotated[Path, typer.Option(help="where to write results")] = Path("evidence/eval"),
    label: Annotated[str, typer.Option(help="label for this evaluation, e.g. baseline or improved")] = "",
) -> None:
    """Run many scenarios and write a JSON + Markdown summary with honest metrics."""
    _init(planner)
    from zerodrop.runner import git_commit, run_scenario
    from zerodrop.scenarios import load_scenarios

    chosen = load_scenarios()
    if scenarios != "all":
        wanted = {s.strip() for s in scenarios.split(",") if s.strip()}
        chosen = [s for s in chosen if s.id in wanted]
    skip = {t.strip() for t in exclude_tags.split(",") if t.strip()}
    chosen = [s for s in chosen if not skip.intersection(s.tags)]
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    name = f"{stamp}-{planner}{'-' + label if label else ''}"
    out_dir.mkdir(parents=True, exist_ok=True)
    outcomes = []
    try:
        for s in chosen:
            typer.echo(f"running {s.id} ...", err=True)
            o = run_scenario(s, planner, db_path=str(out_dir / f"{name}.db"))  # type: ignore[arg-type]
            outcomes.append(o)
            typer.echo(
                f"  {o.status.value:20} expected {o.expected.value:20} claimed {o.agent_claimed_status}"
                f" {'OK' if o.matched_expectation else 'MISMATCH'} {o.duration_s:.1f}s",
                err=True,
            )
    finally:
        telemetry.shutdown()
    summary = summarize(outcomes, planner, label, git_commit())
    (out_dir / f"{name}.json").write_text(
        json.dumps({"summary": summary, "outcomes": [o.model_dump(mode="json") for o in outcomes]}, indent=2),
        encoding="utf-8",
    )
    (out_dir / f"{name}.md").write_text(render_markdown(summary, outcomes), encoding="utf-8")
    typer.echo(json.dumps(summary, indent=2))


def summarize(outcomes: list, planner: str, label: str, commit: str) -> dict:  # type: ignore[type-arg]
    n = len(outcomes)
    verified_success = sum(1 for o in outcomes if o.status.value == "SUCCESS")
    matched = sum(1 for o in outcomes if o.matched_expectation)
    false_claims = sum(1 for o in outcomes if o.false_success_claim)
    calls = sum(int(o.metrics.get("llm_calls", 0) or 0) for o in outcomes)
    cost = sum(float(o.metrics.get("llm_cost_usd", o.metrics.get("cost_usd", 0.0)) or 0.0) for o in outcomes)
    durations = sorted(o.duration_s for o in outcomes)
    median = durations[n // 2] if n else 0.0
    return {
        "planner": planner,
        "label": label,
        "git_commit": commit,
        "scenarios": n,
        "matched_expected_outcome": matched,
        "verified_success": verified_success,
        "false_success_claims": false_claims,
        "crash_resumes": sum(1 for o in outcomes if o.crashed_and_resumed),
        "llm_calls": calls,
        "llm_cost_usd": round(cost, 4),
        "cost_per_verified_success_usd": round(cost / verified_success, 4) if verified_success else None,
        "median_duration_s": median,
    }


def render_markdown(summary: dict, outcomes: list) -> str:  # type: ignore[type-arg]
    lines = [
        f"# ZeroDrop evaluation: planner={summary['planner']} {summary['label']}".rstrip(),
        "",
        f"- Commit: `{summary['git_commit']}`",
        f"- Scenarios: {summary['scenarios']}; matched expected outcome: {summary['matched_expected_outcome']}",
        f"- Verified SUCCESS: {summary['verified_success']}; false success claims: {summary['false_success_claims']}",
        f"- LLM calls: {summary['llm_calls']}; LLM cost: ${summary['llm_cost_usd']}; "
        f"cost per verified success: {summary['cost_per_verified_success_usd']}",
        f"- Median duration: {summary['median_duration_s']} s",
        "",
        "| Scenario | Expected | Verifier status | Agent claim | Match | Faults fired | Duration (s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for o in outcomes:
        kinds = ", ".join(sorted({str(f.get("kind")) for f in o.faults_fired})) or "-"
        lines.append(
            f"| {o.scenario_id} | {o.expected.value} | {o.status.value} | "
            f"{o.agent_claimed_status.value if o.agent_claimed_status else '-'} | "
            f"{'yes' if o.matched_expectation else 'NO'} | {kinds} | {o.duration_s} |"
        )
    failures = [o for o in outcomes if o.failed_checks]
    if failures:
        lines += ["", "## Failed verifier checks", ""]
        for o in failures:
            lines.append(f"- **{o.scenario_id}**: " + "; ".join(o.failed_checks)[:600])
    return "\n".join(lines) + "\n"


@app.command("sandbox")
def sandbox(
    seed: int = 7,
    size: str = "demo",
    fault_plan: Annotated[Path | None, typer.Option(help="YAML/JSON fault plan for NovaBill")] = None,
    source_port: int = 8701,
    target_port: int = 8702,
    host: Annotated[str, typer.Option(help="listening interface (0.0.0.0 inside a container)")] = "127.0.0.1",
) -> None:
    """Serve LegacyBill and NovaBill on fixed ports (for manual exploration)."""
    from zerodrop.sandbox import servers

    servers.serve_forever(
        seed, size, servers.load_fault_plan(fault_plan), source_port, target_port, bind_host=host
    )


@app.command("serve")
def serve(
    host: str = "127.0.0.1",
    port: int = 8700,
    planner: PlannerOpt = "oracle",
    db: str = "runs/zerodrop.db",
) -> None:
    """Serve the dashboard API (and the built UI from ui/dist when present)."""
    _init(planner)
    import uvicorn

    from zerodrop.api import create_app

    Path(db).parent.mkdir(parents=True, exist_ok=True)
    uvicorn.run(create_app(db_path=db, default_planner=planner), host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
