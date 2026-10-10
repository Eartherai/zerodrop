"""Deterministic, network-free stand-ins for the agent layer.

- `FakePlanner(mode="oracle")` returns the correct plan for the sandbox semantics
  (docs/CONTRACTS.md section 1) and the correct repair after the v2 schema flip.
- `FakePlanner(mode="naive")` returns a plausible but flawed plan (a fixed 2 decimals
  for every currency, no e-mail lower-casing, currency case left as is) and repairs
  only the entity that failed.
- `ScriptedBackend` is an `LLMBackend` that replays canned responses for unit tests.
"""

from __future__ import annotations

import copy
import itertools
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from zerodrop.agent.llm import UsageTotals
from zerodrop.models import (
    ENTITY_ORDER,
    Condition,
    DiscoveryContext,
    Entity,
    EnumPair,
    FailedItemSample,
    FieldMapping,
    MappingSpec,
    MigrationPlan,
    RepairContext,
    TransformOp,
)

FakeMode = Literal["oracle", "naive"]

CUSTOMER_STATUS = (("A", "active"), ("S", "suspended"), ("X", "closed"))
SUBSCRIPTION_STATE = (
    ("live", "active"),
    ("past_due", "delinquent"),
    ("cancelled", "canceled"),
    ("trial", "trialing"),
)
INVOICE_PAID = (("Y", "paid"), ("N", "open"))
PRICE_LOOKUP = TransformOp(op="lookup", table="prices", match_field="lookup_key", return_field="id")


# ---------------------------------------------------------------------------
# Mapping builders
# ---------------------------------------------------------------------------


def _op(op: Any, **params: Any) -> TransformOp:
    return TransformOp(op=op, **params)


def _enum(pairs: Iterable[tuple[str, str]]) -> TransformOp:
    return _op("enum_map", mapping=[EnumPair(source=s, target=t) for s, t in pairs])


def _field(target: str, source: str | None, *ops: TransformOp, required: bool = True) -> FieldMapping:
    return FieldMapping(target=target, source=source, ops=list(ops), required=required)


def _properties(schema: dict[str, Any], entity: str) -> dict[str, Any]:
    return ((schema.get("entities") or {}).get(entity) or {}).get("properties") or {}


def schema_version(schema: dict[str, Any]) -> str:
    return str(schema.get("version") or "v1")


def customers_spec(tz: str, version: str = "v1", *, lower_email: bool = True) -> MappingSpec:
    email_ops = [_op("strip"), _op("lower")] if lower_email else [_op("strip")]
    return MappingSpec(
        entity=Entity.customers,
        target_api_version=version,
        fields=[
            _field("external_id", "cust_id"),
            _field("given_name", "full_name", _op("split_name", part="first")),
            _field("family_name", "full_name", _op("split_name", part="last")),
            _field("email", "email", *email_ops),
            _field("country", "country", _op("strip"), _op("upper")),
            _field("status", "status", _enum(CUSTOMER_STATUS)),
            _field("created_at", "created", _op("parse_datetime", formats=["%m/%d/%Y"], assume_tz=tz)),
            _field("notes", "notes", _op("null_if_empty"), required=False),
        ],
        exclude_if=[Condition(field="deleted", equals=True)],
        rationale=f"Split full_name, normalize email/country case, local dates in {tz} to UTC; skip soft-deleted.",
    )


def subscriptions_spec(tz: str, version: str = "v1", *, price_id: bool = False) -> MappingSpec:
    plan = _field("price_id", "plan_code", PRICE_LOOKUP) if price_id else _field("plan_code", "plan_code")
    return MappingSpec(
        entity=Entity.subscriptions,
        target_api_version=version,
        fields=[
            _field("external_id", "sub_id"),
            _field("customer_id", "cust_id", _op("ref", entity=Entity.customers)),
            plan,
            _field("status", "state", _enum(SUBSCRIPTION_STATE)),
            _field("start_at", "started", _op("parse_datetime", formats=["%Y-%m-%d %H:%M:%S"], assume_tz=tz)),
            _field("quantity", "seats", _op("to_int")),
        ],
        rationale=(
            "Plan via the prices table (lookup_key -> id)."
            if price_id
            else "Plan code is the catalog lookup_key."
        )
        + f" Naive start times are {tz} wall-clock.",
    )


