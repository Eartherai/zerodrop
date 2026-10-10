from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from zerodrop.sandbox import novabill
from zerodrop.sandbox.fixtures import generate, price_catalog

TOKEN = "nb_live_local_demo_token"
ROTATED = "nb_live_rotated_token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ADMIN = {"X-Admin-Token": "nb_admin_local"}


def make_client(version: str = "v1") -> TestClient:
    return TestClient(novabill.create_app(price_catalog(), initial_version=version))


@pytest.fixture
def client() -> TestClient:
    return make_client()


def customer(n: int = 1, **overrides: Any) -> dict[str, Any]:
    payload = {
        "external_id": f"C{n:06d}",
        "given_name": "Asha",
        "family_name": "Rao",
        "email": f"asha{n}@example.com",
        "country": "IN",
        "status": "active",
        "created_at": "2021-03-14T18:30:00Z",
        "notes": None,
    }
    return payload | overrides


def subscription(customer_id: str, n: int = 1, version: str = "v1", **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "external_id": f"S{n:06d}",
        "customer_id": customer_id,
        "status": "active",
        "start_at": "2023-01-05T04:52:00Z",
        "quantity": 3,
    }
    payload |= {"plan_code": "PRO_M"} if version == "v1" else {"price_id": "price_pro_m"}
    return payload | overrides


def invoice(customer_id: str, n: int = 1, **overrides: Any) -> dict[str, Any]:
    payload = {
        "external_id": f"I{n:06d}",
        "customer_id": customer_id,
        "subscription_id": None,
        "amount_minor": 12900,
        "currency": "usd",
        "issued_at": "2024-02-01T00:00:00Z",
        "status": "paid",
    }
    return payload | overrides


def batch(
    client: TestClient, entity: str, payloads: list[dict], keys: list[str] | None = None, token: str = TOKEN
):
    keys = keys or [f"{entity}:{p.get('external_id')}" for p in payloads]
    items = [{"idempotency_key": k, "payload": p} for k, p in zip(keys, payloads, strict=True)]
    return client.post(
        f"/api/{entity}:batch", json={"items": items}, headers={"Authorization": f"Bearer {token}"}
    )


def one(client: TestClient, entity: str, payload: dict, key: str | None = None) -> dict:
    response = batch(client, entity, [payload], [key] if key else None)
    assert response.status_code == 200, response.text
    return response.json()["results"][0]


def seeded_customer(client: TestClient) -> str:
    result = one(client, "customers", customer(1))
    assert result["status"] == 201
    return result["id"]


# -- discovery -----------------------------------------------------------------


def test_meta_and_version_header_on_every_response(client: TestClient) -> None:
    assert client.get("/api/meta").json() == {"api_version": "v1"}
    for response in (
        client.get("/api/meta"),
        client.get("/api/customers"),  # 401
        client.get("/api/payments", headers=AUTH),  # 404
        client.get("/_admin/stats", headers=ADMIN),
        batch(client, "customers", [customer()]),
    ):
        assert response.headers["NovaBill-Version"] == "v1"


def test_schema_document_shape(client: TestClient) -> None:
    doc = client.get("/api/schema").json()
    assert doc["version"] == "v1"
    assert doc["reference_tables"] == {"prices": "/api/prices"}
    for entity in ("customers", "subscriptions", "invoices"):
        schema = doc["entities"][entity]
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False
    assert "plan_code" in doc["entities"]["subscriptions"]["properties"]


def test_prices_catalog(client: TestClient) -> None:
    items = client.get("/api/prices").json()["items"]
    assert len(items) == 6
    assert {
        "id": "price_pro_m",
        "lookup_key": "PRO_M",
        "currency": "usd",
        "unit_amount_minor": 2900,
        "interval": "month",
    } in items


# -- auth ----------------------------------------------------------------------


