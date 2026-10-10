"""Independent verifier: reconciles LegacyBill (source) with NovaBill (target).

The verifier re-derives the canonical NovaBill values from LegacyBill semantics
(docs/CONTRACTS.md section 1) with its own tables and parsers. It never imports the
engine, the mapping DSL, the ledger or the agent, so a wrong agent mapping cannot
verify itself. It reads both systems fresh and decides the final run status.

Status rules: every check passes and nothing is quarantined -> SUCCESS; every check
passes and something is quarantined (each item expected by the golden file or carrying
a DATA-type reason, which the ``quarantine_reasons`` check enforces) -> PARTIAL_SUCCESS;
otherwise FAILED.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from functools import partial
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from zerodrop import telemetry
from zerodrop.models import (
    ENTITY_ORDER,
    CheckResult,
    Entity,
    PreservationContract,
    QuarantineItem,
    ReconciliationReport,
    RunStatus,
)

# ---------------------------------------------------------------------------
# LegacyBill semantics (own copy; deliberately not shared with the engine)
# ---------------------------------------------------------------------------

SOURCE_ID_FIELD: dict[Entity, str] = {
    Entity.customers: "cust_id",
    Entity.subscriptions: "sub_id",
    Entity.invoices: "inv_id",
}
CUSTOMER_STATUS: dict[str, str] = {"A": "active", "S": "suspended", "X": "closed"}
SUBSCRIPTION_STATE: dict[str, str] = {
    "live": "active",
    "past_due": "delinquent",
    "cancelled": "canceled",
    "trial": "trialing",
}
INVOICE_PAID: dict[str, str] = {"Y": "paid", "N": "open"}
CREATED_FORMAT = "%m/%d/%Y"  # account-local calendar date (local midnight)
STARTED_FORMAT = "%Y-%m-%d %H:%M:%S"  # naive account-local wall-clock time
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# ISO 4217 minor units; every currency not listed here has 2.
_ZERO_DECIMAL = ("BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX", "UYI", "VND")
_ZERO_DECIMAL_2 = ("VUV", "XAF", "XOF", "XPF")
_THREE_DECIMAL = ("BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND")
_FOUR_DECIMAL = ("CLF", "UYW")
_MINOR_UNITS_EXCEPTIONS: dict[str, int] = {
    **dict.fromkeys(_ZERO_DECIMAL + _ZERO_DECIMAL_2, 0),
    **dict.fromkeys(_THREE_DECIMAL, 3),
    **dict.fromkeys(_FOUR_DECIMAL, 4),
}

# Quarantine reasons that describe a problem with one record (FailureClass.DATA).
DATA_REASON_CODES: frozenset[str] = frozenset(
    {
        "invalid_reference",
        "duplicate_email",
        "invalid_value",
        "missing_field",
        "unknown_field",
        "not_lowercase",
    }
)

# Canonical NovaBill fields compared per entity (the golden record format). Subscriptions are
# also compared on `price_id` when the target record has it (v2), else on `plan_code` (v1).
COMPARED_FIELDS: dict[Entity, tuple[str, ...]] = {
    Entity.customers: ("given_name", "family_name", "email", "country", "status", "created_at", "notes"),
    Entity.subscriptions: ("customer_external_id", "status", "start_at", "quantity"),
    Entity.invoices: (
        "customer_external_id",
        "subscription_external_id",
        "amount_minor",
        "currency",
        "issued_at",
        "status",
    ),
}
TIMESTAMP_FIELDS = frozenset({"created_at", "start_at", "issued_at"})
INT_FIELDS = frozenset({"quantity", "amount_minor"})

MAX_LISTED = 5  # ids / mismatches shown in a check's detail
MAX_REPR = 60
DEFAULT_ATTEMPTS = 5
MAX_AMOUNT_DIGITS = 30  # integer digits accepted in a source amount (far beyond any real invoice)


class SourceLike(Protocol):
    def iter_records(self, entity: str) -> Iterable[dict[str, Any]]: ...

    def account(self) -> dict[str, Any]: ...


class TargetLike(Protocol):
    def list_all(self, entity: str) -> list[dict[str, Any]]: ...

    def prices(self) -> list[dict[str, Any]]: ...


# ---------------------------------------------------------------------------
# Money and time canonicalization
# ---------------------------------------------------------------------------


def minor_units(currency: str) -> int:
    """ISO 4217 minor-unit exponent of `currency` (case-insensitive)."""
    return _MINOR_UNITS_EXCEPTIONS.get(currency.strip().upper(), 2)


def to_minor(amount: Any, currency: str) -> int:
    """Major-unit decimal text ("129.00", "1500") -> integer minor units; raises ValueError if inexact.

    Pure integer arithmetic on the decimal digits: no Decimal context rounding (28 digits)
    and no Overflow on extreme exponents.
    """
    if isinstance(amount, bool) or not isinstance(amount, str | int | Decimal):
        raise ValueError(f"amount {amount!r} is not decimal text")
    try:
        value = Decimal(str(amount).strip())
    except InvalidOperation as exc:
        raise ValueError(f"amount {amount!r} is not a decimal number") from exc
    if not value.is_finite():
        raise ValueError(f"amount {amount!r} is not finite")
    if value and value.adjusted() > MAX_AMOUNT_DIGITS:
        raise ValueError(f"amount {amount!r} is implausibly large")
    sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):  # unreachable for finite values; keeps the type exact
        raise ValueError(f"amount {amount!r} is not finite")
    coefficient = int("".join(map(str, digits)) or "0")
    shift = exponent + minor_units(currency)
    if shift >= 0:
        minor = coefficient * 10**shift
    elif coefficient == 0:
        minor = 0
    elif -shift > len(digits) or coefficient % 10**-shift:
        raise ValueError(f"amount {amount!r} has more decimals than {currency.upper()} allows")
    else:
        minor = coefficient // 10**-shift
    return -minor if sign else minor


def _local_to_utc(text: Any, fmt: str, tz: ZoneInfo | None) -> str:
    if tz is None:
        raise ValueError("source account timezone is unknown")
    local = datetime.strptime(str(text).strip(), fmt)
    return local.replace(tzinfo=tz).astimezone(UTC).strftime(UTC_FORMAT)


def _utc_midnight(text: Any) -> str:
    return f"{date.fromisoformat(str(text).strip()).isoformat()}T00:00:00Z"


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


# ---------------------------------------------------------------------------
# Source records -> canonical NovaBill records (golden format)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SourceContext:
    tz: ZoneInfo | None
    price_id_by_key: dict[str, str]


def _split_name(full_name: Any) -> tuple[str, str]:
    tokens = str(full_name).split()
    if len(tokens) < 2:
        raise ValueError(f"full_name {full_name!r} does not have a given and a family name")
    return tokens[0], " ".join(tokens[1:])


def _code(value: Any, table: Mapping[str, str], label: str) -> str:
    key = str(value).strip()
    for candidate in (key, key.upper(), key.lower()):
        if candidate in table:
            return table[candidate]
    raise ValueError(f"unknown {label} {value!r}")


def _seats(value: Any) -> int:
    seats = int(str(value).strip())
    if seats < 1:
        raise ValueError(f"seats {value!r} is below 1")
    return seats


def _canonical_customer(rec: Mapping[str, Any], ctx: _SourceContext) -> dict[str, Any]:
    given, family = _split_name(rec["full_name"])
    return {
        "external_id": rec["cust_id"],
        "given_name": given,
        "family_name": family,
        "email": str(rec["email"]).strip().lower(),
        "country": str(rec["country"]).strip().upper(),
        "status": _code(rec["status"], CUSTOMER_STATUS, "customer status"),
        "created_at": _local_to_utc(rec["created"], CREATED_FORMAT, ctx.tz),
        "notes": rec.get("notes") or None,
    }


def _canonical_subscription(rec: Mapping[str, Any], ctx: _SourceContext) -> dict[str, Any]:
    plan_code = str(rec["plan_code"]).strip()
    return {
        "external_id": rec["sub_id"],
        "customer_external_id": rec["cust_id"],
        "plan_code": plan_code,
        "price_id": ctx.price_id_by_key.get(plan_code),
        "status": _code(rec["state"], SUBSCRIPTION_STATE, "subscription state"),
        "start_at": _local_to_utc(rec["started"], STARTED_FORMAT, ctx.tz),
        "quantity": _seats(rec["seats"]),
    }


def _canonical_invoice(rec: Mapping[str, Any], ctx: _SourceContext) -> dict[str, Any]:
    currency = str(rec["currency"]).strip()
    return {
        "external_id": rec["inv_id"],
        "customer_external_id": rec["cust_id"],
        "subscription_external_id": str(rec.get("sub_id") or "").strip() or None,
        "amount_minor": to_minor(rec["amount"], currency),
        "currency": currency.lower(),
        "issued_at": _utc_midnight(rec["issued"]),
        "status": _code(rec["paid"], INVOICE_PAID, "paid flag"),
    }


_CANONICALIZERS: dict[Entity, Callable[[Mapping[str, Any], _SourceContext], dict[str, Any]]] = {
    Entity.customers: _canonical_customer,
    Entity.subscriptions: _canonical_subscription,
    Entity.invoices: _canonical_invoice,
}


def canonicalize(entity: Entity, rec: Mapping[str, Any], ctx: _SourceContext) -> dict[str, Any]:
    """One LegacyBill record -> its expected NovaBill record; raises ValueError/KeyError on bad input."""
    return _CANONICALIZERS[entity](rec, ctx)


def _source_context(account: Mapping[str, Any], prices: list[dict[str, Any]]) -> _SourceContext:
    try:
        tz: ZoneInfo | None = ZoneInfo(str(account.get("timezone", "")))
    except (ZoneInfoNotFoundError, ValueError):
        tz = None
    price_ids = {
        str(p["lookup_key"]): str(p["id"]) for p in prices if p.get("lookup_key") and p.get("id") is not None
    }
    return _SourceContext(tz=tz, price_id_by_key=price_ids)


def _is_deleted(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "y", "yes"}


# ---------------------------------------------------------------------------
# Target records -> comparable views (references resolved to external ids)
# ---------------------------------------------------------------------------


def _resolve(target_id: Any, external_by_id: Mapping[str, str]) -> str:
    if isinstance(target_id, str) and target_id in external_by_id:
        return external_by_id[target_id]
    return f"<unresolved {target_id!r}>"


def _target_view(
    entity: Entity, rec: Mapping[str, Any], cust_ext: Mapping[str, str], sub_ext: Mapping[str, str]
) -> dict[str, Any]:
    view: dict[str, Any] = {"external_id": rec.get("external_id")}
    for name in COMPARED_FIELDS[entity]:
        if name == "customer_external_id":
            view[name] = _resolve(rec.get("customer_id"), cust_ext)
        elif name == "subscription_external_id":
            sub_id = rec.get("subscription_id")
            view[name] = None if sub_id is None else _resolve(sub_id, sub_ext)
        else:
            view[name] = rec.get(name)
    if entity is Entity.subscriptions:
        plan_field = "price_id" if "price_id" in rec else "plan_code"
        view[plan_field] = rec.get(plan_field)
    return view


def _same(name: str, expected: Any, actual: Any) -> bool:
    if name in TIMESTAMP_FIELDS:
        exp_t, act_t = _instant(expected), _instant(actual)
        if exp_t is not None and act_t is not None:
            return exp_t == act_t
    if name == "currency":
        return isinstance(expected, str) and isinstance(actual, str) and expected.lower() == actual.lower()
    if name in INT_FIELDS:
        return all(isinstance(v, int) and not isinstance(v, bool) for v in (expected, actual)) and (
            expected == actual
        )
    return expected == actual


def _short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= MAX_REPR else text[: MAX_REPR - 3] + "..."


def _field_mismatches(expected: Mapping[str, Any], view: Mapping[str, Any]) -> list[str]:
    ext_id = view.get("external_id")
    return [
        f"{ext_id}.{name}: expected {_short(expected.get(name))}, got {_short(view[name])}"
        for name in view
        if name != "external_id" and not _same(name, expected.get(name), view[name])
    ]


# ---------------------------------------------------------------------------
# Snapshot of both systems
# ---------------------------------------------------------------------------


@dataclass
class _EntityData:
    entity: Entity
    source_ids: list[str]  # eligible source ids (soft-deleted customers excluded when the contract says so)
    records: dict[str, dict[str, Any]]  # eligible source id -> raw LegacyBill record
    deleted_ids: set[str]
    canonical: dict[str, dict[str, Any]]  # source id -> expected NovaBill record
    canon_errors: dict[str, str]  # source id -> why it could not be canonicalized
    target: list[dict[str, Any]]
    views: dict[str, dict[str, Any]]  # target external_id -> comparable view (first occurrence)
    quarantined: set[str]  # quarantined source ids of this entity

    @property
    def target_ids(self) -> set[str]:
        return set(self.views)

    @property
    def expected_on_target(self) -> set[str]:
        return set(self.source_ids) - self.quarantined


@dataclass(frozen=True)
class _Snapshot:
    account: dict[str, Any]
    source: dict[Entity, list[dict[str, Any]]]
    target: dict[Entity, list[dict[str, Any]]]
    prices: list[dict[str, Any]]


def _is_transient(exc: Exception) -> bool:
    flag = getattr(exc, "transient", None)
    if isinstance(flag, bool):
        return flag
    if getattr(exc, "timeout", False) is True or isinstance(exc, TimeoutError | ConnectionError):
        return True
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    name = type(exc).__name__
    return "Timeout" in name or "Connection" in name


def _retry[T](fn: Callable[[], T], attempts: int, sleep: Callable[[float], None]) -> T:
    attempt = 1
    while True:
        try:
            return fn()
        except Exception as exc:
            if attempt >= attempts or not _is_transient(exc):
                raise
            retry_after = getattr(exc, "retry_after", None)
            delay = retry_after if isinstance(retry_after, int | float) else 0.25 * 2 ** (attempt - 1)
            sleep(min(max(float(delay), 0.0), 5.0))
            attempt += 1


def _source_records(source: SourceLike, entity: Entity) -> list[dict[str, Any]]:
    return [dict(r) for r in source.iter_records(entity.value)]


def _target_records(target: TargetLike, entity: Entity) -> list[dict[str, Any]]:
    return [dict(r) for r in target.list_all(entity.value)]


def _prices(target: TargetLike) -> list[dict[str, Any]]:
    return [dict(p) for p in target.prices()]


def _fetch(
    source: SourceLike,
    target: TargetLike,
    entities: list[Entity],
    attempts: int,
    sleep: Callable[[float], None],
) -> _Snapshot:
    def read[T](fn: Callable[..., T], *args: Any) -> T:
        return _retry(partial(fn, *args), attempts, sleep)

    return _Snapshot(
        account=dict(read(source.account)),
        source={e: read(_source_records, source, e) for e in entities},
        target={e: read(_target_records, target, e) for e in ENTITY_ORDER},
        prices=read(_prices, target),
    )


def _entity_data(
    entity: Entity,
    snapshot: _Snapshot,
    ctx: _SourceContext,
    contract: PreservationContract,
    quarantined: set[str],
    views: dict[str, dict[str, Any]],
) -> _EntityData:
    id_field = SOURCE_ID_FIELD[entity]
    source_ids: list[str] = []
    records: dict[str, dict[str, Any]] = {}
    deleted: set[str] = set()
    canonical: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for rec in snapshot.source[entity]:
        source_id = str(rec.get(id_field, ""))
        if (
            entity is Entity.customers
            and contract.exclude_deleted_customers
            and _is_deleted(rec.get("deleted"))
        ):
            deleted.add(source_id)
            continue
        source_ids.append(source_id)
        records[source_id] = rec
        try:
            canonical[source_id] = canonicalize(entity, rec, ctx)
        except (KeyError, ValueError, TypeError) as exc:
            errors[source_id] = f"{type(exc).__name__}: {exc}"
    return _EntityData(
        entity=entity,
        source_ids=source_ids,
        records=records,
        deleted_ids=deleted,
        canonical=canonical,
        canon_errors=errors,
        target=snapshot.target[entity],
        views=views,
        quarantined=quarantined,
    )


def _build_views(snapshot: _Snapshot) -> dict[Entity, dict[str, dict[str, Any]]]:
    cust_ext = _external_by_id(snapshot.target[Entity.customers])
    sub_ext = _external_by_id(snapshot.target[Entity.subscriptions])
    views: dict[Entity, dict[str, dict[str, Any]]] = {}
    for entity in ENTITY_ORDER:
        by_ext: dict[str, dict[str, Any]] = {}
        for rec in snapshot.target[entity]:
            ext = rec.get("external_id")
            if isinstance(ext, str) and ext not in by_ext:
                by_ext[ext] = _target_view(entity, rec, cust_ext, sub_ext)
        views[entity] = by_ext
    return views


def _external_by_id(records: list[dict[str, Any]]) -> dict[str, str]:
    return {
        r["id"]: r["external_id"]
        for r in records
        if isinstance(r.get("id"), str) and isinstance(r.get("external_id"), str)
    }


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _preview(items: Iterable[str], limit: int = MAX_LISTED) -> str:
    listed = list(items)
    shown = ", ".join(listed[:limit])
    return shown + (f" (+{len(listed) - limit} more)" if len(listed) > limit else "")


def _check_count(d: _EntityData) -> CheckResult:
    q_in_source = len(d.quarantined & set(d.source_ids))
    expected = len(d.source_ids) - q_in_source
    actual = len(d.target)
    detail = (
        f"source {len(d.source_ids)} ({len(d.deleted_ids)} soft-deleted excluded), "
        f"quarantined {q_in_source}, target {actual}"
    )
    return CheckResult(
        name="count",
        entity=d.entity,
        passed=expected == actual,
        expected=expected,
        actual=actual,
        detail=detail,
    )


def _check_duplicates(d: _EntityData) -> CheckResult:
    ext_ids = [r.get("external_id") for r in d.target]
    without_id = sum(1 for e in ext_ids if not isinstance(e, str) or not e)
    dups = sorted(e for e, n in Counter(e for e in ext_ids if isinstance(e, str) and e).items() if n > 1)
    problems = [f"duplicated: {_preview(dups)}"] if dups else []
    if without_id:
        problems.append(f"{without_id} record(s) without external_id")
    return CheckResult(
        name="no_duplicate_external_ids",
        entity=d.entity,
        passed=not problems,
        expected=0,
        actual=len(dups) + without_id,
        detail="; ".join(problems),
    )


def _check_missing(d: _EntityData) -> CheckResult:
    missing = sorted(d.expected_on_target - d.target_ids)
    return CheckResult(
        name="missing_records_quarantined",
        entity=d.entity,
        passed=not missing,
        expected=0,
        actual=len(missing),
        detail=f"missing from target and not quarantined: {_preview(missing)}" if missing else "",
    )


def _check_unexpected(d: _EntityData) -> CheckResult:
    unexpected = sorted(d.target_ids - d.expected_on_target)
    labels = [_unexpected_label(d, ext) for ext in unexpected]
    return CheckResult(
        name="no_unexpected_records",
        entity=d.entity,
        passed=not unexpected,
        expected=0,
        actual=len(unexpected),
        detail=f"on target but not expected: {_preview(labels)}" if unexpected else "",
    )


def _unexpected_label(d: _EntityData, ext: str) -> str:
    if ext in d.deleted_ids:
        return f"{ext} (soft-deleted)"
    if ext in d.quarantined:
        return f"{ext} (quarantined)"
    return f"{ext} (not in source)"


def _check_unique_emails(d: _EntityData) -> CheckResult:
    owners: dict[str, list[str]] = defaultdict(list)
    for rec in d.target:
        email = rec.get("email")
        if isinstance(email, str):
            owners[email.strip().lower()].append(str(rec.get("external_id")))
    clashes = sorted("/".join(sorted(ids)) for ids in owners.values() if len(ids) > 1)
    return CheckResult(
        name="unique_emails",
        entity=d.entity,
        passed=not clashes,
        expected=0,
        actual=len(clashes),
        detail=f"case-insensitive email shared by: {_preview(clashes)}" if clashes else "",
    )


def _check_source_fidelity(d: _EntityData) -> CheckResult:
    """Every target record equals the verifier's own canonicalization of its source record."""
    compared = sorted(d.target_ids & set(d.source_ids))
    problems: list[str] = []
    matching = 0
    for ext in compared:
        if ext in d.canon_errors:
            problems.append(f"{ext}: source record not canonicalizable ({d.canon_errors[ext]})")
            continue
        mismatches = _field_mismatches(d.canonical[ext], d.views[ext])
        problems.extend(mismatches)
        matching += not mismatches
    return CheckResult(
        name="source_fidelity",
        entity=d.entity,
        passed=not problems,
        expected=len(compared),
        actual=matching,
        detail=_problems_detail(problems),
    )


