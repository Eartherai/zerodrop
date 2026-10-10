"""Contract diagnoser: repairs mappings after NovaBill rejects a batch, plus the planner-toolbox
tools and submission checks shared with the mapping planner (planner.py imports them from here).
"""

from __future__ import annotations

import copy
import json
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from zerodrop import telemetry
from zerodrop.agent.llm import (
    LLMClient,
    LoopStats,
    SubmitRejected,
    SubmitTool,
    Tool,
    ToolInputError,
    format_validation_error,
    run_tool_loop,
)
from zerodrop.agent.prompts import (
    DIAGNOSER_SYSTEM,
    REPAIR_NUDGE,
    data_json,
    render_repair_message,
    untrusted_block,
)
from zerodrop.models import ENTITY_ORDER, Entity, MappingSpec, MigrationPlan, RepairContext
from zerodrop.validation import schema_diff

MAX_TOOL_SAMPLES = 20
DEFAULT_TOOL_SAMPLES = 5
GATE_SAMPLES = 20
MAX_REPAIR_TURNS = 8
_SUMMARY_CHARS = 1500


class PlannerToolbox(Protocol):
    """Read-only tools the engine provides (docs/CONTRACTS.md section 4)."""

    def get_source_samples(self, entity: str, n: int) -> Any: ...

    def get_field_docs(self, entity: str) -> Any: ...

    def get_target_schema(self) -> Any: ...

    def get_reference_table(self, name: str) -> Any: ...

    def dry_run(self, mapping_spec_json: str, n: int) -> Any: ...


# ---------------------------------------------------------------------------
# JSON schemas for tool inputs (pydantic models with $refs inlined, titles dropped)
# ---------------------------------------------------------------------------