def test_auth_required_for_entity_endpoints(client: TestClient) -> None:
    for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}):
        response = client.get("/api/customers", headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_token"
    assert batch(client, "customers", [customer()], token="wrong").status_code == 401


def test_rotated_token_always_accepted(client: TestClient) -> None:
    assert client.get("/api/customers", headers={"Authorization": f"Bearer {ROTATED}"}).status_code == 200
    assert batch(client, "customers", [customer()], token=ROTATED).json()["results"][0]["status"] == 201


# -- writes ----------------------------------------------------------------------


def test_create_lookup_and_ids(client: TestClient) -> None:
    result = one(client, "customers", customer(1))
    assert result == {"index": 0, "status": 201, "id": "cus_000001", "error": None}
    sub = one(client, "subscriptions", subscription("cus_000001"))
    assert sub["id"] == "sub_000001"
    inv = one(client, "invoices", invoice("cus_000001", subscription_id="sub_000001"))
    assert inv["id"] == "inv_000001"
    found = client.get("/api/customers", params={"external_id": "C000001"}, headers=AUTH).json()
    assert found == {"items": [{"id": "cus_000001", **customer(1)}]}
    assert client.get("/api/customers", params={"external_id": "nope"}, headers=AUTH).json() == {"items": []}


def test_optional_nullable_fields_are_stored_as_null(client: TestClient) -> None:
    payload = customer(1)
    del payload["notes"]
    assert one(client, "customers", payload)["status"] == 201
    inv = invoice("cus_000001")
    del inv["subscription_id"]
    assert one(client, "invoices", inv)["status"] == 201
    assert client.get("/_admin/dump/customers", headers=ADMIN).json()["items"][0]["notes"] is None
    assert client.get("/_admin/dump/invoices", headers=ADMIN).json()["items"][0]["subscription_id"] is None


def test_idempotent_replay_returns_200_with_original_id(client: TestClient) -> None:
    first = one(client, "customers", customer(1), key="customers:C000001")
    again = one(client, "customers", customer(1, given_name="Changed"), key="customers:C000001")
    assert first["status"] == 201 and again["status"] == 200
    assert again["id"] == first["id"] and again["error"] is None
    assert client.get("/_admin/stats", headers=ADMIN).json()["records"]["customers"] == 1


def test_idempotency_keys_are_scoped_per_entity(client: TestClient) -> None:
    cus = one(client, "customers", customer(1), key="shared-key")["id"]
    sub = one(client, "subscriptions", subscription(cus), key="shared-key")
    assert sub["status"] == 201 and sub["id"].startswith("sub_")


def test_duplicate_external_id_is_409_with_existing_id(client: TestClient) -> None:
    first = one(client, "customers", customer(1), key="k1")
    conflict = one(client, "customers", customer(1, email="other@example.com"), key="k2")
    assert conflict["status"] == 409
    assert conflict["id"] == first["id"]
    assert conflict["error"]["code"] == "duplicate_external_id"


def test_failed_item_does_not_consume_idempotency_key(client: TestClient) -> None:
    bad = one(client, "customers", customer(1, status="A"), key="k")
    assert bad["status"] == 422
    good = one(client, "customers", customer(1), key="k")
    assert good["status"] == 201


def test_results_follow_item_order_with_mixed_outcomes(client: TestClient) -> None:
    payloads = [customer(1), customer(2, country="in"), customer(3), customer(1)]
    results = batch(client, "customers", payloads, ["a", "b", "c", "d"]).json()["results"]
    assert [r["index"] for r in results] == [0, 1, 2, 3]
    assert [r["status"] for r in results] == [201, 422, 201, 409]
    assert [r["id"] for r in results] == ["cus_000001", None, "cus_000002", "cus_000001"]


# -- validation codes -------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "code", "field"),
    [
        (customer(1, nickname="A"), "unknown_field", "nickname"),
        ({k: v for k, v in customer(1).items() if k != "email"}, "missing_field", "email"),
        (customer(1, status="A"), "invalid_value", "status"),
        (customer(1, country="in"), "invalid_value", "country"),
        (customer(1, created_at="03/15/2021"), "invalid_value", "created_at"),
        (customer(1, created_at="2021-02-30T00:00:00Z"), "invalid_value", "created_at"),
        (customer(1, created_at="2021-03-14T18:30:00+05:30"), "invalid_value", "created_at"),
        (customer(1, notes=5), "invalid_value", "notes"),
        (customer(1, email="Asha.Rao@Example.com"), "not_lowercase", "email"),
        (customer(1, email="not-an-email"), "invalid_value", "email"),
    ],
)
def test_customer_validation_codes(client: TestClient, payload: dict, code: str, field: str) -> None:
    result = one(client, "customers", payload)
    assert result["status"] == 422 and result["id"] is None
    assert (result["error"]["code"], result["error"]["field"]) == (code, field)


def test_unknown_field_reported_before_other_errors(client: TestClient) -> None:
    result = one(client, "customers", {"external_id": "C1", "zzz": 1, "aaa": 2})
    assert (result["error"]["code"], result["error"]["field"]) == ("unknown_field", "aaa")