def _problems_detail(problems: list[str]) -> str:
    if not problems:
        return ""
    return (
        f"{len(problems)} problem(s): "
        + "; ".join(problems[:MAX_LISTED])
        + (" ..." if len(problems) > MAX_LISTED else "")
    )


def _check_subscription_refs(d: _EntityData, cust_ids: set[str], prices: list[dict[str, Any]]) -> CheckResult:
    price_ids = {p["id"] for p in prices if isinstance(p.get("id"), str)}
    lookup_keys = {p["lookup_key"] for p in prices if isinstance(p.get("lookup_key"), str)}
    problems: list[str] = []
    for rec in d.target:
        ext = rec.get("external_id")
        if not _member(rec.get("customer_id"), cust_ids):
            problems.append(f"{ext}.customer_id {_short(rec.get('customer_id'))} not found")
        if "price_id" in rec:
            if not _member(rec["price_id"], price_ids):
                problems.append(f"{ext}.price_id {_short(rec['price_id'])} not in catalog")
        elif not _member(rec.get("plan_code"), lookup_keys):
            problems.append(f"{ext}.plan_code {_short(rec.get('plan_code'))} not in catalog")
    return _refs_result(d.entity, problems)


def _check_invoice_refs(d: _EntityData, cust_ids: set[str], subs: list[dict[str, Any]]) -> CheckResult:
    sub_owner = {s["id"]: s.get("customer_id") for s in subs if isinstance(s.get("id"), str)}
    problems: list[str] = []
    for rec in d.target:
        ext, cust, sub = rec.get("external_id"), rec.get("customer_id"), rec.get("subscription_id")
        if not _member(cust, cust_ids):
            problems.append(f"{ext}.customer_id {_short(cust)} not found")
        if sub is None:
            continue
        if not _member(sub, sub_owner):
            problems.append(f"{ext}.subscription_id {_short(sub)} not found")
        elif sub_owner[sub] != cust:
            problems.append(f"{ext}.subscription_id {_short(sub)} belongs to another customer")
    return _refs_result(d.entity, problems)


