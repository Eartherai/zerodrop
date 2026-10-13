"""The verifier must stay independent of the agent: it may not import the code it judges.

The project's claim is that the final status comes from a checker the agent cannot influence.
That only holds while the verifier package imports nothing from the engine, the planner, the
mapping language, the ledger or the runner. It may import the shared data models (the report
and record types both sides exchange) and the tracing helper (it only emits spans).
"""

from __future__ import annotations

import ast
from pathlib import Path

VERIFIER = Path(__file__).resolve().parents[1] / "src" / "zerodrop" / "verifier"
ALLOWED = {"zerodrop.models", "zerodrop.telemetry"}


def zerodrop_imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.split(".")[0] == "zerodrop")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == "zerodrop":
                found.update(f"zerodrop.{alias.name}" for alias in node.names)
            elif node.module.split(".")[0] == "zerodrop":
                found.add(node.module)
    return found


def test_the_verifier_imports_only_the_data_models_and_the_tracing_helper() -> None:
    modules = sorted(VERIFIER.glob("*.py"))
    assert modules, "the verifier package was not found"
    imported = set().union(*(zerodrop_imports(path) for path in modules))
    outside = {name for name in imported if not name.startswith("zerodrop.verifier")}
    assert outside <= ALLOWED, f"the verifier imports agent-side code: {sorted(outside - ALLOWED)}"
    assert outside == ALLOWED  # if this shrinks, tighten ALLOWED and the wording in EVIDENCE.md