def test_non_object_payload_is_invalid(client: TestClient) -> None:
    result = one(client, "customers", ["not", "an", "object"], key="k")  # type: ignore[arg-type]
    assert result["status"] == 422 and result["error"]["code"] == "invalid_value"


def test_duplicate_email_case_insensitive(client: TestClient) -> None:
    seeded_customer(client)
    result = one(client, "customers", customer(2, email="asha1@example.com"))
    assert (result["status"], result["error"]["code"]) == (422, "duplicate_email")
    upper = one(client, "customers", customer(3, email="ASHA1@EXAMPLE.COM"))
    assert upper["error"]["code"] == "not_lowercase"  # never stored with upper case, so never matched as new


@pytest.mark.parametrize(
    ("overrides", "code", "field"),
    [
        ({"quantity": 0}, "invalid_value", "quantity"),
        ({"quantity": "3"}, "invalid_value", "quantity"),
        ({"quantity": 2.0}, "invalid_value", "quantity"),
        ({"quantity": True}, "invalid_value", "quantity"),
        ({"status": "live"}, "invalid_value", "status"),
        ({"customer_id": "cus_999999"}, "invalid_reference", "customer_id"),
        ({"customer_id": "C000001"}, "invalid_reference", "customer_id"),
        ({"plan_code": "GOLD_M"}, "invalid_reference", "plan_code"),
        ({"price_id": "price_pro_m"}, "unknown_field", "price_id"),
    ],
)
def test_subscription_validation_codes_v1(client: TestClient, overrides: dict, code: str, field: str) -> None:
    cus = seeded_customer(client)
    result = one(client, "subscriptions", subscription(cus) | overrides)
    assert (result["status"], result["error"]["code"], result["error"]["field"]) == (422, code, field)


@pytest.mark.parametrize(
    ("overrides", "code", "field"),
    [
        ({"amount_minor": -1}, "invalid_value", "amount_minor"),
        ({"amount_minor": "129.00"}, "invalid_value", "amount_minor"),
        ({"currency": "US"}, "invalid_value", "currency"),
        ({"status": "Y"}, "invalid_value", "status"),
        ({"subscription_id": "sub_999999"}, "invalid_reference", "subscription_id"),
        ({"customer_id": "cus_424242"}, "invalid_reference", "customer_id"),
    ],
)
def test_invoice_validation_codes(client: TestClient, overrides: dict, code: str, field: str) -> None:
    cus = seeded_customer(client)
    result = one(client, "invoices", invoice(cus) | overrides)
    assert (result["status"], result["error"]["code"], result["error"]["field"]) == (422, code, field)


def test_invoice_subscription_must_belong_to_customer(client: TestClient) -> None:
    a = seeded_customer(client)
    b = one(client, "customers", customer(2))["id"]
    sub = one(client, "subscriptions", subscription(a))["id"]
    result = one(client, "invoices", invoice(b, subscription_id=sub))
    assert (result["error"]["code"], result["error"]["field"]) == ("invalid_reference", "subscription_id")


# -- versions ----------------------------------------------------------------------


def test_v1_accepts_any_case_currency(client: TestClient) -> None:
    cus = seeded_customer(client)
    assert one(client, "invoices", invoice(cus, 1, currency="USD"))["status"] == 201
    assert one(client, "invoices", invoice(cus, 2, currency="usd"))["status"] == 201


def test_v2_rules() -> None:
    client = make_client("v2")
    assert client.get("/api/meta").json() == {"api_version": "v2"}
    doc = client.get("/api/schema").json()
    sub_schema = doc["entities"]["subscriptions"]
    assert "plan_code" not in sub_schema["properties"] and "price_id" in sub_schema["required"]
    cus = seeded_customer(client)

    with_plan = one(client, "subscriptions", subscription(cus, 1, version="v1"))
    assert (with_plan["error"]["code"], with_plan["error"]["field"]) == ("unknown_field", "plan_code")
    no_price = subscription(cus, 2, version="v2")
    del no_price["price_id"]
    assert one(client, "subscriptions", no_price)["error"]["code"] == "missing_field"
    bad_price = one(client, "subscriptions", subscription(cus, 3, version="v2", price_id="PRO_M"))
    assert (bad_price["error"]["code"], bad_price["error"]["field"]) == ("invalid_reference", "price_id")
    assert one(client, "subscriptions", subscription(cus, 4, version="v2"))["status"] == 201

    upper = one(client, "invoices", invoice(cus, 1, currency="USD"))
    assert (upper["error"]["code"], upper["error"]["field"]) == ("not_lowercase", "currency")
    assert one(client, "invoices", invoice(cus, 2, currency="us1"))["error"]["code"] == "invalid_value"
    assert one(client, "invoices", invoice(cus, 3, currency="usd"))["status"] == 201