def _member(value: Any, ids: Collection[str]) -> bool:
    """Membership for ids read from the target; a non-string value (even unhashable) is never an id."""
    return isinstance(value, str) and value in ids


def _refs_result(entity: Entity, problems: list[str]) -> CheckResult:
    return CheckResult(
        name="referential_integrity",
        entity=entity,
        passed=not problems,
        expected=0,
        actual=len(problems),
        detail=_problems_detail(problems),
    )


def _money(
    invoices: _EntityData, target: list[dict[str, Any]]
) -> tuple[dict[str, int], dict[str, int], dict[str, int], list[str]]:
    """(all eligible source, expected on target, target) sums per upper-case currency, plus problems.

    Source amounts are converted straight from the raw LegacyBill fields, so an unrelated
    unparseable field (e.g. a paid flag) does not affect the money check.
    """
    source_all: Counter[str] = Counter()
    expected: Counter[str] = Counter()
    problems: list[str] = []
    for source_id, rec in invoices.records.items():
        try:
            currency = str(rec["currency"]).strip().upper()
            amount = to_minor(rec["amount"], currency)
        except (KeyError, ValueError) as exc:
            if source_id not in invoices.quarantined:  # a quarantined invoice is accounted for
                problems.append(f"{source_id}: source amount unusable ({exc})")
            continue
        source_all[currency] += amount
        if source_id not in invoices.quarantined:
            expected[currency] += amount
    actual: Counter[str] = Counter()
    for rec in target:
        amount, currency = rec.get("amount_minor"), rec.get("currency")
        if isinstance(amount, bool) or not isinstance(amount, int) or not isinstance(currency, str):
            problems.append(f"{rec.get('external_id')}: target amount/currency unusable")
            continue
        actual[currency.upper()] += amount
    return _sorted(source_all), _sorted(expected), _sorted(actual), problems