def invoices_spec(
    version: str = "v1", *, fixed_decimals: int | None = None, lower_currency: bool = True
) -> MappingSpec:
    amount = (
        _op("decimal_to_minor", decimals=fixed_decimals)
        if fixed_decimals is not None
        else _op("decimal_to_minor", currency_field="currency")
    )
    currency_ops = [_op("strip"), _op("lower")] if lower_currency else [_op("strip")]
    return MappingSpec(
        entity=Entity.invoices,
        target_api_version=version,
        fields=[
            _field("external_id", "inv_id"),
            _field("customer_id", "cust_id", _op("ref", entity=Entity.customers)),
            _field(
                "subscription_id",
                "sub_id",
                _op("null_if_empty"),
                _op("ref", entity=Entity.subscriptions),
                required=False,
            ),
            _field("amount_minor", "amount", amount),
            _field("currency", "currency", *currency_ops),
            _field("issued_at", "issued", _op("parse_datetime", formats=["%Y-%m-%d"], assume_tz="UTC")),
            _field("status", "paid", _enum(INVOICE_PAID)),
        ],
        rationale="Amounts to ISO-4217 minor units per currency; issue dates are UTC; empty sub_id -> null.",
    )


def oracle_spec(entity: Entity, tz: str, schema: dict[str, Any]) -> MappingSpec:
    """The correct mapping for `entity` under the given NovaBill schema document."""
    version = schema_version(schema)
    if entity == Entity.customers:
        return customers_spec(tz, version)
    if entity == Entity.subscriptions:
        return subscriptions_spec(tz, version, price_id="price_id" in _properties(schema, "subscriptions"))
    return invoices_spec(version)


def naive_spec(entity: Entity, tz: str, schema: dict[str, Any]) -> MappingSpec:
    version = schema_version(schema)
    if entity == Entity.customers:
        return customers_spec(tz, version, lower_email=False)
    if entity == Entity.invoices:
        return invoices_spec(version, fixed_decimals=2, lower_currency=False)
    return oracle_spec(entity, tz, schema)


# ---------------------------------------------------------------------------
# Patching helpers (naive repair)
# ---------------------------------------------------------------------------


def _requires_lowercase(prop: dict[str, Any] | None) -> bool:
    if not prop:
        return False
    pattern = str(prop.get("pattern") or "")
    return ("a-z" in pattern and "A-Z" not in pattern) or "lower-case" in str(
        prop.get("description") or ""
    ).lower()


def _with_lower(fm: FieldMapping) -> FieldMapping:
    ops = [op for op in fm.ops if op.op not in ("lower", "upper")] + [_op("lower")]
    return fm.model_copy(update={"ops": ops})


def adapt_to_schema(spec: MappingSpec, schema: dict[str, Any]) -> MappingSpec:
    """Patch one mapping for the current schema: plan_code <-> price_id, lower-case-only fields."""
    props = _properties(schema, spec.entity.value)
    fields = []
    for fm in spec.fields:
        if fm.target == "plan_code" and "plan_code" not in props and "price_id" in props:
            fm = _field("price_id", fm.source, PRICE_LOOKUP)
        elif fm.target == "price_id" and "price_id" not in props and "plan_code" in props:
            fm = _field("plan_code", fm.source)
        elif _requires_lowercase(props.get(fm.target)) and (not fm.ops or fm.ops[-1].op != "lower"):
            fm = _with_lower(fm)
        fields.append(fm)
    return spec.model_copy(update={"fields": fields, "target_api_version": schema_version(schema)})


def lowercase_failed_fields(spec: MappingSpec, failed: Iterable[FailedItemSample]) -> MappingSpec:
    names = {s.error.field for s in failed if s.error and s.error.code == "not_lowercase" and s.error.field}
    fields = [
        _with_lower(fm) if fm.target in names and (not fm.ops or fm.ops[-1].op != "lower") else fm
        for fm in spec.fields
    ]
    return spec.model_copy(update={"fields": fields})


def _timezone_in(specs: Iterable[MappingSpec]) -> str | None:
    for spec in specs:
        if spec.entity == Entity.invoices:
            continue
        for fm in spec.fields:
            for op in fm.ops:
                if op.op == "parse_datetime" and op.assume_tz:
                    return op.assume_tz
    return None


def _same_mapping(a: MappingSpec, b: MappingSpec) -> bool:
    exclude = {"version", "rationale"}
    return a.model_dump(mode="json", exclude=exclude) == b.model_dump(mode="json", exclude=exclude)


# ---------------------------------------------------------------------------
# FakePlanner
# ---------------------------------------------------------------------------


