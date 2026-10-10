"""The ZeroDrop migration engine: a persisted state machine that executes the planner's mappings.

    CREATED -> DISCOVERING -> PLANNING -> DRY_RUN -> EXECUTING <-> RECOVERING -> VERIFYING
            -> SUCCESS | PARTIAL_SUCCESS | FAILED | WAITING_FOR_APPROVAL

The LLM planner only proposes `MappingSpec`s; this module runs them deterministically,
checkpoints every record in the ledger, classifies failures (`zerodrop.classify`) and
applies the recovery policy of docs/CONTRACTS.md section 5. The final status comes
from the independent verifier; the engine's own belief is stored separately as
`agent_claimed_status`.

Choices where the contract is silent:
- `crash_after_batches=N` raises `SimulatedCrash` right after the N-th batch response
  arrives and *before* it is checkpointed (the worst case for duplicates).
- Quarantine reasons start with the NovaBill-equivalent error code, e.g.
  ``"invalid_reference: customer_id: ..."`` (DSL ``unresolved_reference`` maps to
  ``invalid_reference``), so they line up with the fixture's expected reason codes.
- Rotated credentials are installed with ``target.set_token(token)`` when the target has
  it, otherwise by replacing the connector's ``_token_provider``.
- Budgets are per invocation for wall time; LLM calls/cost accumulate across resumes.
- A failure before any write ends the run FAILED without verification; once executing
  started, every stop goes through the verifier for an honest report, except
  WAITING_FOR_APPROVAL (credentials are needed first; resume later).
- 422s in a response that announces a new NovaBill-Version are held and re-sent after
  re-validation instead of being quarantined.
- The dry run also asks for a repair when a minority code repeats (>= 2 samples and >= 10 %);
  if repair rounds run out on such record-level failures only, the run proceeds and those
  records are quarantined. Majority or structural failures still halt the run.
- An unresolved reference to a parent that was quarantined or excluded is a cascade
  (DATA, ``invalid_reference``), never evidence that the mapping is wrong; so is an orphan
  (parent absent from the source) once the mapping has resolved references for other records.
- When a suspected CONTRACT failure ends with the planner keeping the mapping and the mapping
  passing the dry run, the failed records are quarantined (DATA) instead of re-sent, so a small
  final batch of bad records cannot halt the run.
- Retry-After is honored in full up to 60 s (our own backoff is capped at 5 s); a wait that would
  outlive the wall-clock budget stops the run as BUDGET instead of sleeping.
"""

from __future__ import annotations

import copy
import json
import random
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from zerodrop import telemetry
from zerodrop.classify import DATA_ONLY_CODES, classify_batch, classify_exception, contract_signal
from zerodrop.config import Settings
from zerodrop.connectors.errors import SourceError
from zerodrop.dsl import apply_mapping, error_code, error_field, matches_exclusion
from zerodrop.ledger import Ledger, RunRecord
from zerodrop.models import (
    ENTITY_ORDER,
    DiscoveryContext,
    Entity,
    EventKind,
    FailedItemSample,
    FailureClass,
    MappingSpec,
    MigrationPlan,
    PreservationContract,
    ReconciliationReport,
    RecordState,
    RepairContext,
    RunEvent,
    RunStatus,
    SourceEntityInfo,
    TargetItemError,
)
from zerodrop.validation import entity_schema, schema_diff, validate_payload

DISCOVERY_SAMPLES = 8
DRY_RUN_SAMPLES = 200
MAX_TOOL_SAMPLES = 200
MAX_FAILED_SAMPLES = 10
MAX_BATCH_ITEMS = 50
SOURCE_PAGE_LIMIT = 200
BACKOFF_BASE_S = 0.25
BACKOFF_CAP_S = 5.0
RETRY_AFTER_MAX_S = 60.0  # a server-requested wait is honored in full up to this ceiling

DEFAULT_ID_FIELDS: dict[str, str] = {"customers": "cust_id", "subscriptions": "sub_id", "invoices": "inv_id"}
# Error codes that only a wrong mapping produces (target 422 codes and DSL spec errors).
STRUCTURAL_MAPPING_CODES: frozenset[str] = frozenset(
    {"unknown_field", "missing_field", "missing_param", "invalid_param", "duplicate_target"}
)
# DSL error codes -> the NovaBill 422 code a quarantine reason carries.
DSL_TO_TARGET_CODE: dict[str, str] = {
    "unresolved_reference": "invalid_reference",
    "lookup_miss": "invalid_reference",
    "required_null": "missing_field",
    "unmapped_value": "invalid_value",
    "parse_error": "invalid_value",
    "invalid_type": "invalid_value",
    "non_integral": "invalid_value",
    "out_of_range": "invalid_value",
}
_VERIFIER_STATUSES = frozenset({RunStatus.SUCCESS, RunStatus.PARTIAL_SUCCESS, RunStatus.FAILED})


class SimulatedCrash(RuntimeError):
    """Raised when `crash_after_batches` is reached, to emulate the process dying mid-run."""


class RunResult(BaseModel):
    run_id: str
    status: RunStatus
    agent_claimed_status: RunStatus | None = None
    report: ReconciliationReport | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class _Halt(Exception):
    """Stop executing safely; the run is then verified (or failed if nothing was written)."""

    def __init__(self, failure: FailureClass, message: str) -> None:
        super().__init__(message)
        self.failure = failure
        self.message = message


class _AwaitApproval(Exception):
    """Credentials were rejected and could not be refreshed: wait for a human."""


# ---------------------------------------------------------------------------
# Planner tools and dry runs
# ---------------------------------------------------------------------------


@dataclass
class DryRunReport:
    """Result of applying one mapping to source samples and validating against the target schema."""

    entity: str
    mapping_version: int
    api_version: str | None
    checked: int
    excluded: int
    failures: list[tuple[str, dict[str, Any] | None, list[str]]]
    hard_problem: bool  # most samples fail alike, or a structural error: the mapping is wrong
    systematic_codes: list[str]  # minority codes repeated across samples: probably fixable by the mapping
    dominant_code: str | None

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def mapping_problem(self) -> bool:
        return self.hard_problem or bool(self.systematic_codes)

    def failed_samples(self, limit: int = MAX_FAILED_SAMPLES) -> list[FailedItemSample]:
        """Failures as repair evidence; status 422 = schema rejection, 0 = failed before a payload existed."""
        return [
            FailedItemSample(
                source_id=source_id,
                payload=payload or {},
                status=422 if payload is not None else 0,
                error=TargetItemError(
                    code=_primary_code(errors) or "invalid_value",
                    field=error_field(errors[0]) if errors else None,
                    message="; ".join(errors)[:500],
                ),
            )
            for source_id, payload, errors in self.failures[:limit]
        ]

    def as_dict(self, limit: int = 20) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "mapping_version": self.mapping_version,
            "target_api_version": self.api_version,
            "checked": self.checked,
            "excluded": self.excluded,
            "passed": self.checked - len(self.failures),
            "failed": len(self.failures),
            "ok": self.ok,
            "mapping_problem": self.mapping_problem,
            "systematic_codes": self.systematic_codes,
            "dominant_code": self.dominant_code,
            "errors": [
                {"source_id": source_id, "errors": errors[:5]}
                for source_id, _, errors in self.failures[:limit]
            ],
        }


class _MappingContext:
    """The DSL context: id map plus target reference tables. Dry runs use placeholder ids."""

    def __init__(
        self,
        id_map: Callable[[str, str], str | None] | None,
        table: Callable[[str], list[dict[str, Any]]],
        placeholder_refs: bool,
    ) -> None:
        self._id_map = id_map
        self._table = table
        self._placeholder_refs = placeholder_refs

    def id_map(self, entity: str, source_id: str) -> str | None:
        found = self._id_map(str(entity), source_id) if self._id_map else None
        if found is None and self._placeholder_refs:
            return f"dryrun_{entity}_{source_id}"
        return found

    def lookup(self, table: str, match_field: str, value: Any, return_field: str) -> Any | None:
        for row in self._table(table):
            if row.get(match_field) == value:
                return row.get(return_field)
        return None


def _direct_call(fn: Callable[..., Any], *args: Any, **_: Any) -> Any:
    return fn(*args)