def _sorted(counter: Counter[str]) -> dict[str, int]:
    return {k: counter[k] for k in sorted(counter)}


def _check_money(expected: dict[str, int], actual: dict[str, int], problems: list[str]) -> CheckResult:
    diffs = []
    for currency in sorted(set(expected) | set(actual)):
        exp, act = expected.get(currency, 0), actual.get(currency, 0)
        if exp != act:
            ratio = f" (x{act / exp:g})" if exp else ""
            diffs.append(f"{currency}: expected {exp}, got {act}{ratio}")
    all_problems = diffs + problems
    return CheckResult(
        name="money_by_currency",
        entity=Entity.invoices,
        passed=not all_problems,
        expected=expected,
        actual=actual,
        detail=_problems_detail(all_problems),
    )


# -- golden (eval only) -------------------------------------------------------


def _load_golden(path: str) -> dict[str, Any]:
    golden = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(golden, dict):
        raise ValueError("golden file is not a JSON object")
    for key in (*(e.value for e in ENTITY_ORDER), "expected_quarantine"):
        rows = golden.get(key)
        if rows is not None and not (isinstance(rows, list) and all(isinstance(r, dict) for r in rows)):
            raise ValueError(f"golden {key!r} is not a list of objects")
    return golden


def _check_golden_records(d: _EntityData, golden_records: list[dict[str, Any]]) -> CheckResult:
    golden_by_id = {str(r.get("external_id")): r for r in golden_records}
    missing = sorted(set(golden_by_id) - d.target_ids)
    unexpected = sorted(d.target_ids - set(golden_by_id))
    problems = [f"missing: {_preview(missing)}"] if missing else []
    if unexpected:
        problems.append(f"unexpected: {_preview(unexpected)}")
    matching = 0
    for ext in sorted(set(golden_by_id) & d.target_ids):
        mismatches = _field_mismatches(golden_by_id[ext], d.views[ext])
        problems.extend(mismatches)
        matching += not mismatches
    return CheckResult(
        name="golden_records",
        entity=d.entity,
        passed=not problems,
        expected=len(golden_by_id),
        actual=matching,
        detail=_problems_detail(problems),
    )


