from __future__ import annotations

import copy
from typing import Any

import pytest

from zerodrop.validation import entity_schema, schema_diff, validate_payload

ISO = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


CUSTOMERS = _obj(
    {
        "external_id": {"type": "string", "minLength": 1},
        "given_name": {"type": "string", "minLength": 1},
        "family_name": {"type": "string", "minLength": 1},
        "email": {"type": "string", "pattern": "^[^A-Z]+@[^A-Z]+$"},
        "country": {"type": "string", "pattern": "^[A-Z]{2}$"},
        "status": {"type": "string", "enum": ["active", "suspended", "closed"]},
        "created_at": {"type": "string", "pattern": ISO},
        "notes": {"type": ["string", "null"]},
    }
)
SUB_COMMON = {
    "external_id": {"type": "string"},
    "customer_id": {"type": "string"},
    "status": {"type": "string", "enum": ["active", "delinquent", "canceled", "trialing"]},
    "start_at": {"type": "string", "pattern": ISO},
    "quantity": {"type": "integer", "minimum": 1},
}
INVOICES_V1 = _obj(
    {
        "external_id": {"type": "string"},
        "customer_id": {"type": "string"},
        "subscription_id": {"type": ["string", "null"]},
        "amount_minor": {"type": "integer", "minimum": 0},
        "currency": {"type": "string", "pattern": "^[A-Za-z]{3}$"},
        "issued_at": {"type": "string", "pattern": ISO},
        "status": {"type": "string", "enum": ["paid", "open"]},
    }
)
INVOICES_V2 = copy.deepcopy(INVOICES_V1)
INVOICES_V2["properties"]["currency"]["pattern"] = "^[a-z]{3}$"

SCHEMA_V1 = {
    "version": "v1",
    "entities": {
        "customers": CUSTOMERS,
        "subscriptions": _obj({**SUB_COMMON, "plan_code": {"type": "string"}}),
        "invoices": INVOICES_V1,
    },
    "reference_tables": {"prices": "/api/prices"},
}
SCHEMA_V2 = {
    "version": "v2",
    "entities": {
        "customers": copy.deepcopy(CUSTOMERS),
        "subscriptions": _obj({**SUB_COMMON, "price_id": {"type": "string"}}),
        "invoices": INVOICES_V2,
    },
    "reference_tables": {"prices": "/api/prices"},
}

GOOD_CUSTOMER = {
    "external_id": "C000123",
    "given_name": "Asha",
    "family_name": "Rao",
    "email": "asha.rao@example.com",
    "country": "IN",
    "status": "active",
    "created_at": "2021-03-14T18:30:00Z",
    "notes": None,
}
GOOD_SUB_V1 = {
    "external_id": "S000001",
    "customer_id": "cus_1",
    "plan_code": "PRO_M",
    "status": "active",
    "start_at": "2023-01-05T04:52:00Z",
    "quantity": 3,
}
GOOD_INVOICE = {
    "external_id": "I000001",
    "customer_id": "cus_1",
    "subscription_id": None,
    "amount_minor": 12900,
    "currency": "usd",
    "issued_at": "2024-02-01T00:00:00Z",
    "status": "paid",
}


def subs(doc: dict[str, Any]) -> dict[str, Any]:
    return entity_schema(doc, "subscriptions")


def test_valid_payloads_have_no_errors() -> None:
    assert validate_payload(CUSTOMERS, GOOD_CUSTOMER) == []
    assert validate_payload(subs(SCHEMA_V1), GOOD_SUB_V1) == []
    assert validate_payload(INVOICES_V2, GOOD_INVOICE) == []


def test_v1_payload_against_v2_schema_names_both_fields() -> None:
    errors = validate_payload(subs(SCHEMA_V2), GOOD_SUB_V1)
    assert errors == [
        "plan_code: unknown_field: field is not allowed by the target schema",
        "price_id: missing_field: required field is missing",
    ]


def test_every_missing_field_is_listed_once() -> None:
    errors = validate_payload(CUSTOMERS, {"external_id": "C1"})
    missing = [e.split(":")[0] for e in errors]
    assert missing == sorted(set(CUSTOMERS["required"]) - {"external_id"})
    assert all(": missing_field: " in e for e in errors)


def test_multiple_unknown_fields() -> None:
    errors = validate_payload(CUSTOMERS, {**GOOD_CUSTOMER, "zeta": 1, "alpha": 2})
    assert errors == [
        "alpha: unknown_field: field is not allowed by the target schema",
        "zeta: unknown_field: field is not allowed by the target schema",
    ]


def test_uppercase_currency_on_v2_is_not_lowercase() -> None:
    errors = validate_payload(INVOICES_V2, {**GOOD_INVOICE, "currency": "USD"})
    assert errors == ["currency: not_lowercase: 'USD' does not match pattern ^[a-z]{3}$"]
    assert validate_payload(INVOICES_V1, {**GOOD_INVOICE, "currency": "USD"}) == []


def test_bad_currency_is_invalid_value_not_case() -> None:
    errors = validate_payload(INVOICES_V2, {**GOOD_INVOICE, "currency": "us"})
    assert errors == ["currency: invalid_value: 'us' does not match pattern ^[a-z]{3}$"]