class PlannerTools:
    """Read-only tools for the planner, backed by the connectors, the DSL and the validator.

    The engine shares these caches (source records, field docs, target schema,
    reference tables), so the planner always sees what the engine executes against.
    Tool methods return plain JSON-compatible data and never write anything.
    """

    def __init__(
        self,
        source: Any,
        target: Any,
        *,
        call: Callable[..., Any] | None = None,
        id_map: Callable[[str, str], str | None] | None = None,
    ) -> None:
        self._source = source
        self._target = target
        self.attach(call, id_map)
        self.reset()

    def attach(
        self,
        call: Callable[..., Any] | None = None,
        id_map: Callable[[str, str], str | None] | None = None,
    ) -> None:
        """Route reads through `call` (the engine's retry policy) and resolve refs with `id_map`."""
        self._call = call or _direct_call
        self._id_map = id_map

    def reset(self) -> None:
        self._records: dict[str, list[dict[str, Any]]] = {}
        self._account: dict[str, Any] | None = None
        self._field_docs: dict[str, Any] | None = None
        self._schema: dict[str, Any] | None = None
        self._tables: dict[str, list[dict[str, Any]]] = {}

    # -- tool surface (what the planner calls) ----------------------------------

    def get_source_samples(self, entity: str, n: int = 5) -> list[dict[str, Any]]:
        if entity not in DEFAULT_ID_FIELDS:
            return []
        return copy.deepcopy(spread(self.records(entity), _clamp(n, 1, MAX_TOOL_SAMPLES)))

    def get_field_docs(self, entity: str) -> dict[str, str]:
        return dict(self.field_docs().get(entity) or {})

    def get_target_schema(self) -> dict[str, Any]:
        return copy.deepcopy(self.schema())

    def get_reference_table(self, name: str) -> list[dict[str, Any]]:
        return copy.deepcopy(self.reference_table(name))

    def dry_run(self, mapping_spec_json: str | dict[str, Any] | MappingSpec, n: int = 20) -> dict[str, Any]:
        """Apply a mapping to n source samples and validate each payload against the current schema."""
        try:
            spec = _coerce_spec(mapping_spec_json)
        except (ValidationError, ValueError, TypeError) as exc:
            return {"ok": False, "spec_errors": _spec_errors(exc)}
        return self.check_mapping(spec, _clamp(n, 1, MAX_TOOL_SAMPLES)).as_dict()

    # -- engine-facing ------------------------------------------------------------

    def account(self) -> dict[str, Any]:
        if self._account is None:
            self._account = self._call(self._source.account, system="source", label="source account")
        return self._account

    def field_docs(self) -> dict[str, Any]:
        if self._field_docs is None:
            self._field_docs = self._call(self._source.field_docs, system="source", label="source field docs")
        return self._field_docs

    def loaded(self, entity: str) -> bool:
        return entity in self._records

    def records(self, entity: str) -> list[dict[str, Any]]:
        if entity not in self._records:
            self._records[entity] = self._load_records(entity)
        return self._records[entity]

    def schema(self) -> dict[str, Any]:
        if self._schema is None:
            self._schema = self._call(self._target.schema, system="target", label="target schema")
        return self._schema

    def reference_table(self, name: str) -> list[dict[str, Any]]:
        if name not in self._tables:
            if name != "prices":  # the only reference table the connector exposes
                return []
            self._tables[name] = list(self._call(self._target.prices, system="target", label="prices"))
        return self._tables[name]

    def reference_tables(self) -> dict[str, list[dict[str, Any]]]:
        names = list((self.schema().get("reference_tables") or {"prices": ""}).keys())
        return {name: self.reference_table(name) for name in names if self.reference_table(name)}

    def refresh_target(self) -> dict[str, Any]:
        """Refetch the target schema and reference tables (after a contract change)."""
        self._schema = None
        self._tables = {}
        schema = self.schema()
        self.reference_tables()
        return schema

    def check_mapping(self, spec: MappingSpec, n: int = DRY_RUN_SAMPLES) -> DryRunReport:
        entity = spec.entity.value
        try:
            schema = entity_schema(self.schema(), entity)
        except KeyError:
            schema = None
        ctx = _MappingContext(self._id_map, self.reference_table, placeholder_refs=True)
        failures: list[tuple[str, dict[str, Any] | None, list[str]]] = []
        codes: list[str | None] = []
        excluded = 0
        for index, record in enumerate(spread(self.records(entity), n)):
            if matches_exclusion(spec, record):
                excluded += 1
                continue
            payload, errors = apply_mapping(spec, record, ctx)
            if payload is not None:
                errors = (
                    validate_payload(schema, payload)
                    if schema is not None
                    else [f"<schema>: unknown_entity: target schema has no entity {entity!r}"]
                )
            codes.append(_primary_code(errors) if errors else None)
            if errors:
                failures.append((source_id_of(spec, record) or f"row-{index}", payload, errors))
        suspect, dominant = contract_signal(codes, structural=STRUCTURAL_MAPPING_CODES)
        structural = any(
            error_code(error) in STRUCTURAL_MAPPING_CODES | {"unknown_entity"}
            for _, _, errors in failures
            for error in errors
        )
        return DryRunReport(
            entity=entity,
            mapping_version=spec.version,
            api_version=self.schema().get("version"),
            checked=len(codes),
            excluded=excluded,
            failures=failures,
            hard_problem=suspect or structural,
            systematic_codes=_systematic_codes(codes),
            dominant_code=dominant,
        )

    def _load_records(self, entity: str) -> list[dict[str, Any]]:
        page = getattr(self._source, "page", None)
        label = f"source {entity}"
        if not callable(page):
            return list(
                self._call(lambda: list(self._source.iter_records(entity)), system="source", label=label)
            )
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            items, cursor = self._call(page, entity, cursor, SOURCE_PAGE_LIMIT, system="source", label=label)
            rows.extend(items)
            if cursor is None:
                return rows
            if cursor in seen:  # never continue on a truncated read: the run would claim success wrongly
                raise SourceError(f"pagination loop for {entity}: cursor {cursor!r} repeated")
            seen.add(cursor)