def _normalized_reason(reason: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", reason.lower()).strip("_")


def _reason_has_code(reason: str, code: str) -> bool:
    return f"_{_normalized_reason(code)}_" in f"_{_normalized_reason(reason)}_"


def is_data_reason(reason: str) -> bool:
    """True when a quarantine reason names a single-record problem (a 422 code or a DATA prefix)."""
    norm = _normalized_reason(reason)
    return (
        norm == "data"
        or norm.startswith("data_")
        or any(_reason_has_code(reason, c) for c in DATA_REASON_CODES)
    )


def _check_golden_quarantine(
    expected_items: list[dict[str, Any]], quarantined: list[QuarantineItem], entities: list[Entity]
) -> CheckResult:
    scope = {e.value for e in entities}
    expected = {
        (str(i.get("entity")), str(i.get("source_id"))): str(i.get("reason_code", ""))
        for i in expected_items
        if str(i.get("entity")) in scope
    }
    actual = {(q.entity.value, q.source_id): q.reason for q in quarantined if q.entity.value in scope}
    not_quarantined = [f"{e}:{s}" for e, s in sorted(set(expected) - set(actual))]
    surplus = [f"{e}:{s}" for e, s in sorted(set(actual) - set(expected))]
    wrong_reason = [
        f"{e}:{s} reason {_short(actual[(e, s)])} lacks code {expected[(e, s)]!r}"
        for e, s in sorted(set(expected) & set(actual))
        if expected[(e, s)] and not _reason_has_code(actual[(e, s)], expected[(e, s)])
    ]
    problems = [f"expected but not quarantined: {_preview(not_quarantined)}"] if not_quarantined else []
    if surplus:
        problems.append(f"quarantined but not expected: {_preview(surplus)}")
    problems.extend(wrong_reason)
    return CheckResult(
        name="golden_quarantine",
        passed=not problems,
        expected=sorted(f"{e}:{s}" for e, s in expected),
        actual=sorted(f"{e}:{s}" for e, s in actual),
        detail=_problems_detail(problems),
    )


def _check_quarantine_reasons(
    quarantined: list[QuarantineItem], golden_expected: set[tuple[str, str]] | None
) -> CheckResult:
    def acceptable(item: QuarantineItem) -> bool:
        if golden_expected is not None and (item.entity.value, item.source_id) in golden_expected:
            return True
        return is_data_reason(item.reason)

    # expected = the acceptable items, actual = every quarantined item: the report hash (over the
    # checks) then covers the full quarantine list, which the SUCCESS/PARTIAL_SUCCESS split depends on.
    keys = sorted({f"{q.entity.value}:{q.source_id}" for q in quarantined})
    rejected = sorted({f"{q.entity.value}:{q.source_id}" for q in quarantined if not acceptable(q)})
    return CheckResult(
        name="quarantine_reasons",
        passed=not rejected,
        expected=[key for key in keys if key not in rejected],
        actual=keys,
        detail=f"quarantined without a DATA-type reason: {_preview(rejected)}" if rejected else "",
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def report_hash(checks: list[CheckResult]) -> str:
    """sha256 of the canonical JSON (sorted keys, compact separators) of the checks."""
    payload = json.dumps(
        [c.model_dump(mode="json") for c in checks], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decide_status(checks: list[CheckResult], quarantined: list[QuarantineItem]) -> RunStatus:
    if not all(c.passed for c in checks):
        return RunStatus.FAILED
    return RunStatus.PARTIAL_SUCCESS if quarantined else RunStatus.SUCCESS


def _entity_checks(d: _EntityData, snapshot: _Snapshot, contract: PreservationContract) -> list[CheckResult]:
    checks = [_check_count(d), _check_duplicates(d), _check_missing(d), _check_unexpected(d)]
    if d.entity is Entity.customers:
        checks.append(_check_unique_emails(d))
    checks.append(_check_source_fidelity(d))
    if contract.referential_integrity and d.entity is not Entity.customers:
        cust_ids = {r.get("id") for r in snapshot.target[Entity.customers] if isinstance(r.get("id"), str)}
        if d.entity is Entity.subscriptions:
            checks.append(_check_subscription_refs(d, cust_ids, snapshot.prices))
        else:
            checks.append(_check_invoice_refs(d, cust_ids, snapshot.target[Entity.subscriptions]))
    return checks


def _golden_checks(
    contract: PreservationContract,
    data: dict[Entity, _EntityData],
    quarantined: list[QuarantineItem],
) -> tuple[list[CheckResult], set[tuple[str, str]] | None]:
    if contract.golden_path is None:
        return [], None
    try:
        golden = _load_golden(contract.golden_path)
    except (OSError, ValueError) as exc:
        return [CheckResult(name="golden_load", passed=False, detail=f"{type(exc).__name__}: {exc}")], None
    checks = [_check_golden_records(d, list(golden.get(e.value) or [])) for e, d in data.items()]
    expected_items = list(golden.get("expected_quarantine") or [])
    checks.append(_check_golden_quarantine(expected_items, quarantined, list(data)))
    expected_keys = {(str(i.get("entity")), str(i.get("source_id"))) for i in expected_items}
    return checks, expected_keys


def _reconcile(
    run_id: str, snapshot: _Snapshot, contract: PreservationContract, quarantined: list[QuarantineItem]
) -> ReconciliationReport:
    entities = [e for e in ENTITY_ORDER if e in contract.entities]
    ctx = _source_context(snapshot.account, snapshot.prices)
    views = _build_views(snapshot)
    q_ids: dict[Entity, set[str]] = defaultdict(set)
    for item in quarantined:
        q_ids[item.entity].add(item.source_id)
    data = {e: _entity_data(e, snapshot, ctx, contract, q_ids[e], views[e]) for e in entities}

    checks: list[CheckResult] = []
    for d in data.values():
        checks.extend(_entity_checks(d, snapshot, contract))
    money_source: dict[str, int] = {}
    money_target: dict[str, int] = {}
    if Entity.invoices in data:
        money_source, money_expected, money_target, problems = _money(
            data[Entity.invoices], snapshot.target[Entity.invoices]
        )
        if contract.money_by_currency:
            checks.append(_check_money(money_expected, money_target, problems))
    golden_checks, golden_expected = _golden_checks(contract, data, quarantined)
    checks.extend(golden_checks)
    checks.append(_check_quarantine_reasons(quarantined, golden_expected))

    return ReconciliationReport(
        run_id=run_id,
        status=_decide_status(checks, quarantined),
        checks=checks,
        quarantined=list(quarantined),
        source_counts={e.value: len(d.source_ids) for e, d in data.items()},
        target_counts={e.value: len(d.target) for e, d in data.items()},
        money_source_minor=money_source,
        money_target_minor=money_target,
        report_hash=report_hash(checks),
    )


def _read_failure_report(
    run_id: str, quarantined: list[QuarantineItem], exc: Exception
) -> ReconciliationReport:
    checks = [CheckResult(name="read_data", passed=False, detail=f"{type(exc).__name__}: {_short(str(exc))}")]
    return ReconciliationReport(
        run_id=run_id,
        status=RunStatus.FAILED,
        checks=checks,
        quarantined=list(quarantined),
        report_hash=report_hash(checks),
    )


def verify(
    run_id: str,
    source: SourceLike,
    target: TargetLike,
    contract: PreservationContract,
    quarantined: list[QuarantineItem],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> ReconciliationReport:
    """Read source and target fresh and decide SUCCESS / PARTIAL_SUCCESS / FAILED.

    Transient read errors (429, 5xx, timeouts, connection failures) are retried up to
    `attempts` times; a read that still fails yields a FAILED report with a `read_data` check.
    """
    with telemetry.trace("verifier.verify", kind="EVALUATOR") as span_obj:
        telemetry.set_attr(span_obj, "zerodrop.run_id", run_id)
        entities = [e for e in ENTITY_ORDER if e in contract.entities]
        try:
            snapshot = _fetch(source, target, entities, max(1, attempts), sleep)
        except Exception as exc:
            report = _read_failure_report(run_id, quarantined, exc)
        else:
            report = _reconcile(run_id, snapshot, contract, quarantined)
        failed = [f"{c.name}:{c.entity.value if c.entity else '*'}" for c in report.checks if not c.passed]
        telemetry.set_attr(span_obj, "zerodrop.verify.status", report.status.value)
        telemetry.set_attr(span_obj, "zerodrop.verify.report_hash", report.report_hash)
        telemetry.set_attr(span_obj, "zerodrop.verify.failed_checks", ",".join(failed))
    return report