def test_mixed_case_email_is_not_lowercase() -> None:
    errors = validate_payload(CUSTOMERS, {**GOOD_CUSTOMER, "email": "Asha.Rao@Example.com"})
    assert errors == ["email: not_lowercase: 'Asha.Rao@Example.com' does not match pattern ^[^A-Z]+@[^A-Z]+$"]


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"quantity": "3"}, "quantity: invalid_value: expected integer, got string"),
        ({"quantity": 0}, "quantity: invalid_value: 0 violates minimum 1"),
        ({"quantity": True}, "quantity: invalid_value: expected integer, got boolean"),
        (
            {"status": "live"},
            "status: invalid_value: 'live' is not one of ['active', 'delinquent', 'canceled', 'trialing']",
        ),
        (
            {"start_at": "2023-01-05 10:22:00"},
            "start_at: invalid_value: '2023-01-05 10:22:00' does not match pattern " + ISO,
        ),
    ],
)
def test_value_errors_name_the_field(change: dict[str, Any], expected: str) -> None:
    assert validate_payload(subs(SCHEMA_V1), {**GOOD_SUB_V1, **change}) == [expected]


def test_union_type_message() -> None:
    errors = validate_payload(CUSTOMERS, {**GOOD_CUSTOMER, "notes": 5})
    assert errors == ["notes: invalid_value: expected string or null, got integer"]


def test_min_length_and_long_values_are_clipped() -> None:
    errors = validate_payload(CUSTOMERS, {**GOOD_CUSTOMER, "given_name": ""})
    assert len(errors) == 1 and errors[0].startswith("given_name: invalid_value: ")
    errors = validate_payload(CUSTOMERS, {**GOOD_CUSTOMER, "country": "X" * 500})
    assert len(errors) == 1 and errors[0].startswith("country: invalid_value: ") and len(errors[0]) < 200


def test_nested_paths_are_dotted() -> None:
    schema = {
        "type": "object",
        "properties": {"address": _obj({"city": {"type": "string"}})},
    }
    assert validate_payload(schema, {"address": {"city": 3}}) == [
        "address.city: invalid_value: expected string, got integer"
    ]
    assert validate_payload(schema, {"address": {}}) == [
        "address.city: missing_field: required field is missing"
    ]


def test_non_object_payload() -> None:
    assert validate_payload(CUSTOMERS, ["x"]) == ["<payload>: invalid_value: expected object, got array"]


def test_invalid_schema_is_reported_not_raised() -> None:
    errors = validate_payload({"type": "nonsense"}, {})
    assert len(errors) == 1 and errors[0].startswith("<schema>: invalid_schema: ")
    assert validate_payload("not a schema", {})[0].startswith("<schema>: invalid_schema: ")  # type: ignore[arg-type]


def test_messages_are_sorted_and_deterministic() -> None:
    payload = {"quantity": "x", "bogus": 1}
    first = validate_payload(subs(SCHEMA_V2), payload)
    assert first == sorted(first)
    assert validate_payload(subs(SCHEMA_V2), payload) == first


def test_entity_schema_lookup() -> None:
    assert entity_schema(SCHEMA_V1, "customers") is CUSTOMERS
    with pytest.raises(KeyError):
        entity_schema(SCHEMA_V1, "refunds")


# ---------------------------------------------------------------------------
# schema_diff
# ---------------------------------------------------------------------------


def test_schema_diff_v1_to_v2() -> None:
    diff = schema_diff(SCHEMA_V1, SCHEMA_V2)
    assert list(diff) == ["customers", "subscriptions", "invoices"]
    assert diff["customers"] == {
        "added_fields": [],
        "removed_fields": [],
        "changed_fields": [],
        "details": {},
    }
    assert diff["subscriptions"]["added_fields"] == ["price_id"]
    assert diff["subscriptions"]["removed_fields"] == ["plan_code"]
    assert diff["subscriptions"]["changed_fields"] == []
    invoices = diff["invoices"]
    assert (invoices["added_fields"], invoices["removed_fields"]) == ([], [])
    assert invoices["changed_fields"] == ["currency"]
    detail = invoices["details"]["currency"]
    assert detail["old"]["pattern"] == "^[A-Za-z]{3}$"
    assert detail["new"]["pattern"] == "^[a-z]{3}$"
    assert detail["old_required"] is detail["new_required"] is True


def test_schema_diff_reverse_direction() -> None:
    diff = schema_diff(SCHEMA_V2, SCHEMA_V1)
    assert diff["subscriptions"]["added_fields"] == ["plan_code"]
    assert diff["subscriptions"]["removed_fields"] == ["price_id"]


def test_schema_diff_identical_docs_is_empty() -> None:
    diff = schema_diff(SCHEMA_V1, copy.deepcopy(SCHEMA_V1))
    assert all(
        d == {"added_fields": [], "removed_fields": [], "changed_fields": [], "details": {}}
        for d in diff.values()
    )


def test_schema_diff_required_flag_change_counts_as_change() -> None:
    new = copy.deepcopy(SCHEMA_V1)
    new["entities"]["customers"]["required"].remove("notes")
    diff = schema_diff(SCHEMA_V1, new)
    assert diff["customers"]["changed_fields"] == ["notes"]
    assert diff["customers"]["details"]["notes"]["new_required"] is False


def test_schema_diff_entity_added_or_missing() -> None:
    new = copy.deepcopy(SCHEMA_V1)
    new["entities"]["refunds"] = _obj(
        {"external_id": {"type": "string"}, "amount_minor": {"type": "integer"}}
    )
    del new["entities"]["customers"]
    diff = schema_diff(SCHEMA_V1, new)
    assert diff["refunds"]["added_fields"] == ["amount_minor", "external_id"]
    assert diff["customers"]["removed_fields"] == sorted(CUSTOMERS["properties"])


def test_schema_diff_tolerates_malformed_docs() -> None:
    assert schema_diff({}, {"entities": None}) == {}
    diff = schema_diff({"entities": {"x": {}}}, {"entities": {"x": {"properties": {"a": {}}}}})
    assert diff["x"]["added_fields"] == ["a"]
