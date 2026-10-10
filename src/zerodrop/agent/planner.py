"""Mapping planner: an LLM tool loop that explores the systems, dry-runs mappings and submits a MigrationPlan."""

from __future__ import annotations

from typing import Any

from zerodrop import telemetry
from zerodrop.agent.diagnoser import (
    MIGRATION_PLAN_SCHEMA,
    ContractDiagnoser,
    DryRunGate,
    PlannerToolbox,
    mapping_problems,
    submission_key,
    toolbox_tools,
)
from zerodrop.agent.llm import LLMClient, LoopStats, SubmitRejected, SubmitTool, UsageTotals, run_tool_loop
from zerodrop.agent.prompts import PLAN_NUDGE, PLANNER_SYSTEM, render_discovery_message
from zerodrop.config import Settings
from zerodrop.models import ENTITY_ORDER, DiscoveryContext, Entity, MappingSpec, MigrationPlan, RepairContext

MAX_PLAN_TURNS = 12
MAX_REPAIR_TURNS = 8


def plan_entities(ctx: DiscoveryContext) -> list[Entity]:
    """Entities the plan must cover: those in the discovery data (all of them if none is recognised)."""
    known = {e.value: e for e in Entity}
    found = [known[s.entity] for s in ctx.source_entities if s.entity in known]
    return found or list(ENTITY_ORDER)


class _PlanAcceptor:
    """Validates a submit_plan call: pydantic, schema checks, coverage, then the dry-run gate."""

    def __init__(self, ctx: DiscoveryContext, toolbox: PlannerToolbox) -> None:
        self.schema = ctx.target_schema
        self.entities = plan_entities(ctx)
        self.gate = DryRunGate(toolbox)

    def __call__(self, arguments: dict[str, Any]) -> MigrationPlan:
        plan = MigrationPlan.model_validate(arguments)  # ValidationError -> is_error result
        problems = self._coverage_problems(plan)
        for spec in plan.mappings:
            problems += mapping_problems(spec, self.schema)
        if problems:
            raise SubmitRejected(problems)
        key = submission_key(plan.mappings, [e.value for e in plan.entity_order])
        rejection = self.gate.verdict(key, self.gate.failures(plan.mappings), "submit_plan")
        if rejection:
            raise SubmitRejected(rejection)
        return plan.model_copy(
            update={"mappings": [m.model_copy(update={"version": 1}) for m in plan.mappings]}
        )

    def _coverage_problems(self, plan: MigrationPlan) -> list[str]:
        mapped = [m.entity for m in plan.mappings]
        problems = []
        missing = [e.value for e in self.entities if e not in mapped]
        if missing:
            problems.append(f"mappings missing for: {', '.join(missing)}")
        duplicates = sorted({e.value for e in mapped if mapped.count(e) > 1})
        if duplicates:
            problems.append(f"one mapping per entity; duplicated: {', '.join(duplicates)}")
        unordered = [e.value for e in self.entities if e not in plan.entity_order]
        if unordered:
            problems.append(f"entity_order is missing: {', '.join(unordered)}")
        return problems


class ClaudePlanner:
    """The `Planner` implementation backed by Claude (docs/CONTRACTS.md section 4).

    `llm` is an `LLMClient`, or `Settings` to build one with the real Anthropic backend.
    The engine supplies the read-only toolbox via `bind_tools` (or pass `tools=`).
    """

    def __init__(
        self,
        llm: LLMClient | Settings,
        tools: PlannerToolbox | None = None,
        *,
        max_plan_turns: int = MAX_PLAN_TURNS,
        max_repair_turns: int = MAX_REPAIR_TURNS,
    ) -> None:
        self.llm = llm if isinstance(llm, LLMClient) else LLMClient(llm)
        self.tools = tools
        self.max_plan_turns = max_plan_turns
        self.diagnoser = ContractDiagnoser(self.llm, tools, max_turns=max_repair_turns)
        self.last_stats = LoopStats()

    @property
    def usage(self) -> UsageTotals:
        """Cumulative LLM usage (`calls`, `cost_usd`, tokens, served models) for the engine's budget guard."""
        return self.llm.usage

    def bind_tools(self, tools: PlannerToolbox) -> None:
        self.tools = tools
        self.diagnoser.bind_tools(tools)

    @telemetry.span(kind="AGENT", name="mapping-planner")
    def plan(self, ctx: DiscoveryContext) -> MigrationPlan:
        if self.tools is None:
            raise RuntimeError("ClaudePlanner needs the planner toolbox (pass tools= or call bind_tools)")
        submit = SubmitTool(
            name="submit_plan",
            description=(
                "Submit the complete MigrationPlan: entity_order plus one MappingSpec per entity. Call it once "
                "every mapping passes dry_run; planning ends when it is accepted."
            ),
            input_schema=MIGRATION_PLAN_SCHEMA,
            accept=_PlanAcceptor(ctx, self.tools),
        )
        self.last_stats = LoopStats()
        return run_tool_loop(
            self.llm,
            system=PLANNER_SYSTEM,
            user_message=render_discovery_message(ctx),
            tools=toolbox_tools(self.tools),
            submit=submit,
            max_turns=self.max_plan_turns,
            effort=self.llm.settings.effort_plan,
            nudge=PLAN_NUDGE,
            stats=self.last_stats,
        )

    def repair(self, ctx: RepairContext) -> list[MappingSpec]:
        """Delegates to the contract diagnoser; may return mappings for several pending entities."""
        if self.diagnoser.tools is None and self.tools is not None:
            self.diagnoser.bind_tools(self.tools)
        return self.diagnoser.repair(ctx)