class FakePlanner:
    """The `Planner` protocol with zero network calls."""

    def __init__(self, mode: FakeMode = "oracle") -> None:
        if mode not in ("oracle", "naive"):
            raise ValueError(f"unknown FakePlanner mode {mode!r}; expected 'oracle' or 'naive'")
        self.mode = mode
        self.usage = UsageTotals()
        self.tools: Any = None
        self.plan_calls: list[DiscoveryContext] = []
        self.repair_calls: list[RepairContext] = []
        self._timezone: str | None = None

    def bind_tools(self, tools: Any) -> None:
        self.tools = tools

    def plan(self, ctx: DiscoveryContext) -> MigrationPlan:
        self.plan_calls.append(ctx)
        tz = str(ctx.source_account.get("timezone") or "UTC")
        self._timezone = tz
        known = {e.value for e in Entity}
        wanted = [Entity(s.entity) for s in ctx.source_entities if s.entity in known] or list(ENTITY_ORDER)
        build = oracle_spec if self.mode == "oracle" else naive_spec
        order = [e for e in ENTITY_ORDER if e in wanted]
        return MigrationPlan(
            entity_order=order,
            mappings=[build(e, tz, ctx.target_schema) for e in order],
            notes=f"FakePlanner ({self.mode}) plan; account timezone {tz}.",
        )

    def repair(self, ctx: RepairContext) -> list[MappingSpec]:
        self.repair_calls.append(ctx)
        if self.mode == "naive":
            spec = lowercase_failed_fields(
                adapt_to_schema(ctx.current_mapping, ctx.current_schema), ctx.failed_samples
            )
            return [spec.model_copy(update={"version": ctx.current_mapping.version + 1})]
        pending = [ctx.current_mapping, *ctx.other_pending_mappings]
        tz = _timezone_in(pending) or self._timezone or "UTC"
        out = []
        for spec in pending:
            fixed = oracle_spec(spec.entity, tz, ctx.current_schema)
            if spec.entity == ctx.entity or not _same_mapping(fixed, spec):
                out.append(fixed.model_copy(update={"version": spec.version + 1}))
        return out


# ---------------------------------------------------------------------------
# Scripted LLM backend
# ---------------------------------------------------------------------------


@dataclass
class FakeBlock:
    type: str
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: Any = None
    thinking: str | None = None


@dataclass
class FakeIteration:
    type: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class FakeUsage:
    input_tokens: int = 1000
    output_tokens: int = 200
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    iterations: list[FakeIteration] | None = None


@dataclass
class FakeStopDetails:
    category: str | None = None
    explanation: str | None = None
    type: str = "refusal"


@dataclass
class FakeMessage:
    content: list[FakeBlock]
    stop_reason: str
    model: str = "claude-opus-5-5"
    usage: FakeUsage = field(default_factory=FakeUsage)
    stop_details: FakeStopDetails | None = None
    id: str = "msg_fake"
    role: str = "assistant"
    type: str = "message"


_ids = itertools.count(1)


def text_message(
    text: str = "Done.", *, usage: FakeUsage | None = None, model: str = "claude-opus-5-5"
) -> FakeMessage:
    return FakeMessage([FakeBlock("text", text=text)], "end_turn", model=model, usage=usage or FakeUsage())


def tool_message(
    *calls: tuple[str, Any],
    text: str | None = None,
    usage: FakeUsage | None = None,
    model: str = "claude-opus-5-5",
) -> FakeMessage:
    """An assistant turn calling tools; each call is (name, input dict or raw JSON string)."""
    blocks = [FakeBlock("thinking", thinking="")]
    if text:
        blocks.append(FakeBlock("text", text=text))
    blocks += [FakeBlock("tool_use", id=f"toolu_{next(_ids):04d}", name=n, input=i) for n, i in calls]
    return FakeMessage(blocks, "tool_use", model=model, usage=usage or FakeUsage())


def refusal_message(category: str | None = "cyber", *, usage: FakeUsage | None = None) -> FakeMessage:
    return FakeMessage(
        [], "refusal", usage=usage or FakeUsage(output_tokens=0), stop_details=FakeStopDetails(category)
    )


def max_tokens_message(*, usage: FakeUsage | None = None) -> FakeMessage:
    return FakeMessage(
        [FakeBlock("thinking", thinking=""), FakeBlock("text", text="partial")],
        "max_tokens",
        usage=usage or FakeUsage(),
    )


ScriptItem = FakeMessage | Exception | Callable[[dict[str, Any]], Any]


class ScriptedBackend:
    """An `LLMBackend` replaying canned responses in order and recording every request."""

    def __init__(self, script: Iterable[ScriptItem]) -> None:
        self._script = list(script)
        self.requests: list[dict[str, Any]] = []

    @property
    def remaining(self) -> int:
        return len(self._script)

    def create(self, request: dict[str, Any]) -> Any:
        self.requests.append(copy.deepcopy(request))
        if not self._script:
            raise AssertionError("ScriptedBackend: no scripted response left")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item) and not isinstance(item, FakeMessage):
            return item(request)
        return item