def spread(items: Sequence[Any], n: int) -> list[Any]:
    """Up to n items evenly spaced over the sequence (deterministic, keeps first and last)."""
    total = len(items)
    if n >= total:
        return list(items)
    if n <= 0:
        return []
    if n == 1:
        return [items[0]]
    indices = sorted({(2 * i * (total - 1) + (n - 1)) // (2 * (n - 1)) for i in range(n)})
    return [items[i] for i in indices]


def source_id_of(spec: MappingSpec, record: Mapping[str, Any]) -> str | None:
    """The source record's id: the source field mapped to `external_id` (or the entity's default)."""
    id_field = next(
        (fm.source for fm in spec.fields if fm.target == "external_id" and fm.source),
        DEFAULT_ID_FIELDS.get(spec.entity.value),
    )
    value = record.get(id_field) if id_field and isinstance(record, Mapping) else None
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


@dataclass
class _Item:
    source_id: str
    record: dict[str, Any]
    payload: dict[str, Any]
    external_id: str
    key: str
    mapping_version: int


@dataclass
class _RunState:
    run_id: str
    goal: str
    contract: PreservationContract
    crash_after: int | None
    resumed: bool
    started: float
    base_calls: int
    base_cost: float
    planner_calls0: int
    planner_cost0: float
    status: RunStatus = RunStatus.CREATED
    order: list[Entity] = field(default_factory=list)
    mappings: dict[Entity, MappingSpec] = field(default_factory=dict)
    counts_reported: dict[str, int] = field(default_factory=dict)
    target_version: str | None = None
    version_dirty: bool = False
    validated_for: dict[Entity, str | None] = field(default_factory=dict)
    token_refreshed: bool = False
    executing: bool = False
    replans: int = 0
    dry_run_rounds: int = 0
    batches_returned: int = 0
    backoff_seconds: float = 0.0
    metrics: Counter[str] = field(default_factory=Counter)


class MigrationEngine:
    """Runs one migration at a time; `run` starts a new run, `resume` continues one from the ledger."""

    def __init__(
        self,
        settings: Settings,
        source: Any,
        target: Any,
        planner: Any,
        verifier: Any,
        ledger: Ledger,
        on_event: Callable[[RunEvent], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng_seed: int = 0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.source = source
        self.target = target
        self.planner = planner
        self.verifier = verifier
        self.ledger = ledger
        self._on_event = on_event
        self._sleep = sleep
        self._clock = clock
        self._rng = random.Random(rng_seed)
        self._st: _RunState | None = None
        self.tools = _planner_tools(planner) or PlannerTools(source, target)
        self.tools.attach(call=self._call_with_retries, id_map=self._known_id)
        binder = getattr(planner, "bind_tools", None)
        if callable(binder):
            binder(self.tools)

    # -- public API ---------------------------------------------------------------

    def run(
        self,
        goal: str,
        scenario: str = "",
        contract: PreservationContract | None = None,
        crash_after_batches: int | None = None,
    ) -> RunResult:
        contract = contract or PreservationContract()
        run_id = self.ledger.create_run(goal, scenario, contract)
        self._start(run_id, goal, contract, crash_after_batches, resumed=False, base=(0, 0.0))
        self._emit("state", f"run created: {goal}", scenario=scenario)
        return self._workflow(None)

    def resume(self, run_id: str, crash_after_batches: int | None = None) -> RunResult:
        record = self.ledger.get_run(run_id)
        if record is None:
            raise KeyError(f"unknown run {run_id!r}")
        if record.status in (RunStatus.SUCCESS, RunStatus.PARTIAL_SUCCESS):
            return self._stored_result(record)
        self._start(
            run_id,
            record.goal,
            record.contract(),
            crash_after_batches,
            resumed=True,
            base=(record.llm_calls, record.cost_usd),
        )
        self._emit("info", f"resuming run from {record.status.value}", previous_status=record.status.value)
        plan = MigrationPlan.model_validate_json(record.plan_json) if record.plan_json else None
        return self._workflow(plan)

    # -- workflow -----------------------------------------------------------------

    def _start(
        self,
        run_id: str,
        goal: str,
        contract: PreservationContract,
        crash_after: int | None,
        resumed: bool,
        base: tuple[int, float],
    ) -> None:
        calls0, cost0 = _usage_of(self.planner)
        status = RunStatus.CREATED
        if resumed:
            stored = self.ledger.get_run(run_id)
            status = stored.status if stored else status
        self._st = _RunState(
            run_id=run_id,
            goal=goal,
            contract=contract,
            crash_after=None if crash_after is None else max(1, int(crash_after)),
            resumed=resumed,
            started=self._clock(),
            base_calls=int(base[0]),
            base_cost=float(base[1]),
            planner_calls0=calls0,
            planner_cost0=cost0,
            status=status,
        )
        self.tools.reset()

    @property
    def _state(self) -> _RunState:
        if self._st is None:
            raise RuntimeError("no active run")
        return self._st

    @telemetry.span(kind="WORKFLOW", name="zerodrop.migration")
    def _workflow(self, plan: MigrationPlan | None) -> RunResult:
        try:
            self._discover()
            if plan is None:
                self._plan()
                self._dry_run_phase()
            else:
                self._restore_plan(plan)
            self._execute()
        except SimulatedCrash:
            raise
        except _AwaitApproval as exc:
            return self._finish_waiting(str(exc))
        except _Halt as exc:
            return self._finish_halted(exc.failure, exc.message)
        except Exception as exc:  # planner budget guard or a bug: stop safely, report honestly
            failure = classify_exception(exc, write=False)
            failure = failure if failure == FailureClass.BUDGET else FailureClass.UNKNOWN
            return self._finish_halted(failure, f"{type(exc).__name__}: {exc}")
        return self._finish_verified(self._belief())

    def _discover(self) -> None:
        st = self._state
        self._set_status(RunStatus.DISCOVERING)
        entities = [e for e in ENTITY_ORDER if e in st.contract.entities]
        with telemetry.trace("discovery", kind="TOOL", run_id=st.run_id, entities=len(entities)) as span:
            account = self.tools.account()
            self.tools.field_docs()
            st.counts_reported = {
                e.value: self._call_with_retries(self.source.count, e.value, system="source", label="count")
                for e in entities
            }
            loaded = {e.value: len(self.tools.records(e.value)) for e in entities}
            meta = self._call_with_retries(self.target.meta, system="target", label="target meta")
            schema = self.tools.refresh_target()
            st.target_version = schema.get("version") or meta.get("api_version")
            st.version_dirty = False
            telemetry.set_attr(span, "outcome", "ok")
            telemetry.set_attr(span, "target_api_version", str(st.target_version))
        self._emit(
            "info",
            f"discovered {sum(loaded.values())} source records; target API {st.target_version}",
            counts_reported=st.counts_reported,
            records_loaded=loaded,
            target_api_version=st.target_version,
            timezone=account.get("timezone"),
        )

    def _plan(self) -> None:
        st = self._state
        self._set_status(RunStatus.PLANNING)
        ctx = self._discovery_context()
        self._check_budget(llm=True)
        try:
            with telemetry.trace("planner.plan", kind="AGENT", run_id=st.run_id):
                raw = self.planner.plan(ctx)
        finally:  # persist usage even when the planner fails, so budgets hold across resumes
            self._record_llm_usage("plan")
        plan = raw if isinstance(raw, MigrationPlan) else MigrationPlan.model_validate(raw)
        self._adopt_plan(plan, save=True)
        self.ledger.set_plan(st.run_id, plan.model_dump_json())
        self._emit(
            "plan",
            "plan: " + " -> ".join(e.value for e in st.order),
            entity_order=[e.value for e in st.order],
            mappings={e.value: _spec_summary(st.mappings[e]) for e in st.order},
            notes=plan.notes,
        )

    def _adopt_plan(self, plan: MigrationPlan, save: bool) -> None:
        st = self._state
        wanted = [e for e in ENTITY_ORDER if e in st.contract.entities]
        for entity in wanted:
            stored = None if save else self.ledger.latest_mapping(st.run_id, entity.value)
            if stored is None:
                try:
                    spec = plan.mapping_for(entity)
                except KeyError:
                    raise _Halt(FailureClass.UNKNOWN, f"the plan has no mapping for {entity.value}") from None
                stored = self.ledger.save_mapping(st.run_id, spec)
            st.mappings[entity] = stored
        listed = list(dict.fromkeys(e for e in plan.entity_order if e in wanted))
        order = listed + [e for e in wanted if e not in listed]
        st.order = _dependency_order(order, {e: _referenced_entities(st.mappings[e]) for e in order})
        if st.order != listed:
            self._emit(
                "decision",
                "entity order adjusted to respect references: " + " -> ".join(e.value for e in st.order),
                planned=[e.value for e in plan.entity_order],
            )

    def _restore_plan(self, plan: MigrationPlan) -> None:
        st = self._state
        self._adopt_plan(plan, save=False)
        self._emit(
            "plan",
            "restored plan with mapping versions "
            + ", ".join(f"{e.value} v{st.mappings[e].version}" for e in st.order),
            mappings={e.value: _spec_summary(st.mappings[e]) for e in st.order},
        )
        self._set_status(RunStatus.DRY_RUN)
        remaining = self._remaining(None)
        self._repair_until_valid(remaining, {}, self.tools.schema(), phase="dry_run")
        for entity in remaining:
            st.validated_for[entity] = st.target_version

    def _dry_run_phase(self) -> None:
        st = self._state
        self._set_status(RunStatus.DRY_RUN)
        self._repair_until_valid(list(st.order), {}, self.tools.schema(), phase="dry_run")
        for entity in st.order:
            st.validated_for[entity] = st.target_version

    def _discovery_context(self) -> DiscoveryContext:
        st = self._state
        docs = self.tools.field_docs()
        return DiscoveryContext(
            goal=st.goal,
            source_account=self.tools.account(),
            source_entities=[
                SourceEntityInfo(
                    entity=entity,
                    count_reported=count,
                    fields=dict(docs.get(entity) or {}),
                    samples=self.tools.get_source_samples(entity, DISCOVERY_SAMPLES),
                )
                for entity, count in st.counts_reported.items()
            ],
            target_schema=self.tools.get_target_schema(),
            target_reference_tables={k: v[:50] for k, v in self.tools.reference_tables().items()},
        )

    # -- mapping repair -------------------------------------------------------------

    def _repair_until_valid(
        self,
        entities: list[Entity],
        forced: dict[Entity, list[FailedItemSample]],
        previous_schema: dict[str, Any],
        phase: str,
    ) -> None:
        """Dry-run every mapping in `entities`; ask the planner to repair failing ones (bounded rounds).

        `forced` entities are repaired even if their dry run passes: the target already
        rejected them, and its evidence (failed samples) goes first.
        """
        st = self._state
        forced = dict(forced)
        limit = self.settings.max_replans
        while True:
            failing: dict[Entity, list[FailedItemSample]] = {}
            hard: set[Entity] = set(forced)
            for entity in entities:
                report = self.tools.check_mapping(st.mappings[entity])
                self._emit(
                    "decision",
                    f"dry run {entity.value} v{report.mapping_version} on {report.api_version}: "
                    f"{report.checked - len(report.failures)}/{report.checked} samples valid",
                    entity=entity,
                    **{k: v for k, v in report.as_dict(limit=5).items() if k != "entity"},
                )
                if report.mapping_problem:
                    failing[entity] = report.failed_samples()
                if report.hard_problem:
                    hard.add(entity)
            for entity, samples in forced.items():
                failing[entity] = samples + failing.get(entity, [])
            if not failing:
                return
            used = st.dry_run_rounds if phase == "dry_run" else st.replans
            names = ", ".join(e.value for e in entities if e in failing)
            if used >= limit and not hard:
                self._emit(
                    "decision",
                    f"{names}: repeated record-level failures remain after {limit} repair rounds; "
                    "proceeding, those records will be quarantined",
                )
                return
            if used >= limit:
                raise _Halt(
                    FailureClass.CONTRACT,
                    f"mapping for {names} still invalid after {limit} repair rounds",
                )
            entity = next(e for e in entities if e in failing)
            others = [e for e in entities if e != entity]
            specs = self._call_repair(entity, failing[entity], previous_schema, others)
            if phase == "dry_run":
                st.dry_run_rounds += 1
            else:
                st.replans += 1
            self._accept_specs(specs, entities)
            forced.pop(entity, None)

    def _call_repair(
        self,
        entity: Entity,
        samples: list[FailedItemSample],
        previous_schema: dict[str, Any],
        others: list[Entity],
    ) -> list[MappingSpec]:
        st = self._state
        self._check_budget(llm=True)
        ctx = RepairContext(
            entity=entity,
            current_mapping=st.mappings[entity],
            failed_samples=samples[:MAX_FAILED_SAMPLES],
            previous_schema=previous_schema,
            current_schema=self.tools.get_target_schema(),
            target_reference_tables={k: v[:50] for k, v in self.tools.reference_tables().items()},
            source_samples=self.tools.get_source_samples(entity.value, DISCOVERY_SAMPLES),
            other_pending_mappings=[st.mappings[e] for e in others],
        )
        self._emit(
            "decision",
            f"asking the planner to repair the {entity.value} mapping "
            f"({len(samples)} failing samples, {len(others)} other pending mappings)",
            entity=entity,
            codes=sorted({s.error.code for s in samples if s.error}),
        )
        try:
            with telemetry.trace("planner.repair", kind="AGENT", entity=entity.value, failed=len(samples)):
                raw = self.planner.repair(ctx)
        finally:
            self._record_llm_usage("repair")
        return [s if isinstance(s, MappingSpec) else MappingSpec.model_validate(s) for s in (raw or [])]

    def _accept_specs(self, specs: Iterable[MappingSpec], allowed: list[Entity]) -> None:
        st = self._state
        for spec in specs:
            if spec.entity not in allowed:
                self._emit("decision", f"ignored a proposed mapping for {spec.entity.value} (not pending)")
                continue
            current = st.mappings[spec.entity]
            if spec.model_copy(update={"version": current.version}) == current:
                self._emit("decision", f"planner returned an unchanged {spec.entity.value} mapping")
                continue
            stored = self.ledger.save_mapping(
                st.run_id, spec.model_copy(update={"version": current.version + 1})
            )
            st.mappings[spec.entity] = stored
            self._emit(
                "plan",
                f"mapping {spec.entity.value} v{current.version} -> v{stored.version} "
                f"(for {stored.target_api_version})",
                entity=spec.entity,
                changes=_mapping_changes(current, stored),
                rationale=stored.rationale,
                version_from=current.version,
                version_to=stored.version,
            )

    # -- execution ------------------------------------------------------------------

    def _execute(self) -> None:
        st = self._state
        st.executing = True
        self._set_status(RunStatus.EXECUTING)
        for entity in st.order:
            if self._entity_complete(entity):
                continue
            self._sync_version(entity)
            self._migrate_entity(entity)
            self.ledger.set_entity_done(st.run_id, entity.value)
            counts = self.ledger.counts(st.run_id).get(entity.value, {})
            self._emit(
                "decision",
                f"{entity.value} complete: {counts.get('written', 0)} written, "
                f"{counts.get('quarantined', 0)} quarantined",
                entity=entity,
                **counts,
            )

    def _entity_complete(self, entity: Entity) -> bool:
        st = self._state
        counts = self.ledger.counts(st.run_id).get(entity.value, {})
        unresolved = counts.get("pending", 0) + counts.get("failed", 0)
        return self.ledger.entity_done(st.run_id, entity.value) and unresolved == 0

    def _remaining(self, current: Entity | None) -> list[Entity]:
        st = self._state
        start = st.order.index(current) if current in st.order else 0
        return [
            e for i, e in enumerate(st.order) if i >= start and (e == current or not self._entity_complete(e))
        ]

    def _sync_version(self, entity: Entity) -> None:
        """Before an entity starts: re-check the target version and re-validate stale mappings."""
        st = self._state
        meta = self._call_with_retries(self.target.meta, system="target", label="target meta", entity=entity)
        self._observe_version(meta.get("api_version") if isinstance(meta, Mapping) else None)
        stale = [
            e
            for e in self._remaining(entity)
            if st.mappings[e].target_api_version != st.target_version
            and st.validated_for.get(e) != st.target_version
        ]
        if st.version_dirty or stale:
            self._recover(entity, "version_change" if st.version_dirty else "stale_mapping")

    def _migrate_entity(self, entity: Entity) -> None:
        st = self._state
        states = self.ledger.record_states(st.run_id, entity.value)
        seen: set[str] = set()
        chunk: list[tuple[str, dict[str, Any]]] = []
        size = _clamp(self.settings.batch_size, 1, MAX_BATCH_ITEMS)
        for index, record in enumerate(self.tools.records(entity.value)):
            spec = st.mappings[entity]
            if matches_exclusion(spec, record):
                continue
            source_id = source_id_of(spec, record) or f"row-{index}"
            if source_id in seen:
                continue
            seen.add(source_id)
            if states.get(source_id) in (RecordState.WRITTEN, RecordState.QUARANTINED):
                st.metrics["skipped_already_resolved"] += 1
                continue
            chunk.append((source_id, record))
            if len(chunk) >= size:
                self._process_chunk(entity, chunk)
                chunk = []
        if chunk:
            self._process_chunk(entity, chunk)

    def _process_chunk(self, entity: Entity, chunk: list[tuple[str, dict[str, Any]]]) -> None:
        st = self._state
        if st.version_dirty:
            self._recover(entity, "version_change")
        self.ledger.ensure_records(
            st.run_id, entity.value, [sid for sid, _ in chunk], st.mappings[entity].version
        )
        items = self._map_chunk(entity, chunk)
        if items:
            self._write(entity, items)

    def _map_chunk(self, entity: Entity, chunk: list[tuple[str, dict[str, Any]]]) -> list[_Item]:
        """Map records to payloads. Isolated mapping failures are quarantined (DATA);
        failures across most of the chunk mean the mapping is wrong (CONTRACT: repair, re-map)."""
        st = self._state
        while True:
            spec = st.mappings[entity]
            ctx = _MappingContext(self._known_id, self.tools.reference_table, placeholder_refs=False)
            items: list[_Item] = []
            failures: list[tuple[str, list[str]]] = []
            for source_id, record in chunk:
                payload, errors = apply_mapping(spec, record, ctx)
                if payload is None:
                    failures.append((source_id, errors))
                    continue
                external = payload.get("external_id")
                items.append(
                    _Item(
                        source_id=source_id,
                        record=record,
                        payload=payload,
                        external_id=source_id if external is None else str(external),
                        key=f"{entity.value}:{source_id}",
                        mapping_version=spec.version,
                    )
                )
            if not failures:
                return items
            records = dict(chunk)
            proven = bool(items) or self.ledger.counts(st.run_id).get(entity.value, {}).get("written", 0) > 0
            cascades = {
                sid: self._cascade_reason(spec, records[sid], errors, proven) for sid, errors in failures
            }
            codes = [None] * len(items) + [
                None if cascades[sid] else _primary_code(errors) for sid, errors in failures
            ]
            suspect, dominant = contract_signal(codes, structural=STRUCTURAL_MAPPING_CODES)
            reasons = [(sid, cascades[sid] or _dsl_reason(errors)) for sid, errors in failures]
            if not suspect:
                self._quarantine(entity, reasons, "mapping")
                return items
            failures = [(sid, errors) for sid, errors in failures if not cascades[sid]]
            samples = [
                FailedItemSample(
                    source_id=sid,
                    payload={},
                    status=0,
                    error=TargetItemError(
                        code=_primary_code(errors) or "invalid_value",
                        field=error_field(errors[0]) if errors else None,
                        message="; ".join(errors)[:500],
                    ),
                )
                for sid, errors in failures[:MAX_FAILED_SAMPLES]
            ]
            self._emit(
                "failure",
                f"mapping {entity.value} v{spec.version} failed on {len(failures)}/{len(chunk)} records "
                f"({dominant}): the mapping itself looks wrong",
                entity=entity,
                failure_class=FailureClass.CONTRACT.value,
                dominant_code=dominant,
            )
            self._recover(entity, "mapping_errors", samples)
            if st.mappings[entity].version == spec.version:
                # The planner kept the mapping and it passes the dry run: the failures are
                # record-level (e.g. a small final chunk), so quarantine instead of looping.
                self._quarantine(entity, reasons, "mapping kept after repair")
                return items

    def _cascade_reason(
        self, spec: MappingSpec, record: dict[str, Any], errors: list[str], proven: bool = False
    ) -> str | None:
        """A quarantine reason when a reference fails because of the parent record, not the mapping.

        Cascades (the parent was quarantined or excluded) never count as evidence that the
        mapping is wrong. Orphans (the parent is missing from the source) count as record-level
        only once the mapping is `proven` (it resolved references for other records of this
        entity); otherwise a wrong reference field would look like a run of orphans.
        """
        if _primary_code(errors) != "unresolved_reference":
            return None
        target_field = error_field(errors[0])
        fm = next((f for f in spec.fields if f.target == target_field and f.source), None)
        ref = next((op for op in fm.ops if op.op == "ref" and op.entity), None) if fm else None
        raw = record.get(fm.source) if fm and fm.source else None
        if ref is None or ref.entity is None or not isinstance(raw, str | int) or str(raw).strip() == "":
            return None
        parent, parent_id = ref.entity, str(raw).strip()
        state = self.ledger.record_states(self._state.run_id, parent.value).get(parent_id)
        parent_spec = self._state.mappings.get(parent)
        parents = (
            [r for r in self.tools.records(parent.value) if source_id_of(parent_spec, r) == parent_id]
            if parent_spec is not None
            else []
        )
        if state == RecordState.QUARANTINED:
            fate = "was quarantined"
        elif parent_spec is not None and any(matches_exclusion(parent_spec, r) for r in parents):
            fate = "is excluded from the migration"
        elif parent_spec is not None and proven and not parents:
            fate = "does not exist in the source"
        else:
            return None
        return f"invalid_reference: {target_field}: parent {parent.value} {parent_id} {fate}"

    def _write(self, entity: Entity, items: list[_Item]) -> None:
        """Send items in one batch until each is written, quarantined or the run halts."""
        st = self._state
        pending = list(items)
        attempt = 0
        while pending:
            if st.version_dirty:  # attempts are not reset here: a flapping version must not loop forever
                self._recover(entity, "version_change")
                pending = self._map_chunk(entity, [(it.source_id, it.record) for it in pending])
                if not pending:
                    return
            attempt += 1
            if attempt > self.settings.max_attempts_per_request:
                self._fail_items(entity, pending, f"still failing after {attempt - 1} attempts")
                raise _Halt(
                    FailureClass.TRANSIENT,
                    f"{entity.value}: {len(pending)} records still failing after "
                    f"{self.settings.max_attempts_per_request} attempts",
                )
            self._check_budget()
            self.ledger.mark_attempts(st.run_id, entity.value, [it.source_id for it in pending])
            result, error = self._post_batch(entity, pending, attempt)
            if error is not None:
                pending = self._handle_request_failure(entity, pending, attempt, error)
                continue
            pending, changed = self._apply_results(entity, pending, result, attempt)
            if changed:
                attempt = 0

    def _post_batch(self, entity: Entity, pending: list[_Item], attempt: int) -> tuple[Any, Exception | None]:
        st = self._state
        body = [{"idempotency_key": it.key, "payload": it.payload} for it in pending]
        with telemetry.trace(
            "novabill.batch_write", kind="TOOL", entity=entity.value, batch_size=len(pending), attempt=attempt
        ) as span:
            try:
                result = self.target.batch(entity.value, body)
            except Exception as exc:
                telemetry.set_attr(span, "outcome", f"error:{type(exc).__name__}")
                st.metrics["batch_requests"] += 1
                return None, exc
            statuses = Counter(int(r.status) for r in result.results)
            telemetry.set_attr(span, "outcome", ",".join(f"{k}x{v}" for k, v in sorted(statuses.items())))
        st.metrics["batch_requests"] += 1
        st.batches_returned += 1
        if st.crash_after is not None and st.batches_returned >= st.crash_after:
            raise SimulatedCrash(f"simulated crash after {st.batches_returned} write batches")
        return result, None

    def _handle_request_failure(
        self, entity: Entity, pending: list[_Item], attempt: int, exc: Exception
    ) -> list[_Item]:
        failure = classify_exception(exc, write=True)
        status = getattr(exc, "status", None)
        self._emit(
            "failure",
            f"{entity.value} batch of {len(pending)} failed ({failure.value}): {exc}",
            entity=entity,
            failure_class=failure.value,
            status=status,
            attempt=attempt,
        )
        if failure == FailureClass.TRANSIENT:
            self._backoff(entity, attempt, getattr(exc, "retry_after", None), str(exc))
            return pending
        if failure == FailureClass.AMBIGUOUS_WRITE:
            remaining = self._resolve_ambiguous(entity, pending)
            if remaining:
                self._backoff(entity, attempt, None, "re-sending items not found after an ambiguous write")
            return remaining
        if failure == FailureClass.AUTH:
            self._handle_auth(entity)
            return pending
        raise _Halt(failure, f"{entity.value}: batch write failed: {exc}")

    def _apply_results(
        self, entity: Entity, pending: list[_Item], result: Any, attempt: int
    ) -> tuple[list[_Item], bool]:
        """Checkpoint one batch response; returns (items to send again, whether a repair was forced)."""
        st = self._state
        self._observe_version(getattr(result, "version", None) or getattr(self.target, "last_version", None))
        out = _sort_results(pending, result.results, version_changed=st.version_dirty)
        self.ledger.mark_written_many(st.run_id, entity.value, out.written, pending[0].mapping_version)
        if out.data:
            self._quarantine(entity, out.data, "target")
        for item, reason in out.failed:
            self.ledger.mark_failed(st.run_id, entity.value, item.source_id, reason)
        st.metrics["records_written"] += len(out.written)
        st.metrics["idempotent_replays"] += out.replays
        st.metrics["already_present"] += out.present
        self._emit(
            "batch",
            f"{entity.value} batch (attempt {attempt}): {len(out.written)}/{len(pending)} written",
            entity=entity,
            attempt=attempt,
            size=len(pending),
            written=len(out.written),
            replayed=out.replays,
            already_present=out.present,
            quarantined=len(out.data),
            contract_rejected=len(out.contract),
            held_for_revalidation=len(out.held),
            retry=len(out.retry),
            failed=len(out.failed),
            api_version=getattr(result, "version", None),
        )
        retry = out.retry
        if out.unresolved:
            retry = retry + self._resolve_ambiguous(entity, out.unresolved)
        if out.auth:
            self._handle_auth(entity)
        if not out.contract and not out.held:
            if retry and not st.version_dirty:
                self._backoff(entity, attempt, None, f"{len(retry)} items temporarily unavailable")
            return retry, False
        if out.contract:
            self._emit(
                "failure",
                f"{len(out.contract)} of {len(pending)} {entity.value} items rejected with "
                f"{out.dominant_code}: target contract change suspected",
                entity=entity,
                failure_class=FailureClass.CONTRACT.value,
                dominant_code=out.dominant_code,
            )
            samples = [
                FailedItemSample(
                    source_id=item.source_id,
                    payload=item.payload,
                    status=int(res.status),
                    error=_item_error(res),
                )
                for item, res in out.contract[:MAX_FAILED_SAMPLES]
            ]
            self._recover(entity, "contract", samples)
            current = st.mappings[entity].version
            kept = [(item, res) for item, res in out.contract if item.mapping_version == current]
            if kept:
                # Same mapping, valid against the refreshed schema: re-sending would only be
                # rejected again, so these rejections are record-level after all.
                reasons = [(item.source_id, _target_reason(res)) for item, res in kept]
                self._quarantine(entity, reasons, "target, mapping kept after repair")
                out.contract = [(item, res) for item, res in out.contract if item.mapping_version != current]
        else:
            self._emit(
                "decision",
                f"{len(out.held)} {entity.value} item(s) rejected in the response that changed the target "
                "version: re-validating mappings before deciding",
                entity=entity,
            )
            self._recover(entity, "version_change")
        resend = {id(it) for it in retry} | {id(it) for it, _ in out.contract + out.held}
        again = [(it.source_id, it.record) for it in pending if id(it) in resend]  # keep source order
        return self._map_chunk(entity, again), bool(out.contract)

    # -- recovery -------------------------------------------------------------------

    def _recover(
        self, entity: Entity | None, trigger: str, failed: list[FailedItemSample] | None = None
    ) -> None:
        """CONTRACT recovery: pause writers, refetch the schema, repair and dry-run every pending mapping."""
        st = self._state
        with telemetry.trace(
            f"recovery.{FailureClass.CONTRACT.value}",
            kind="CHAIN",
            entity=entity.value if entity else "",
            trigger=trigger,
            failed_items=len(failed or []),
        ) as span:
            self._set_status(RunStatus.RECOVERING)
            previous = self.tools.schema()
            current = self.tools.refresh_target()
            old_version, new_version = st.target_version, current.get("version") or st.target_version
            st.target_version, st.version_dirty = new_version, False
            if old_version != new_version:
                st.metrics["version_changes"] += 1
            changes = {
                name: {k: d[k] for k in ("added_fields", "removed_fields", "changed_fields")}
                for name, d in schema_diff(previous, current).items()
                if d["added_fields"] or d["removed_fields"] or d["changed_fields"]
            }
            self._emit(
                "recovery",
                f"paused writes; refetched target schema ({old_version} -> {new_version})",
                entity=entity,
                trigger=trigger,
                schema_changes=changes,
            )
            remaining = self._remaining(entity)
            forced = {entity: failed} if (failed and entity is not None) else {}
            self._repair_until_valid(remaining, forced, previous, phase="recovery")
            for e in remaining:
                st.validated_for[e] = st.target_version
            telemetry.set_attr(span, "outcome", "resumed")
            telemetry.set_attr(span, "replans", st.replans)
        self._emit(
            "recovery",
            f"mappings valid for {st.target_version}; resuming writes",
            entity=entity,
            mapping_versions={e.value: st.mappings[e].version for e in remaining},
        )
        self._set_status(RunStatus.EXECUTING)

    def _resolve_ambiguous(self, entity: Entity, pending: list[_Item]) -> list[_Item]:
        """AMBIGUOUS_WRITE: look each item up by external id; only the missing ones are re-sent."""
        st = self._state
        with telemetry.trace(
            f"recovery.{FailureClass.AMBIGUOUS_WRITE.value}",
            kind="CHAIN",
            entity=entity.value,
            batch_size=len(pending),
        ) as span:
            found: list[tuple[str, str]] = []
            remaining: list[_Item] = []
            for item in pending:
                record = self._call_with_retries(
                    self.target.lookup,
                    entity.value,
                    item.external_id,
                    system="target",
                    label=f"lookup {entity.value}",
                    entity=entity,
                    trace_name="novabill.lookup",
                )
                if isinstance(record, Mapping) and record.get("id"):
                    found.append((item.source_id, str(record["id"])))
                else:
                    remaining.append(item)
            self.ledger.mark_written_many(st.run_id, entity.value, found, pending[0].mapping_version)
            telemetry.set_attr(span, "found", len(found))
            telemetry.set_attr(span, "resend", len(remaining))
        st.metrics["ambiguous_writes"] += 1
        st.metrics["lookups"] += len(pending)
        st.metrics["recovered_by_lookup"] += len(found)
        st.metrics["records_written"] += len(found)
        self._emit(
            "recovery",
            f"ambiguous write on {entity.value}: {len(found)} of {len(pending)} items were committed; "
            f"re-sending {len(remaining)}",
            entity=entity,
            found=len(found),
            resend=len(remaining),
        )
        return remaining

    def _quarantine(self, entity: Entity, items: list[tuple[str, str]], origin: str) -> None:
        st = self._state
        with telemetry.trace(
            f"recovery.{FailureClass.DATA.value}", kind="CHAIN", entity=entity.value, records=len(items)
        ):
            for source_id, reason in items:
                self.ledger.mark_quarantined(st.run_id, entity.value, source_id, reason)
        st.metrics["quarantined"] += len(items)
        self._emit(
            "decision",
            f"quarantined {len(items)} {entity.value} record(s) ({origin}); continuing",
            entity=entity,
            failure_class=FailureClass.DATA.value,
            items=[{"source_id": sid, "reason": reason} for sid, reason in items[:20]],
        )

    def _fail_items(self, entity: Entity, items: list[_Item], reason: str) -> None:
        st = self._state
        for item in items:
            self.ledger.mark_failed(st.run_id, entity.value, item.source_id, reason)

    def _handle_auth(self, entity: Entity | None) -> None:
        with telemetry.trace(
            f"recovery.{FailureClass.AUTH.value}", kind="CHAIN", entity=entity.value if entity else ""
        ) as span:
            refreshed = self._refresh_token()
            telemetry.set_attr(span, "outcome", "token_reloaded" if refreshed else "waiting_for_approval")
        if not refreshed:
            raise _AwaitApproval(
                "the target rejected the credentials and no new token could be loaded from the token file"
            )
        self._state.metrics["token_refreshes"] += 1
        self._emit(
            "recovery", "credentials rejected; re-read the token file once and retrying", entity=entity
        )

    def _refresh_token(self) -> bool:
        st = self._state
        if st.token_refreshed:
            return False
        st.token_refreshed = True
        path = self.settings.target_token_file
        if not path:
            return False
        try:
            token = Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            return False
        return bool(token) and _install_token(self.target, token)

    def _backoff(self, entity: Entity | None, attempt: int, retry_after: float | None, reason: str) -> None:
        st = self._state
        delay = self._backoff_delay(attempt, retry_after)
        remaining = self.settings.max_wall_seconds - (self._clock() - st.started)
        if delay > remaining:
            self._budget_stop(
                f"wall-clock budget exhausted: waiting {delay:.1f}s ({reason}) "
                f"exceeds the {max(0.0, remaining):.1f}s left"
            )
        with telemetry.trace(
            f"recovery.{FailureClass.TRANSIENT.value}",
            kind="CHAIN",
            entity=entity.value if entity else "",
            attempt=attempt,
            delay_s=round(delay, 3),
        ):
            self._emit(
                "recovery",
                f"transient failure ({reason}); retrying in {delay:.2f}s (attempt {attempt})",
                entity=entity,
                failure_class=FailureClass.TRANSIENT.value,
                delay_s=round(delay, 3),
                retry_after=retry_after,
                attempt=attempt,
            )
            self._sleep(delay)
        st.metrics["retries"] += 1
        st.backoff_seconds += delay

    def _backoff_delay(self, attempt: int, retry_after: float | None) -> float:
        """Capped exponential backoff with seeded jitter, never shorter than Retry-After.

        Retry-After is honored in full (up to RETRY_AFTER_MAX_S); the cap only bounds our own backoff.
        """
        base = BACKOFF_BASE_S * 2 ** max(0, attempt - 1)
        jittered = min(BACKOFF_CAP_S, base * (0.5 + 0.5 * self._rng.random()))
        return max(jittered, min(max(retry_after or 0.0, 0.0), RETRY_AFTER_MAX_S))

    def _call_with_retries(
        self,
        fn: Callable[..., Any],
        *args: Any,
        system: str = "target",
        label: str = "",
        entity: Entity | None = None,
        trace_name: str | None = None,
    ) -> Any:
        """Reads (source and target): TRANSIENT -> backoff; AUTH -> refresh the token once, else wait."""
        if self._st is None:
            return fn(*args)
        attempt = 0
        while True:
            attempt += 1
            try:
                if trace_name:
                    with telemetry.trace(
                        trace_name, kind="TOOL", entity=entity.value if entity else "", attempt=attempt
                    ) as span:
                        result = fn(*args)
                        telemetry.set_attr(span, "outcome", "found" if result else "empty")
                else:
                    result = fn(*args)
            except (SimulatedCrash, _Halt, _AwaitApproval):
                raise
            except Exception as exc:
                failure = classify_exception(exc, write=False)
                if failure == FailureClass.TRANSIENT and attempt < self.settings.max_attempts_per_request:
                    self._backoff(entity, attempt, getattr(exc, "retry_after", None), f"{label}: {exc}")
                    continue
                if failure == FailureClass.TRANSIENT:
                    raise _Halt(failure, f"{label}: still failing after {attempt} attempts: {exc}") from exc
                if failure == FailureClass.AUTH and system == "target":
                    self._handle_auth(entity)
                    continue
                if failure == FailureClass.AUTH:
                    raise _AwaitApproval(f"{label}: the source rejected the credentials") from exc
                raise
            if system == "target":
                self._observe_version(getattr(self.target, "last_version", None))
            return result

    def _observe_version(self, version: Any) -> None:
        st = self._st
        if st is None or not isinstance(version, str) or not version:
            return
        if st.target_version is None:
            st.target_version = version
            return
        if version != st.target_version and not st.version_dirty:
            st.version_dirty = True
            self._emit(
                "failure",
                f"target API version changed: {st.target_version} -> {version}; "
                "re-validating every pending mapping",
                failure_class=FailureClass.CONTRACT.value,
                version_from=st.target_version,
                version_to=version,
            )

    # -- budget ---------------------------------------------------------------------

    def _check_budget(self, llm: bool = False) -> None:
        st = self._state
        elapsed = self._clock() - st.started
        if elapsed > self.settings.max_wall_seconds:
            self._budget_stop(
                f"wall-clock budget exhausted ({elapsed:.1f}s > {self.settings.max_wall_seconds}s)"
            )
        if not llm:
            return
        calls, cost = self._llm_usage()
        if calls >= self.settings.max_llm_calls:
            self._budget_stop(f"LLM call budget exhausted ({calls}/{self.settings.max_llm_calls} calls)")
        if cost >= self.settings.max_cost_usd:
            self._budget_stop(f"LLM cost budget exhausted (${cost:.4f} >= ${self.settings.max_cost_usd:.2f})")

    def _budget_stop(self, message: str) -> None:
        with telemetry.trace(f"recovery.{FailureClass.BUDGET.value}", kind="CHAIN", reason=message):
            self._emit("decision", f"{message}; stopping safely", failure_class=FailureClass.BUDGET.value)
        raise _Halt(FailureClass.BUDGET, message)

    def _llm_usage(self) -> tuple[int, float]:
        st = self._state
        calls, cost = _usage_of(self.planner)
        return (
            st.base_calls + max(0, calls - st.planner_calls0),
            st.base_cost + max(0.0, cost - st.planner_cost0),
        )

    def _record_llm_usage(self, label: str) -> None:
        st = self._state
        calls, cost = self._llm_usage()
        self.ledger.set_llm_usage(st.run_id, calls, cost)
        self._emit("llm", f"{label}: {calls} LLM calls so far (${cost:.4f})", calls=calls, cost_usd=cost)

    # -- finishing --------------------------------------------------------------------

    def _belief(self) -> RunStatus:
        """The engine's own claim before verification."""
        st = self._state
        counts = self.ledger.counts(st.run_id)
        relevant = [counts.get(e.value, {}) for e in st.order]
        if any(c.get("pending", 0) or c.get("failed", 0) for c in relevant):
            return RunStatus.FAILED
        if any(c.get("quarantined", 0) for c in relevant):
            return RunStatus.PARTIAL_SUCCESS
        return RunStatus.SUCCESS

    def _finish_verified(self, claim: RunStatus, error: str | None = None) -> RunResult:
        st = self._state
        self.ledger.set_agent_claim(st.run_id, claim)
        self._emit("decision", f"engine believes the run is {claim.value}; handing over to the verifier")
        self._set_status(RunStatus.VERIFYING)
        try:
            report = self._verify(claim)
        except SimulatedCrash:
            raise
        except Exception as exc:
            message = f"verifier error: {type(exc).__name__}: {exc}"
            self._emit("verify", message, failure_class=FailureClass.UNKNOWN.value)
            return self._finish(RunStatus.FAILED, claim, None, error or message)
        status = report.status if report.status in _VERIFIER_STATUSES else RunStatus.FAILED
        return self._finish(status, claim, report, error)

    def _finish_halted(self, failure: FailureClass, message: str) -> RunResult:
        st = self._state
        self._emit("failure", f"run halted ({failure.value}): {message}", failure_class=failure.value)
        self.ledger.set_error(st.run_id, message)
        wrote = any(c.get("written", 0) for c in self.ledger.counts(st.run_id).values())
        if st.executing or wrote:
            return self._finish_verified(RunStatus.FAILED, error=message)
        return self._finish(RunStatus.FAILED, RunStatus.FAILED, None, message)

    def _finish_waiting(self, reason: str) -> RunResult:
        self._emit(
            "decision",
            f"waiting for approval: {reason}",
            failure_class=FailureClass.AUTH.value,
        )
        return self._finish(RunStatus.WAITING_FOR_APPROVAL, RunStatus.WAITING_FOR_APPROVAL, None, reason)

    def _finish(
        self, status: RunStatus, claim: RunStatus, report: ReconciliationReport | None, error: str | None
    ) -> RunResult:
        st = self._state
        self.ledger.set_agent_claim(st.run_id, claim)
        if report is not None:
            self.ledger.set_report(st.run_id, report)
        self.ledger.set_error(st.run_id, error)  # None clears an error left by an earlier invocation
        self._set_status(status)
        return RunResult(
            run_id=st.run_id,
            status=status,
            agent_claimed_status=claim,
            report=report,
            metrics=self._metrics(claim, status),
        )

    def _verify(self, claim: RunStatus) -> ReconciliationReport:
        st = self._state
        quarantined = self.ledger.quarantined_items(st.run_id)
        verify = getattr(self.verifier, "verify", self.verifier)
        with telemetry.trace(
            "independent-verifier", kind="EVALUATOR", run_id=st.run_id, quarantined=len(quarantined)
        ) as span:
            raw = verify(st.run_id, self.source, self.target, st.contract, quarantined)
            report = (
                raw if isinstance(raw, ReconciliationReport) else ReconciliationReport.model_validate(raw)
            )
            failed_checks = [c.name for c in report.checks if not c.passed]
            telemetry.set_attr(span, "status", report.status.value)
            telemetry.set_attr(span, "checks_failed", len(failed_checks))
            telemetry.set_attr(span, "agent_claimed_status", claim.value)
        self._emit(
            "verify",
            f"independent verifier: {report.status.value} "
            f"({len(report.checks) - len(failed_checks)}/{len(report.checks)} checks passed)",
            status=report.status.value,
            agent_claimed_status=claim.value,
            false_success_claim=claim == RunStatus.SUCCESS and report.status != RunStatus.SUCCESS,
            failed_checks=failed_checks,
            source_counts=report.source_counts,
            target_counts=report.target_counts,
            report_hash=report.report_hash,
        )
        return report

    def _metrics(self, claim: RunStatus, status: RunStatus) -> dict[str, Any]:
        st = self._state
        calls, cost = self._llm_usage()
        excluded = {
            e.value: sum(1 for r in self.tools.records(e.value) if matches_exclusion(st.mappings[e], r))
            for e in st.order
            if e in st.mappings and self.tools.loaded(e.value)
        }
        return {
            "counts": self.ledger.counts(st.run_id),
            "excluded": excluded,
            "quarantined": len(self.ledger.quarantined_items(st.run_id)),
            "batch_requests": st.metrics["batch_requests"],
            "records_written": st.metrics["records_written"],
            "retries": st.metrics["retries"],
            "backoff_seconds": round(st.backoff_seconds, 3),
            "ambiguous_writes": st.metrics["ambiguous_writes"],
            "lookups": st.metrics["lookups"],
            "recovered_by_lookup": st.metrics["recovered_by_lookup"],
            "idempotent_replays": st.metrics["idempotent_replays"],
            "already_present": st.metrics["already_present"],
            "skipped_already_resolved": st.metrics["skipped_already_resolved"],
            "replans": st.replans,
            "dry_run_repairs": st.dry_run_rounds,
            "version_changes": st.metrics["version_changes"],
            "token_refreshes": st.metrics["token_refreshes"],
            "mapping_versions": {e.value: m.version for e, m in st.mappings.items()},
            "target_api_version": st.target_version,
            "llm_calls": calls,
            "cost_usd": round(cost, 6),
            "wall_seconds": round(self._clock() - st.started, 3),
            "resumed": st.resumed,
            "false_success_claim": claim == RunStatus.SUCCESS and status != RunStatus.SUCCESS,
        }

    def _stored_result(self, record: RunRecord) -> RunResult:
        return RunResult(
            run_id=record.run_id,
            status=record.status,
            agent_claimed_status=record.agent_claimed_status,
            report=record.report(),
            metrics={"counts": self.ledger.counts(record.run_id), "resumed": True, "already_finished": True},
        )

    # -- events -----------------------------------------------------------------------

    def _set_status(self, status: RunStatus) -> None:
        st = self._state
        if st.status == status:
            return
        previous, st.status = st.status, status
        self.ledger.set_status(st.run_id, status)
        self._emit("state", f"{previous.value} -> {status.value}", previous=previous.value)

    def _emit(
        self, kind: EventKind, message: str, entity: Entity | None = None, **data: Any
    ) -> RunEvent | None:
        st = self._st
        if st is None:
            return None
        event = self.ledger.append_event(
            st.run_id,
            kind,
            message,
            state=st.status,
            entity=entity.value if entity is not None else None,
            data=json.loads(json.dumps(data, default=str)),
        )
        if self._on_event is not None:
            try:
                self._on_event(event)
            except Exception as exc:  # a broken UI callback must never stop a migration
                telemetry.log(f"on_event callback failed: {type(exc).__name__}", level="warning")
        return event

    def _known_id(self, entity: str, source_id: str) -> str | None:
        st = self._st
        return None if st is None else self.ledger.id_map(st.run_id, str(entity), source_id)


@dataclass
class _BatchOutcome:
    written: list[tuple[str, str]] = field(default_factory=list)
    replays: int = 0
    present: int = 0
    unresolved: list[_Item] = field(default_factory=list)  # stored, but the response carried no id
    retry: list[_Item] = field(default_factory=list)
    contract: list[tuple[_Item, Any]] = field(default_factory=list)
    held: list[tuple[_Item, Any]] = field(default_factory=list)  # 422 while the version changed
    data: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[_Item, str]] = field(default_factory=list)
    auth: bool = False
    dominant_code: str | None = None


def _sort_results(pending: list[_Item], results: Sequence[Any], version_changed: bool) -> _BatchOutcome:
    """Partition a batch response by what the engine must do with each item.

    A 422 in a response that announced a new target version is not trusted as a
    data problem: it is held, re-mapped after re-validation and sent again.
    """
    verdict = classify_batch(results)
    by_index = {int(r.index): r for r in results}
    out = _BatchOutcome(dominant_code=verdict.dominant_code)
    for index in verdict.written:
        if not 0 <= index < len(pending):
            continue
        res, item = by_index[index], pending[index]
        if res.id:
            out.written.append((item.source_id, str(res.id)))
            out.replays += res.status == 200
            out.present += res.status == 409
        else:
            out.unresolved.append(item)
    for index, failure in verdict.per_item:
        if not 0 <= index < len(pending):
            continue
        res, item = by_index[index], pending[index]
        code = getattr(_item_error(res), "code", None)
        if failure == FailureClass.CONTRACT:
            out.contract.append((item, res))
        elif failure == FailureClass.DATA and version_changed and code not in DATA_ONLY_CODES:
            out.held.append((item, res))
        elif failure == FailureClass.DATA:
            out.data.append((item.source_id, _target_reason(res)))
        elif failure in (FailureClass.TRANSIENT, FailureClass.AUTH):
            out.retry.append(item)
            out.auth = out.auth or failure == FailureClass.AUTH
        else:
            out.failed.append((item, _target_reason(res)))
    out.retry.extend(item for i, item in enumerate(pending) if i not in by_index)
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(value: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def _coerce_spec(raw: str | dict[str, Any] | MappingSpec) -> MappingSpec:
    if isinstance(raw, MappingSpec):
        return raw
    if isinstance(raw, str):
        return MappingSpec.model_validate_json(raw)
    if isinstance(raw, dict):
        return MappingSpec.model_validate(raw)
    raise TypeError(f"expected a MappingSpec JSON string or object, got {type(raw).__name__}")


def _spec_errors(exc: Exception) -> list[str]:
    if isinstance(exc, ValidationError):
        return [f"{'.'.join(str(p) for p in e['loc']) or '<spec>'}: {e['msg']}" for e in exc.errors()][:20]
    return [str(exc)]


def _systematic_codes(codes: Sequence[str | None], min_count: int = 2, min_share: float = 0.1) -> list[str]:
    """Error codes repeated across samples (>= min_count and >= min_share of them)."""
    counted = Counter(code for code in codes if code is not None and code not in DATA_ONLY_CODES)
    return sorted(c for c, n in counted.items() if n >= min_count and n >= min_share * len(codes))


def _primary_code(errors: Sequence[str]) -> str | None:
    codes = [error_code(error) for error in errors]
    structural = [c for c in codes if c in STRUCTURAL_MAPPING_CODES]
    if structural:
        return structural[0]
    return next((c for c in codes if c), None)


def _dsl_reason(errors: Sequence[str]) -> str:
    first = errors[0] if errors else "<record>: invalid_value: mapping failed"
    code = error_code(first) or "invalid_value"
    return f"{DSL_TO_TARGET_CODE.get(code, 'invalid_value')}: {first}"


def _item_error(result: Any) -> TargetItemError | None:
    error = getattr(result, "error", None)
    if error is None or isinstance(error, TargetItemError):
        return error
    if isinstance(error, Mapping):
        return TargetItemError.model_validate(dict(error))
    return TargetItemError(code=str(getattr(error, "code", "unknown")), message=str(error))


def _target_reason(result: Any) -> str:
    error = _item_error(result)
    if error is None:
        return f"http_{getattr(result, 'status', 'unknown')}: no error details"
    parts = [error.code] + ([error.field] if error.field else []) + [error.message or ""]
    return ": ".join(parts)


def _usage_of(planner: Any) -> tuple[int, float]:
    """(calls, cost_usd) from `planner.usage`, the planner itself, or `planner.llm` (attributes or keys)."""
    usage = getattr(planner, "usage", None)
    if callable(usage) and not hasattr(usage, "calls"):
        try:
            usage = usage()
        except Exception:
            usage = None
    for holder in (usage, planner, getattr(planner, "llm", None)):
        if holder is not None and _has_number(holder, "calls"):
            return int(_number(holder, "calls")), float(_number(holder, "cost_usd"))
    return 0, 0.0


def _has_number(holder: Any, name: str) -> bool:
    value = holder.get(name) if isinstance(holder, Mapping) else getattr(holder, name, None)
    return isinstance(value, int | float) and not isinstance(value, bool)


def _number(holder: Any, name: str) -> float:
    value = holder.get(name) if isinstance(holder, Mapping) else getattr(holder, name, 0)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return value


def _planner_tools(planner: Any) -> PlannerTools | None:
    """A `PlannerTools` the planner was built with (shared so both see the same caches)."""
    for name in ("tools", "_tools"):
        tools = getattr(planner, name, None)
        if isinstance(tools, PlannerTools):
            return tools
    return None


def _install_token(target: Any, token: str) -> bool:
    setter = getattr(target, "set_token", None)
    if callable(setter):
        setter(token)
        return True
    if hasattr(target, "_token_provider"):
        target._token_provider = lambda: token
        return True
    return False


def _referenced_entities(spec: MappingSpec) -> set[Entity]:
    return {
        op.entity
        for fm in spec.fields
        for op in fm.ops
        if op.op == "ref" and op.entity is not None and op.entity != spec.entity
    }


def _dependency_order(order: list[Entity], deps: dict[Entity, set[Entity]]) -> list[Entity]:
    """Stable topological order: each entity after the entities its mapping references."""
    result: list[Entity] = []
    remaining = list(order)
    while remaining:
        ready = next(
            (e for e in remaining if all(d in result or d not in remaining for d in deps.get(e, set()))),
            None,
        )
        if ready is None:  # reference cycle: keep the planner's order
            return result + remaining
        result.append(ready)
        remaining.remove(ready)
    return result


def _spec_summary(spec: MappingSpec) -> dict[str, Any]:
    return {
        "version": spec.version,
        "target_api_version": spec.target_api_version,
        "fields": [fm.target for fm in spec.fields],
        "exclude_if": [c.model_dump(mode="json") for c in spec.exclude_if],
        "rationale": spec.rationale,
    }


def _mapping_changes(old: MappingSpec, new: MappingSpec) -> dict[str, list[str]]:
    before = {fm.target: fm.model_dump(mode="json") for fm in old.fields}
    after = {fm.target: fm.model_dump(mode="json") for fm in new.fields}
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(name for name in set(before) & set(after) if before[name] != after[name]),
    }