def send_all_created(client: TestClient, entity: str, payloads: list[dict], ids: dict[str, str]) -> None:
    """Post payloads in batches of 50, require 201 for each, and record external_id -> NovaBill id."""
    for start in range(0, len(payloads), 50):
        chunk = payloads[start : start + 50]
        results = batch(client, entity, chunk).json()["results"]
        assert all(r["status"] == 201 for r in results), results
        ids.update({p["external_id"]: r["id"] for p, r in zip(chunk, results, strict=True)})


def test_golden_records_are_accepted_in_both_versions() -> None:
    dataset = generate(6, "small", orphan_invoices=1, duplicate_emails=1)
    golden = dataset.golden
    for version in ("v1", "v2"):
        client = TestClient(novabill.create_app(dataset.prices, initial_version=version))
        ids: dict[str, str] = {}
        send_all_created(client, "customers", golden["customers"], ids)
        plan_field = "plan_code" if version == "v1" else "price_id"
        send_all_created(
            client,
            "subscriptions",
            [
                {
                    "external_id": s["external_id"],
                    "customer_id": ids[s["customer_external_id"]],
                    plan_field: s[plan_field],
                    "status": s["status"],
                    "start_at": s["start_at"],
                    "quantity": s["quantity"],
                }
                for s in golden["subscriptions"]
            ],
            ids,
        )
        send_all_created(
            client,
            "invoices",
            [
                {
                    "external_id": i["external_id"],
                    "customer_id": ids[i["customer_external_id"]],
                    "subscription_id": ids[i["subscription_external_id"]]
                    if i["subscription_external_id"]
                    else None,
                    "amount_minor": i["amount_minor"],
                    "currency": i["currency"],
                    "issued_at": i["issued_at"],
                    "status": i["status"],
                }
                for i in golden["invoices"]
            ],
            ids,
        )
        stats = client.get("/_admin/stats", headers=ADMIN).json()
        assert stats["records"] == {e: len(golden[e]) for e in ("customers", "subscriptions", "invoices")}

        dup = next(q for q in golden["expected_quarantine"] if q["entity"] == "customers")
        source_dup = next(c for c in dataset.source["customers"] if c["cust_id"] == dup["source_id"])
        rejected = one(
            client,
            "customers",
            customer(999, external_id=dup["source_id"], email=source_dup["email"].lower()),
        )
        assert rejected["error"]["code"] == "duplicate_email"


# -- listing and admin ------------------------------------------------------------


