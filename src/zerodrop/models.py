"""Shared, frozen contracts for every ZeroDrop component.

Changing anything here changes the interface between the sandbox, the engine,
the agent and the verifier. Keep edits deliberate and update docs/CONTRACTS.md.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Entities and run lifecycle
# ---------------------------------------------------------------------------


class Entity(StrEnum):
    customers = "customers"
    subscriptions = "subscriptions"
    invoices = "invoices"


ENTITY_ORDER: tuple[Entity, ...] = (Entity.customers, Entity.subscriptions, Entity.invoices)


class RunStatus(StrEnum):
    CREATED = "CREATED"
    DISCOVERING = "DISCOVERING"
    PLANNING = "PLANNING"
    DRY_RUN = "DRY_RUN"
    EXECUTING = "EXECUTING"
    RECOVERING = "RECOVERING"
    VERIFYING = "VERIFYING"
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"


TERMINAL_STATUSES: frozenset[RunStatus] = frozenset(
    {RunStatus.SUCCESS, RunStatus.PARTIAL_SUCCESS, RunStatus.FAILED, RunStatus.WAITING_FOR_APPROVAL}
)


class RecordState(StrEnum):
    PENDING = "PENDING"
    WRITTEN = "WRITTEN"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"


class FailureClass(StrEnum):
    TRANSIENT = "TRANSIENT"  # 429, 5xx, connection reset: back off and retry the same request
    AMBIGUOUS_WRITE = "AMBIGUOUS_WRITE"  # timeout after sending: look up before re-sending
    CONTRACT = "CONTRACT"  # target contract changed or mapping wrong for most items: replan
    DATA = "DATA"  # one record is invalid: quarantine it and continue
    AUTH = "AUTH"  # 401/403: re-read credentials once, else wait for approval
    DESTRUCTIVE = "DESTRUCTIVE"  # any delete/overwrite: always wait for approval
    BUDGET = "BUDGET"  # LLM-call / cost / time cap reached
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Mapping DSL (produced by the LLM as structured output, executed deterministically)
# ---------------------------------------------------------------------------

OpName = Literal[
    "lower",  # str -> lower-case
    "upper",  # str -> upper-case
    "strip",  # str -> stripped
    "split_name",  # "Given Family" -> part ("first" = first token, "last" = remaining tokens joined by space)
    "parse_datetime",  # str -> ISO-8601 UTC "YYYY-MM-DDTHH:MM:SSZ"; tries `formats` in order; naive values use `assume_tz`
    "decimal_to_minor",  # "129.00" -> 12900; `decimals`, or the ISO-4217 minor units of `currency_field` (both: must agree)
    "to_int",  # "3" -> 3
    "enum_map",  # value -> mapped value via `mapping`; unmapped values use `default` or fail the record
    "ref",  # source id -> target id of an already-migrated record of `entity` (engine id-map)
    "lookup",  # value -> `return_field` of the row in target reference `table` whose `match_field` equals value
    "bool_map",  # value -> True if str(value) in `true_values` else False
    "const",  # ignore input; emit `value`
    "null_if_empty",  # "" / None -> None
]


class EnumPair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    target: str


class TransformOp(BaseModel):
    """One step of a field transform. Only the parameters relevant to `op` are set."""

    model_config = ConfigDict(extra="forbid")
    op: OpName
    part: Literal["first", "last"] | None = None
    formats: list[str] | None = None  # strptime formats, e.g. ["%m/%d/%Y", "%Y-%m-%d %H:%M:%S"]
    assume_tz: str | None = None  # IANA tz name for naive datetimes, e.g. "Asia/Kolkata"
    decimals: int | None = None
    currency_field: str | None = None  # source field holding the ISO-4217 code
    mapping: list[EnumPair] | None = None
    default: str | None = None
    entity: Entity | None = None
    table: str | None = None
    match_field: str | None = None
    return_field: str | None = None
    true_values: list[str] | None = None
    value: str | int | bool | None = None


class FieldMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str  # target payload field name (flat)
    source: str | None = None  # source record field name; None only with a leading `const` op
    ops: list[TransformOp] = Field(default_factory=list)
    required: bool = True  # a None result on a required field fails the record (DATA)


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    equals: str | int | bool | None


class MappingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity: Entity
    version: int = 1
    target_api_version: str  # the target schema version this mapping was written for, e.g. "v1"
    fields: list[FieldMapping]
    exclude_if: list[Condition] = Field(
        default_factory=list
    )  # source records matching any condition are skipped
    rationale: str = ""  # short human-readable justification (shown in UI and traces)


class MigrationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_order: list[Entity]
    mappings: list[MappingSpec]
    notes: str = ""

    def mapping_for(self, entity: Entity) -> MappingSpec:
        for m in self.mappings:
            if m.entity == entity:
                return m
        raise KeyError(entity)


# ---------------------------------------------------------------------------
# Agent contexts (what the planner / diagnoser get to see)
# ---------------------------------------------------------------------------


class SourceEntityInfo(BaseModel):
    entity: str
    count_reported: int  # what the source /count endpoint says (may include soft-deleted rows)
    fields: dict[str, str]  # field -> description from the source data dictionary
    samples: list[dict[str, Any]]


class DiscoveryContext(BaseModel):
    goal: str
    source_account: dict[str, Any]  # e.g. {"timezone": "Asia/Kolkata", ...}
    source_entities: list[SourceEntityInfo]
    target_schema: dict[str, Any]  # NovaBill /api/schema document (current version)
    target_reference_tables: dict[str, list[dict[str, Any]]]  # e.g. {"prices": [...]} (samples)


class TargetItemError(BaseModel):
    code: str
    field: str | None = None
    message: str = ""


class FailedItemSample(BaseModel):
    source_id: str
    payload: dict[str, Any]
    status: int
    error: TargetItemError | None = None


class RepairContext(BaseModel):
    entity: Entity
    current_mapping: MappingSpec
    failed_samples: list[FailedItemSample]
    previous_schema: dict[str, Any]
    current_schema: dict[str, Any]
    target_reference_tables: dict[str, list[dict[str, Any]]]
    source_samples: list[dict[str, Any]]
    other_pending_mappings: list[MappingSpec] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Events (persisted, streamed to the UI, mirrored into traces)
# ---------------------------------------------------------------------------

EventKind = Literal["state", "plan", "batch", "failure", "recovery", "decision", "verify", "llm", "info"]


class RunEvent(BaseModel):
    run_id: str
    seq: int
    ts: float
    kind: EventKind
    message: str
    state: RunStatus | None = None
    entity: Entity | None = None
    data: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Chaos / fault injection (sandbox side; the agent never sees this)
# ---------------------------------------------------------------------------

FaultKind = Literal[
    "rate_limit",  # respond 429 with Retry-After for `count` requests
    "server_error",  # respond 500/503 for `count` requests
    "timeout_after_write",  # commit the write, then stall longer than the client timeout
    "partial_accept",  # accept the first `accept_first` items of a batch, 503 the rest
    "schema_flip",  # switch the target API to schema version `to_version` (persistent)
    "auth_revoke",  # 401 until the client presents the rotated token
    "slow",  # add `delay_s` latency for `count` requests
]


class FaultRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: FaultKind
    entity: Entity | None = None  # None = any batch-write endpoint
    after_requests: int = 0  # trigger when this many matching write requests have been served
    count: int = 1
    retry_after_s: float = 0.2
    accept_first: int = 0
    to_version: str = "v2"
    delay_s: float = 0.0


class FaultPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed: int = 0
    rules: list[FaultRule] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


class PreservationContract(BaseModel):
    """Business invariants the user declares. The verifier checks these; the agent cannot edit them."""

    model_config = ConfigDict(extra="forbid")
    entities: list[Entity] = Field(default_factory=lambda: list(ENTITY_ORDER))
    exclude_deleted_customers: bool = True
    money_by_currency: bool = True  # sum(invoice amounts) per currency, in minor units, must match
    referential_integrity: bool = True
    golden_path: str | None = None  # eval only: expected target records produced by the fixture generator


class CheckResult(BaseModel):
    name: str
    passed: bool
    entity: Entity | None = None
    expected: Any = None
    actual: Any = None
    detail: str = ""


class QuarantineItem(BaseModel):
    entity: Entity
    source_id: str
    reason: str


class ReconciliationReport(BaseModel):
    run_id: str
    status: RunStatus  # SUCCESS | PARTIAL_SUCCESS | FAILED (decided by the verifier, not the agent)
    checks: list[CheckResult]
    quarantined: list[QuarantineItem] = Field(default_factory=list)
    source_counts: dict[str, int] = Field(default_factory=dict)
    target_counts: dict[str, int] = Field(default_factory=dict)
    money_source_minor: dict[str, int] = Field(default_factory=dict)
    money_target_minor: dict[str, int] = Field(default_factory=dict)
    report_hash: str = ""
