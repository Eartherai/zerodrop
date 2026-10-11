"""Deterministic executor for the mapping DSL (`MappingSpec`, see models.py).

The LLM writes mappings; this module runs them. It never executes code from a
spec and never raises on bad source data: every problem becomes an error string
of the form ``"<target field>: <code>: <detail>"`` (see `error_code`).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from zerodrop.models import Condition, FieldMapping, MappingSpec, TransformOp

# Error codes (second segment of every error string).
ERR_REQUIRED = "required_null"
ERR_UNRESOLVED = "unresolved_reference"
ERR_LOOKUP_MISS = "lookup_miss"
ERR_UNMAPPED = "unmapped_value"
ERR_INVALID_TYPE = "invalid_type"
ERR_PARSE = "parse_error"
ERR_NON_INTEGRAL = "non_integral"
ERR_OUT_OF_RANGE = "out_of_range"
ERR_MISSING_PARAM = "missing_param"
ERR_INVALID_PARAM = "invalid_param"
ERR_DUPLICATE_TARGET = "duplicate_target"
ERR_INVALID_RECORD = "invalid_record"
ERR_OP = "op_error"

# ISO-4217 currencies whose minor unit is not 2 (everything else defaults to 2).
CURRENCY_MINOR_UNITS: dict[str, int] = {
    **dict.fromkeys(("JPY", "KRW", "VND", "CLP", "ISK", "UGX", "XAF", "XOF"), 0),
    **dict.fromkeys(("BHD", "KWD", "OMR", "JOD", "TND", "IQD", "LYD"), 3),
}
DEFAULT_MINOR_UNITS = 2

# Amounts beyond this many digits (in minor units) are rejected instead of computed.
_MAX_MINOR_DIGITS = 40
_INT_RE = re.compile(r"[+-]?[0-9]+")
# Plain ASCII decimal notation (optional exponent). Stricter than Decimal(), which also
# accepts digit-group underscores ("1_000") and non-ASCII digits.
_DECIMAL_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_SHOW_LIMIT = 60


class MappingContext(Protocol):
    """What the executor needs from the engine: the id map and target reference tables."""

    def id_map(self, entity: str, source_id: str) -> str | None: ...

    def lookup(self, table: str, match_field: str, value: Any, return_field: str) -> Any | None: ...


class _OpError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_mapping(
    spec: MappingSpec, record: Mapping[str, Any], ctx: MappingContext
) -> tuple[dict[str, Any] | None, list[str]]:
    """Map one source record to a target payload.

    Returns ``(payload, [])`` on success, or ``(None, errors)`` with one error per
    failing field. Never raises on bad data or a misbehaving context.
    """
    if not isinstance(record, Mapping):
        return None, [f"<record>: {ERR_INVALID_RECORD}: expected an object, got {type(record).__name__}"]
    payload: dict[str, Any] = {}
    errors: list[str] = []
    seen: set[str] = set()
    for fm in spec.fields:
        if fm.target in seen:
            errors.append(f"{fm.target}: {ERR_DUPLICATE_TARGET}: target field is mapped more than once")
            continue
        seen.add(fm.target)
        try:
            value = _map_field(fm, record, ctx)
        except _OpError as exc:
            errors.append(f"{fm.target}: {exc.code}: {exc.detail}")
            continue
        except Exception as exc:  # defensive: apply_mapping must never raise
            errors.append(f"{fm.target}: {ERR_OP}: {type(exc).__name__}: {_clip(str(exc))}")
            continue
        if value is None and fm.required:
            errors.append(f"{fm.target}: {ERR_REQUIRED}: {_null_reason(fm, record)}")
            continue
        payload[fm.target] = value
    if errors:
        return None, errors
    return payload, []


def matches_exclusion(spec: MappingSpec, record: Mapping[str, Any]) -> bool:
    """True when the record matches any `exclude_if` condition (the record is skipped)."""
    if not isinstance(record, Mapping):
        return False
    return any(_condition_matches(cond, record) for cond in spec.exclude_if)


def mapping_hash(spec: MappingSpec) -> str:
    """Stable sha256 (hex) of the spec's canonical JSON (sorted keys, no whitespace)."""
    canonical = json.dumps(
        spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def error_code(error: str) -> str | None:
    """Extract the code from an error string ``"<field>: <code>: <detail>"``."""
    parts = error.split(": ", 2)
    return parts[1] if len(parts) >= 2 else None


def error_field(error: str) -> str | None:
    """Extract the target field from an error string ``"<field>: <code>: <detail>"``."""
    parts = error.split(": ", 2)
    return parts[0] if len(parts) >= 2 else None


def minor_units(currency: str) -> int:
    """ISO-4217 minor units for a currency code (case-insensitive; unknown codes -> 2)."""
    return CURRENCY_MINOR_UNITS.get(currency.strip().upper(), DEFAULT_MINOR_UNITS)


# ---------------------------------------------------------------------------
# Field evaluation
# ---------------------------------------------------------------------------


def _map_field(fm: FieldMapping, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    value = record.get(fm.source) if fm.source is not None else None
    for op in fm.ops:
        if value is None and op.op != "const":
            continue  # a None input short-circuits every op except const
        handler = _OPS[op.op]
        try:
            value = handler(value, op, record, ctx)
        except _OpError:
            raise
        except Exception as exc:
            raise _OpError(ERR_OP, f"{op.op}: {type(exc).__name__}: {_clip(str(exc))}") from exc
    return value


def _null_reason(fm: FieldMapping, record: Mapping[str, Any]) -> str:
    if fm.source is not None and fm.source not in record:
        return f"required field resolved to null (source field {fm.source!r} is missing)"
    if fm.source is not None and record.get(fm.source) is None:
        return f"required field resolved to null (source field {fm.source!r} is null)"
    return "required field resolved to null"


# ---------------------------------------------------------------------------
# Ops: each takes (value, op, record, ctx) with a non-None value (except const)
# ---------------------------------------------------------------------------

OpHandler = Callable[[Any, TransformOp, Mapping[str, Any], MappingContext], Any]


def _op_lower(value: Any, op: TransformOp, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    return _require_str(value, op).lower()


def _op_upper(value: Any, op: TransformOp, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    return _require_str(value, op).upper()


def _op_strip(value: Any, op: TransformOp, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    return _require_str(value, op).strip()


def _op_split_name(value: Any, op: TransformOp, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    text = _require_str(value, op)
    if op.part is None:
        raise _OpError(ERR_MISSING_PARAM, "split_name needs 'part' ('first' or 'last')")
    tokens = text.split()
    if op.part == "first":
        return tokens[0] if tokens else None
    rest = tokens[1:]
    return " ".join(rest) if rest else None


def _op_parse_datetime(value: Any, op: TransformOp, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    text = _require_str(value, op).strip()
    tz = _zone(op.assume_tz)
    parsed = _parse_with_formats(text, op.formats)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)  # date-only formats parse as local midnight
    try:
        utc = parsed.astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        raise _OpError(ERR_OUT_OF_RANGE, f"parse_datetime: {_show(value)} is out of range in UTC") from exc
    return f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}T{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}Z"


def _op_decimal_to_minor(value: Any, op: TransformOp, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    decimals = _decimals_for(op, record)
    amount = _to_decimal(value)
    return _scale_exact(amount, decimals, value)


def _op_to_int(value: Any, op: TransformOp, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    if isinstance(value, bool):
        raise _OpError(ERR_INVALID_TYPE, f"to_int: expected an integer string, got bool {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise _OpError(ERR_PARSE, f"to_int: {_show(value)} is not an integer")
    if isinstance(value, str):
        text = value.strip()
        if _INT_RE.fullmatch(text):
            return int(text)
        raise _OpError(ERR_PARSE, f"to_int: {_show(value)} is not an integer")
    raise _OpError(ERR_INVALID_TYPE, f"to_int: expected an integer string, got {type(value).__name__}")


def _op_enum_map(value: Any, op: TransformOp, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    key = value if isinstance(value, str) else str(value)
    pairs = op.mapping or []
    for pair in pairs:
        if pair.source == key:
            return pair.target
    if op.default is not None:
        return op.default
    known = ", ".join(repr(p.source) for p in pairs) or "none"
    raise _OpError(ERR_UNMAPPED, f"enum_map: no mapping for {_show(value)} (known: {known})")


def _op_ref(value: Any, op: TransformOp, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    if op.entity is None:
        raise _OpError(ERR_MISSING_PARAM, "ref needs 'entity'")
    if _is_empty(value):
        return None
    source_id = value.strip() if isinstance(value, str) else str(value)
    target_id = ctx.id_map(op.entity, source_id)
    if target_id is None:
        raise _OpError(ERR_UNRESOLVED, f"ref: {op.entity.value} {source_id!r} has no migrated target id")
    return target_id


def _op_lookup(value: Any, op: TransformOp, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    table, match_field, return_field = op.table, op.match_field, op.return_field
    if table is None or match_field is None or return_field is None:
        missing = [n for n in ("table", "match_field", "return_field") if getattr(op, n) is None]
        raise _OpError(ERR_MISSING_PARAM, f"lookup needs {', '.join(repr(m) for m in missing)}")
    if _is_empty(value):
        return None
    result = ctx.lookup(table, match_field, value, return_field)
    if result is None:
        raise _OpError(ERR_LOOKUP_MISS, f"lookup: no row in {table!r} with {match_field} == {_show(value)}")
    return result


def _op_bool_map(value: Any, op: TransformOp, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    if op.true_values is None:
        raise _OpError(ERR_MISSING_PARAM, "bool_map needs 'true_values'")
    return str(value) in op.true_values


def _op_const(value: Any, op: TransformOp, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    return op.value


def _op_null_if_empty(value: Any, op: TransformOp, record: Mapping[str, Any], ctx: MappingContext) -> Any:
    return None if value == "" else value


_OPS: dict[str, OpHandler] = {
    "lower": _op_lower,
    "upper": _op_upper,
    "strip": _op_strip,
    "split_name": _op_split_name,
    "parse_datetime": _op_parse_datetime,
    "decimal_to_minor": _op_decimal_to_minor,
    "to_int": _op_to_int,
    "enum_map": _op_enum_map,
    "ref": _op_ref,
    "lookup": _op_lookup,
    "bool_map": _op_bool_map,
    "const": _op_const,
    "null_if_empty": _op_null_if_empty,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_str(value: Any, op: TransformOp) -> str:
    if not isinstance(value, str):
        raise _OpError(ERR_INVALID_TYPE, f"{op.op}: expected a string, got {type(value).__name__}")
    return value


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _zone(name: str | None) -> ZoneInfo:
    if name is None:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except Exception as exc:  # ZoneInfoNotFoundError, ValueError for malformed keys
        raise _OpError(ERR_INVALID_PARAM, f"parse_datetime: unknown timezone {name!r}") from exc


def _parse_with_formats(text: str, formats: list[str] | None) -> datetime:
    """Try each strptime format in order; with no formats, accept ISO-8601."""
    if not formats:
        try:
            return datetime.fromisoformat(text)
        except ValueError as exc:
            raise _OpError(ERR_PARSE, f"parse_datetime: {_show(text)} is not ISO-8601") from exc
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except (ValueError, TypeError):
            continue
    raise _OpError(ERR_PARSE, f"parse_datetime: {_show(text)} matches none of the formats {formats}")


def _decimals_for(op: TransformOp, record: Mapping[str, Any]) -> int:
    if op.decimals is not None:
        if op.decimals < 0:
            raise _OpError(ERR_INVALID_PARAM, f"decimal_to_minor: decimals must be >= 0, got {op.decimals}")
        code = record.get(op.currency_field) if op.currency_field is not None else None
        if isinstance(code, str) and code.strip() and minor_units(code) != op.decimals:
            # Both parameters given and they disagree for this record: never pick one silently.
            raise _OpError(
                ERR_INVALID_PARAM,
                f"decimal_to_minor: decimals={op.decimals} contradicts currency {code.strip().upper()!r}, which "
                f"has {minor_units(code)} minor-unit digits; give only 'currency_field' for mixed currencies",
            )
        return op.decimals
    if op.currency_field is None:
        raise _OpError(ERR_MISSING_PARAM, "decimal_to_minor needs 'decimals' or 'currency_field'")
    code = record.get(op.currency_field)
    if not isinstance(code, str) or not code.strip():
        raise _OpError(
            ERR_MISSING_PARAM,
            f"decimal_to_minor: currency field {op.currency_field!r} is empty or not a string",
        )
    return minor_units(code)


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise _OpError(ERR_INVALID_TYPE, f"decimal_to_minor: expected a decimal string, got bool {value!r}")
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int | str | float):
        # Floats are parsed from their shortest repr; no float arithmetic happens.
        text = value.strip() if isinstance(value, str) else str(value)
        if isinstance(value, str) and not _DECIMAL_RE.fullmatch(text):
            raise _OpError(ERR_PARSE, f"decimal_to_minor: {_show(value)} is not a decimal number")
        try:
            amount = Decimal(text)
        except InvalidOperation as exc:
            raise _OpError(ERR_PARSE, f"decimal_to_minor: {_show(value)} is not a decimal number") from exc
    else:
        raise _OpError(
            ERR_INVALID_TYPE, f"decimal_to_minor: expected a decimal string, got {type(value).__name__}"
        )
    if not amount.is_finite():
        raise _OpError(ERR_PARSE, f"decimal_to_minor: {_show(value)} is not a finite number")
    return amount


def _scale_exact(amount: Decimal, decimals: int, original: Any) -> int:
    """amount * 10**decimals as an exact int, using only integer arithmetic."""
    sign, digits, exponent = amount.as_tuple()
    assert isinstance(exponent, int)  # finite amounts only
    coefficient = int("".join(map(str, digits))) if digits else 0
    if coefficient == 0:
        return 0
    shift = exponent + decimals
    if shift >= 0:
        if len(digits) + shift > _MAX_MINOR_DIGITS:
            raise _OpError(ERR_OUT_OF_RANGE, f"decimal_to_minor: {_show(original)} is too large")
        scaled = coefficient * 10**shift
    else:
        if -shift > len(digits):
            raise _non_integral(original, decimals)
        scaled, remainder = divmod(coefficient, 10**-shift)
        if remainder:
            raise _non_integral(original, decimals)
        if len(str(scaled)) > _MAX_MINOR_DIGITS:
            raise _OpError(ERR_OUT_OF_RANGE, f"decimal_to_minor: {_show(original)} is too large")
    return -scaled if sign else scaled


def _non_integral(original: Any, decimals: int) -> _OpError:
    return _OpError(
        ERR_NON_INTEGRAL,
        f"decimal_to_minor: {_show(original)} is not a whole number of minor units ({decimals} decimals)",
    )


def _condition_matches(cond: Condition, record: Mapping[str, Any]) -> bool:
    return _loose_equal(record.get(cond.field), cond.equals)


def _loose_equal(actual: Any, expected: Any) -> bool:
    """Equality for exclusion rules.

    Same-kind values compare exactly (bools never equal ints). A string compared
    with a bool or int matches case-insensitively on its text form, so a source
    value "true" matches ``equals: true`` and "1" matches ``equals: 1``.
    """
    if actual is None or expected is None:
        return actual is None and expected is None
    if isinstance(actual, bool) or isinstance(expected, bool):
        if isinstance(actual, bool) and isinstance(expected, bool):
            return actual == expected
        other, flag = (actual, expected) if isinstance(expected, bool) else (expected, actual)
        return isinstance(other, str) and other.strip().lower() == str(flag).lower()
    if isinstance(actual, str) != isinstance(expected, str):
        return str(actual).strip() == str(expected).strip()
    return bool(actual == expected)


def _show(value: Any) -> str:
    return _clip(repr(value))


def _clip(text: str) -> str:
    return text if len(text) <= _SHOW_LIMIT else text[: _SHOW_LIMIT - 3] + "..."
