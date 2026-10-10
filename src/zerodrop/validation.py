"""Payload validation against NovaBill entity schemas, and schema-version diffs.

Error strings use the same shape as the DSL: ``"<field>: <code>: <detail>"``, with
codes chosen to match NovaBill's 422 codes where possible (`unknown_field`,
`missing_field`, `invalid_value`, `not_lowercase`) so a dry run predicts what the
target will say.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
from jsonschema.exceptions import SchemaError

ROOT = "<payload>"
_SHOW_LIMIT = 60
_JSON_TYPES = {
    dict: "object",
    list: "array",
    str: "string",
    bool: "boolean",
    int: "integer",
    float: "number",
    type(None): "null",
}


def validate_payload(schema: dict[str, Any], payload: Any) -> list[str]:
    """Validate a payload against one entity's JSON Schema (Draft 2020-12).

    Returns sorted, de-duplicated messages naming the field; empty when valid.
    An invalid schema yields a single ``invalid_schema`` message instead of raising.
    """
    try:
        validator = _validator(_canonical(schema))
    except (SchemaError, TypeError, ValueError) as exc:
        message = exc.message if isinstance(exc, SchemaError) else str(exc)
        return [f"<schema>: invalid_schema: {_clip(message)}"]
    messages: list[str] = []
    for error in validator.iter_errors(payload):
        messages.extend(_describe(error))
    return sorted(set(messages))


def entity_schema(schema_doc: dict[str, Any], entity: str) -> dict[str, Any]:
    """The JSON Schema for `entity` from a NovaBill ``GET /api/schema`` document."""
    entities = schema_doc.get("entities") or {}
    if entity not in entities:
        raise KeyError(entity)
    return entities[entity]


def schema_diff(old_schema_doc: dict[str, Any], new_schema_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per-entity field differences between two ``GET /api/schema`` documents.

    Each entity maps to ``{"added_fields", "removed_fields", "changed_fields"}``
    (sorted field-name lists) plus ``"details"``: for every changed field, the old
    and new property schema and whether it is required in each version.
    """
    old_entities = _entities(old_schema_doc)
    new_entities = _entities(new_schema_doc)
    names = list(dict.fromkeys([*old_entities, *new_entities]))
    return {name: _entity_diff(old_entities.get(name, {}), new_entities.get(name, {})) for name in names}


# ---------------------------------------------------------------------------
# Validation internals
# ---------------------------------------------------------------------------


def _canonical(schema: dict[str, Any]) -> str:
    if not isinstance(schema, dict):
        raise TypeError(f"schema must be an object, got {type(schema).__name__}")
    return json.dumps(schema, sort_keys=True, separators=(",", ":"))


@lru_cache(maxsize=64)
def _validator(canonical_schema: str) -> Draft202012Validator:
    schema = json.loads(canonical_schema)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _describe(error: ValidationError) -> list[str]:
    path = _path(error)
    kind = error.validator
    if kind == "required":
        return _missing_fields(error, path)
    if kind == "additionalProperties":
        return _unknown_fields(error, path)
    field = path or ROOT
    if kind == "type":
        expected = error.validator_value
        expected_text = " or ".join(expected) if isinstance(expected, list) else str(expected)
        return [f"{field}: invalid_value: expected {expected_text}, got {_json_type(error.instance)}"]
    if kind == "pattern":
        code = (
            "not_lowercase"
            if _only_case_differs(error.instance, str(error.validator_value))
            else "invalid_value"
        )
        return [f"{field}: {code}: {_show(error.instance)} does not match pattern {error.validator_value}"]
    if kind == "enum":
        allowed = ", ".join(repr(v) for v in error.validator_value)
        return [f"{field}: invalid_value: {_show(error.instance)} is not one of [{allowed}]"]
    if kind == "const":
        return [f"{field}: invalid_value: {_show(error.instance)} must equal {error.validator_value!r}"]
    if kind in {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"}:
        return [f"{field}: invalid_value: {_show(error.instance)} violates {kind} {error.validator_value}"]
    return [f"{field}: invalid_value: {_clip(error.message)}"]


def _missing_fields(error: ValidationError, path: str) -> list[str]:
    instance = error.instance if isinstance(error.instance, dict) else {}
    required = error.validator_value if isinstance(error.validator_value, list) else []
    return [
        f"{_join(path, name)}: missing_field: required field is missing"
        for name in required
        if name not in instance
    ]


def _unknown_fields(error: ValidationError, path: str) -> list[str]:
    instance = error.instance if isinstance(error.instance, dict) else {}
    properties = error.schema.get("properties", {}) if isinstance(error.schema, dict) else {}
    patterns = error.schema.get("patternProperties", {}) if isinstance(error.schema, dict) else {}
    extras = [
        key for key in instance if key not in properties and not any(_safe_search(p, key) for p in patterns)
    ]
    return [f"{_join(path, key)}: unknown_field: field is not allowed by the target schema" for key in extras]


def _only_case_differs(value: Any, pattern: str) -> bool:
    return isinstance(value, str) and _safe_search(pattern, value.lower())


def _safe_search(pattern: str, text: str) -> bool:
    try:
        return re.search(pattern, text) is not None
    except (re.error, TypeError):
        return False


def _path(error: ValidationError) -> str:
    return ".".join(str(part) for part in error.absolute_path)


def _join(path: str, name: str) -> str:
    return f"{path}.{name}" if path else name


def _json_type(value: Any) -> str:
    return _JSON_TYPES.get(type(value), type(value).__name__)


def _show(value: Any) -> str:
    return _clip(repr(value))


def _clip(text: str) -> str:
    return text if len(text) <= _SHOW_LIMIT else text[: _SHOW_LIMIT - 3] + "..."


# ---------------------------------------------------------------------------
# Schema diff internals
# ---------------------------------------------------------------------------


def _entities(schema_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entities = schema_doc.get("entities") if isinstance(schema_doc, dict) else None
    return entities if isinstance(entities, dict) else {}


def _entity_diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_props: dict[str, Any] = old.get("properties") or {}
    new_props: dict[str, Any] = new.get("properties") or {}
    old_required = set(old.get("required") or [])
    new_required = set(new.get("required") or [])
    added = sorted(set(new_props) - set(old_props))
    removed = sorted(set(old_props) - set(new_props))
    changed = sorted(
        name
        for name in set(old_props) & set(new_props)
        if _canonical_any(old_props[name]) != _canonical_any(new_props[name])
        or (name in old_required) != (name in new_required)
    )
    details = {
        name: {
            "old": old_props[name],
            "new": new_props[name],
            "old_required": name in old_required,
            "new_required": name in new_required,
        }
        for name in changed
    }
    return {"added_fields": added, "removed_fields": removed, "changed_fields": changed, "details": details}


def _canonical_any(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