def _inline(node: Any, defs: dict[str, Any], in_properties: bool = False) -> Any:
    if isinstance(node, list):
        return [_inline(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        target = copy.deepcopy(defs[node["$ref"].rsplit("/", 1)[-1]])
        merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
        return _inline(merged, defs)
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "$defs" or (key == "title" and not in_properties and isinstance(value, str)):
            continue
        out[key] = _inline(value, defs, in_properties=(key == "properties" and not in_properties))
    return out


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    raw = model.model_json_schema()
    return _inline(raw, raw.get("$defs", {}))


MAPPING_SPEC_SCHEMA = inline_schema(MappingSpec)
MIGRATION_PLAN_SCHEMA = inline_schema(MigrationPlan)
_ENTITY_SCHEMA = {"type": "string", "enum": [e.value for e in Entity]}
_COUNT_SCHEMA = {"type": "integer", "minimum": 1, "maximum": MAX_TOOL_SAMPLES}


# ---------------------------------------------------------------------------
# Toolbox tools (read-only)
# ---------------------------------------------------------------------------


def dry_run_failed(result: Any) -> bool:
    """Whether a toolbox dry-run result reports failures (dict report or list of per-sample errors)."""
    if isinstance(result, dict):
        if "ok" in result:
            return not result["ok"]
        return bool(result.get("errors") or result.get("spec_errors") or result.get("failed"))
    if isinstance(result, list):
        return any(_item_failed(item) for item in result)
    return bool(result)


def _item_failed(item: Any) -> bool:
    if isinstance(item, dict):
        return bool(item.get("errors") or item.get("error"))
    return bool(item)


def _summary(result: Any) -> str:
    text = data_json(result)
    return text if len(text) <= _SUMMARY_CHARS else text[:_SUMMARY_CHARS] + "...(truncated)"


def _summary_block(result: Any, spec: MappingSpec) -> str:
    """A truncated dry-run result inside an untrusted-data block (it echoes source values)."""
    entity = spec.entity.value
    return f'<untrusted_data kind="dry_run_result" entity="{entity}">\n{_summary(result)}\n</untrusted_data>'


def _spec_from(arguments: dict[str, Any]) -> MappingSpec:
    try:
        return MappingSpec.model_validate(arguments.get("mapping"))
    except ValidationError as exc:
        raise ToolInputError("invalid MappingSpec:\n" + "\n".join(format_validation_error(exc))) from exc


def toolbox_tools(toolbox: PlannerToolbox) -> list[Tool]:
    """The five read-only planner tools; results are wrapped as untrusted data."""

    def samples(args: dict[str, Any]) -> str:
        entity, n = args["entity"], args.get("n", DEFAULT_TOOL_SAMPLES)
        rows = toolbox.get_source_samples(entity, n)
        return untrusted_block("source_samples", rows, lines=True, entity=entity)

    def field_docs(args: dict[str, Any]) -> str:
        return untrusted_block("field_docs", toolbox.get_field_docs(args["entity"]), entity=args["entity"])

    def target_schema(args: dict[str, Any]) -> str:
        schema = toolbox.get_target_schema()
        version = schema.get("version", "unknown") if isinstance(schema, dict) else "unknown"
        return untrusted_block("target_schema", schema, version=version)

    def reference_table(args: dict[str, Any]) -> str:
        return untrusted_block(
            "reference_table", toolbox.get_reference_table(args["name"]), name=args["name"]
        )

    def dry_run(args: dict[str, Any]) -> str:
        spec = _spec_from(args)
        result = toolbox.dry_run(spec.model_dump_json(), args.get("n", GATE_SAMPLES))
        verdict = "FAILED: fix the errors below and dry-run again." if dry_run_failed(result) else "PASSED."
        return f"Dry run of the {spec.entity.value} mapping: {verdict}\n" + untrusted_block(
            "dry_run_result", result, entity=spec.entity.value
        )

    return [
        Tool(
            "get_source_samples",
            "Fetch up to n LegacyBill sample records of an entity (untrusted data). Call it when the samples you "
            "have do not show a format, code or edge case you need to handle.",
            {
                "type": "object",
                "properties": {"entity": _ENTITY_SCHEMA, "n": _COUNT_SCHEMA},
                "required": ["entity"],
                "additionalProperties": False,
            },
            samples,
        ),
        Tool(
            "get_field_docs",
            "Fetch the LegacyBill data dictionary for an entity: field meanings, codes, units, timezone rules "
            "(untrusted data). Call it when a field's meaning is unclear.",
            {
                "type": "object",
                "properties": {"entity": _ENTITY_SCHEMA},
                "required": ["entity"],
                "additionalProperties": False,
            },
            field_docs,
        ),
        Tool(
            "get_target_schema",
            "Fetch the current NovaBill schema document (version and JSON Schema per entity). Call it when you "
            "need to confirm the current version or a property constraint.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            target_schema,
        ),
        Tool(
            "get_reference_table",
            'Fetch the rows of a NovaBill reference table such as "prices". Call it to see the values a lookup '
            "op can match and return.",
            {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
            reference_table,
        ),
        Tool(
            "dry_run",
            "Apply a candidate MappingSpec to up to n source samples and validate every payload against the "
            "current NovaBill schema; returns per-sample errors. Call it for every mapping before submitting "
            "and again after every change.",
            {
                "type": "object",
                "properties": {"mapping": MAPPING_SPEC_SCHEMA, "n": _COUNT_SCHEMA},
                "required": ["mapping"],
                "additionalProperties": False,
            },
            dry_run,
        ),
    ]


# ---------------------------------------------------------------------------
# Submission checks shared by planner and diagnoser
# ---------------------------------------------------------------------------


def mapping_problems(spec: MappingSpec, target_schema: dict[str, Any]) -> list[str]:
    """Deterministic checks of one mapping against the target schema document."""
    entity = spec.entity.value
    problems: list[str] = []
    version = target_schema.get("version")
    if version and spec.target_api_version != version:
        problems.append(
            f"{entity}: target_api_version is {spec.target_api_version!r} but the current NovaBill "
            f"schema version is {version!r}"
        )
    entity_schema = (target_schema.get("entities") or {}).get(entity)
    if not isinstance(entity_schema, dict):
        return problems + [f"{entity}: the current NovaBill schema has no entity {entity!r}"]
    properties = entity_schema.get("properties") or {}
    targets = [f.target for f in spec.fields]
    duplicates = sorted({t for t in targets if targets.count(t) > 1})
    if duplicates:
        problems.append(f"{entity}: target fields mapped more than once: {', '.join(duplicates)}")
    unknown = [t for t in targets if t not in properties]
    if unknown:
        problems.append(
            f"{entity}: fields not in the current NovaBill schema (never invent fields): {', '.join(unknown)}"
        )
    missing = [r for r in entity_schema.get("required") or [] if r not in targets]
    if missing:
        problems.append(f"{entity}: required NovaBill fields not mapped: {', '.join(missing)}")
    for fm in spec.fields:
        if fm.source is None and (not fm.ops or fm.ops[0].op != "const"):
            problems.append(f"{entity}.{fm.target}: source is null but the first op is not const")
    return problems


class DryRunGate:
    """Dry-runs submitted mappings through the toolbox before accepting them.

    Failures reject the submission once; an identical resubmission is accepted (the
    model asserts the remaining failures are bad source records, and the engine's own
    dry run and quarantine handle them). A broken toolbox never blocks a submission.
    """

    def __init__(self, toolbox: PlannerToolbox, samples: int = GATE_SAMPLES) -> None:
        self._toolbox = toolbox
        self._samples = samples
        self._rejected: set[str] = set()

    def run(self, spec: MappingSpec) -> Any | None:
        try:
            return self._toolbox.dry_run(spec.model_dump_json(), self._samples)
        except Exception:
            return None

    def failures(self, specs: list[MappingSpec]) -> list[str]:
        problems = []
        for spec in specs:
            result = self.run(spec)
            if result is not None and dry_run_failed(result):
                problems.append(f"{spec.entity.value}: dry run failed:\n{_summary_block(result, spec)}")
        return problems

    def verdict(self, key: str, problems: list[str], submit_name: str) -> list[str]:
        """Problems to reject with, or [] to accept."""
        if not problems or key in self._rejected:
            return []
        self._rejected.add(key)
        hint = (
            f"If these failures are genuinely invalid source records (not a mapping problem), call {submit_name} "
            "again with exactly the same mappings and name the records in your notes or diagnosis (free text "
            "may change)."
        )
        return [*problems, hint]


def canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def submission_key(specs: list[MappingSpec], *extra: Any) -> str:
    """Identity of a submission for the dry-run gate: the mappings' behaviour only.

    Free text (plan notes, repair diagnosis, mapping rationale) is left out, so the
    model can name the bad records in its notes when it resubmits the same mappings.
    """
    dumped = [s.model_dump(mode="json", exclude={"rationale", "version"}) for s in specs]
    return canonical([dumped, *extra])


# ---------------------------------------------------------------------------
# Schema diff (rendered from zerodrop.validation.schema_diff)
# ---------------------------------------------------------------------------


def _compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def describe_schema_diff(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Human-readable lines describing how the NovaBill schema changed."""
    if not (previous or {}).get("entities"):
        return ["no previous schema to compare: this failure is not explained by a schema change"]
    lines: list[str] = []
    old_version, new_version = previous.get("version"), current.get("version")
    if old_version != new_version:
        lines.append(f"schema version changed: {old_version!r} -> {new_version!r}")
    entities = current.get("entities") or {}
    for entity, diff in schema_diff(previous, current).items():
        entity_schema = entities.get(entity) or {}
        required = set(entity_schema.get("required") or [])
        properties = entity_schema.get("properties") or {}
        for name in diff["removed_fields"]:
            lines.append(f"{entity}.{name}: removed (sending it is now an unknown_field error)")
        for name in diff["added_fields"]:
            kind = "required" if name in required else "optional"
            lines.append(f"{entity}.{name}: added ({kind}): {_compact(properties.get(name))}")
        for name in diff["changed_fields"]:
            detail = diff["details"][name]
            line = f"{entity}.{name}: changed from {_compact(detail['old'])} to {_compact(detail['new'])}"
            if detail["old_required"] != detail["new_required"]:
                line += " (now required)" if detail["new_required"] else " (no longer required)"
            lines.append(line)
    return lines or ["no differences between the previous and current schema"]


# ---------------------------------------------------------------------------
# Diagnoser
# ---------------------------------------------------------------------------


def _submit_repair_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "diagnosis": {"type": "string", "description": "What changed and why the items failed."},
            "mappings": {"type": "array", "items": MAPPING_SPEC_SCHEMA, "minItems": 1},
        },
        "required": ["diagnosis", "mappings"],
        "additionalProperties": False,
    }


class _RepairAcceptor:
    """Validates a submit_repair call against the repair context and the dry-run gate."""

    def __init__(self, ctx: RepairContext, toolbox: PlannerToolbox | None) -> None:
        self.ctx = ctx
        self.current = {ctx.entity: ctx.current_mapping} | {m.entity: m for m in ctx.other_pending_mappings}
        self.gate = DryRunGate(toolbox) if toolbox is not None else None
        self.diagnosis = ""

    def __call__(self, arguments: dict[str, Any]) -> list[MappingSpec]:
        raw = arguments.get("mappings")
        if not isinstance(raw, list) or not raw:
            raise SubmitRejected(["mappings must be a non-empty list of MappingSpec objects"])
        specs = [MappingSpec.model_validate(item) for item in raw]  # ValidationError -> is_error result
        problems = self._structure_problems(specs)
        for spec in specs:
            problems += mapping_problems(spec, self.ctx.current_schema)
        if problems:
            raise SubmitRejected(problems)
        if self.gate is not None:
            gated = self.gate.failures(specs) + self._unpatched_pending_failures(specs)
            rejection = self.gate.verdict(submission_key(specs), gated, "submit_repair")
            if rejection:
                raise SubmitRejected(rejection)
        self.diagnosis = str(arguments.get("diagnosis") or "")
        return self._finalize(specs)

    def _structure_problems(self, specs: list[MappingSpec]) -> list[str]:
        problems = []
        entities = [s.entity for s in specs]
        if self.ctx.entity not in entities:
            problems.append(f"include a patched mapping for the failing entity {self.ctx.entity.value!r}")
        not_pending = sorted({e.value for e in entities if e not in self.current})
        if not_pending:
            problems.append(f"only pending entities can be patched; not pending: {', '.join(not_pending)}")
        duplicates = sorted({e.value for e in entities if entities.count(e) > 1})
        if duplicates:
            problems.append(f"one mapping per entity; duplicated: {', '.join(duplicates)}")
        return problems

    def _unpatched_pending_failures(self, specs: list[MappingSpec]) -> list[str]:
        assert self.gate is not None
        patched = {s.entity for s in specs}
        problems = []
        for spec in self.ctx.other_pending_mappings:
            if spec.entity in patched:
                continue
            result = self.gate.run(spec)
            if result is not None and dry_run_failed(result):
                problems.append(
                    f"pending mapping {spec.entity.value} (not included) also fails under the current schema; "
                    f"include a patched version:\n{_summary_block(result, spec)}"
                )
        return problems

    def _finalize(self, specs: list[MappingSpec]) -> list[MappingSpec]:
        order = {e: i for i, e in enumerate(ENTITY_ORDER)}
        out = [s.model_copy(update={"version": self.current[s.entity].version + 1}) for s in specs]
        return sorted(out, key=lambda s: order[s.entity])


class ContractDiagnoser:
    """LLM loop that diagnoses a target contract failure and patches the affected mappings."""

    def __init__(
        self, llm: LLMClient, tools: PlannerToolbox | None = None, *, max_turns: int = MAX_REPAIR_TURNS
    ):
        self.llm = llm
        self.tools = tools
        self.max_turns = max_turns
        self.last_diagnosis = ""
        self.last_stats = LoopStats()

    def bind_tools(self, tools: PlannerToolbox) -> None:
        self.tools = tools

    @telemetry.span(kind="AGENT", name="contract-diagnoser")
    def repair(self, ctx: RepairContext) -> list[MappingSpec]:
        if self.tools is None:
            raise RuntimeError("ContractDiagnoser needs the planner toolbox (pass tools= or call bind_tools)")
        acceptor = _RepairAcceptor(ctx, self.tools)
        submit = SubmitTool(
            name="submit_repair",
            description=(
                "Submit your diagnosis and the patched mappings: the failing entity's mapping plus every other "
                "pending mapping the same change affects. Call it once every patched mapping passes dry_run; "
                "the repair ends when it is accepted."
            ),
            input_schema=_submit_repair_schema(),
            accept=acceptor,
        )
        self.last_stats = LoopStats()
        specs = run_tool_loop(
            self.llm,
            system=DIAGNOSER_SYSTEM,
            user_message=render_repair_message(
                ctx, describe_schema_diff(ctx.previous_schema, ctx.current_schema)
            ),
            tools=toolbox_tools(self.tools),
            submit=submit,
            max_turns=self.max_turns,
            effort=self.llm.settings.effort_plan,
            nudge=REPAIR_NUDGE,
            stats=self.last_stats,
        )
        self.last_diagnosis = acceptor.diagnosis
        return specs