def test_cursor_listing(client: TestClient) -> None:
    batch(client, "customers", [customer(n) for n in range(1, 8)])
    seen, cursor = [], None
    while True:
        params: dict = {"limit": 3} | ({"cursor": cursor} if cursor else {})
        body = client.get("/api/customers", params=params, headers=AUTH).json()
        seen += [r["id"] for r in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert seen == [f"cus_{n:06d}" for n in range(1, 8)]
    assert client.get("/api/customers", params={"limit": 201}, headers=AUTH).status_code == 422


def test_batch_envelope_errors(client: TestClient) -> None:
    def post(body: Any) -> Any:
        return client.post("/api/customers:batch", json=body, headers=AUTH)

    assert post({"items": []}).status_code == 400
    assert (
        post({"items": [{"idempotency_key": f"k{i}", "payload": customer(i)} for i in range(51)]}).status_code
        == 400
    )
    assert post({"items": [{"payload": customer(1)}]}).status_code == 400
    assert post({"items": [{"idempotency_key": "", "payload": customer(1)}]}).status_code == 400
    assert post([1, 2]).status_code == 400
    bad_json = client.post("/api/customers:batch", content=b"{not json", headers=AUTH)
    assert bad_json.status_code == 400 and bad_json.json()["error"]["code"] == "invalid_request"
    assert client.post("/api/payments:batch", json={"items": []}, headers=AUTH).status_code == 404


def test_admin_requires_token(client: TestClient) -> None:
    for method, path in (
        ("GET", "/_admin/stats"),
        ("GET", "/_admin/dump/customers"),
        ("POST", "/_admin/reset"),
    ):
        assert client.request(method, path).status_code == 401
        assert client.request(method, path, headers={"X-Admin-Token": "nope"}).status_code == 401


def test_admin_reset_stats_and_dump(client: TestClient) -> None:
    batch(client, "customers", [customer(1), customer(2)])
    dump = client.get("/_admin/dump/customers", headers=ADMIN).json()["items"]
    assert [r["external_id"] for r in dump] == ["C000001", "C000002"]
    stats = client.get("/_admin/stats", headers=ADMIN).json()
    assert stats["records"]["customers"] == 2 and stats["version"] == "v1"
    assert stats["requests"]["batch"] == {"customers": 1}
    assert stats["items"] == {"201": 2}

    reset = client.post(
        "/_admin/reset",
        json={"seed": 5, "fault_plan": {"rules": [{"kind": "schema_flip", "after_requests": 3}]}},
        headers=ADMIN,
    )
    assert reset.json() == {"ok": True, "seed": 5, "version": "v1"}
    stats = client.get("/_admin/stats", headers=ADMIN).json()
    assert stats["records"] == {"customers": 0, "subscriptions": 0, "invoices": 0}
    assert stats["seed"] == 5 and stats["fault_plan"]["rules"][0]["kind"] == "schema_flip"
    assert one(client, "customers", customer(1))["id"] == "cus_000001"  # id sequence restarts
    assert client.get("/_admin/dump/payments", headers=ADMIN).status_code == 404


def test_admin_reset_rejects_bad_plans(client: TestClient) -> None:
    for body in (
        {"fault_plan": {"rules": [{"kind": "explode"}]}},
        {"fault_plan": {"rules": [{"kind": "schema_flip", "to_version": "v9"}]}},
        {"version": "v3"},
        [1],
    ):
        assert client.post("/_admin/reset", json=body, headers=ADMIN).status_code == 400
    assert client.post("/_admin/reset", headers=ADMIN).json()["ok"] is True  # empty body = clean reset


def test_admin_reset_can_choose_version(client: TestClient) -> None:
    client.post("/_admin/reset", json={"version": "v2"}, headers=ADMIN)
    assert client.get("/api/meta").json() == {"api_version": "v2"}
    client.post("/_admin/reset", json={}, headers=ADMIN)
    assert client.get("/api/meta").json() == {"api_version": "v1"}


def test_create_app_rejects_unknown_version() -> None:
    with pytest.raises(ValueError):
        novabill.create_app(price_catalog(), initial_version="v3")


def test_malformed_batch_does_not_consume_a_fault() -> None:
    """Regression: faults were evaluated before the envelope was parsed, so a 400 used up a rule."""
    from zerodrop.models import FaultPlan, FaultRule

    plan = FaultPlan(rules=[FaultRule(kind="rate_limit", count=1), FaultRule(kind="timeout_after_write")])
    client = TestClient(novabill.create_app(price_catalog(), fault_plan=plan))
    assert client.post("/api/customers:batch", json={"items": []}, headers=AUTH).status_code == 400
    assert client.post("/api/customers:batch", content=b"{", headers=AUTH).status_code == 400
    assert batch(client, "customers", [customer()]).status_code == 429  # the rule is still armed
    stats = client.get("/_admin/stats", headers=ADMIN).json()
    assert stats["rules"][0]["seen"] == 1 and stats["requests"]["batch"] == {"customers": 1}
    assert stats["requests"]["by_status"] == {"400": 2, "429": 1}
    assert stats["token_revoked"] is False


def test_version_header_and_status_counts_after_a_flip() -> None:
    from zerodrop.models import FaultPlan, FaultRule

    plan = FaultPlan(rules=[FaultRule(kind="schema_flip", entity="subscriptions", to_version="v2")])
    client = TestClient(novabill.create_app(price_catalog(), fault_plan=plan))
    cid = seeded_customer(client)
    flipped = batch(client, "subscriptions", [subscription(cid)])  # v1 payload hits the new v2 schema
    assert flipped.headers["NovaBill-Version"] == "v2"
    assert flipped.json()["results"][0]["error"]["code"] == "unknown_field"
    assert client.get("/api/schema").json()["version"] == "v2"
    assert client.get("/api/meta").headers["NovaBill-Version"] == "v2"
    assert client.get("/_admin/stats", headers=ADMIN).json()["requests"]["by_status"]["200"] >= 3
