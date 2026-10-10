import pytest
from fastapi.testclient import TestClient

from zerodrop.models import FaultPlan, FaultRule
from zerodrop.sandbox import legacybill
from zerodrop.sandbox.fixtures import Dataset, generate


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return generate(4, "small", orphan_invoices=2, duplicate_emails=1)


@pytest.fixture(scope="module")
def client(dataset: Dataset) -> TestClient:
    return TestClient(legacybill.create_app(dataset))


def _collect(client: TestClient, entity: str, limit: int) -> tuple[list[dict], int]:
    items: list[dict] = []
    cursor: str | None = None
    pages = 0
    while True:
        params: dict = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        response = client.get(f"/api/{entity}", params=params)
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"items", "next_cursor"}
        items += body["items"]
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            return items, pages


def test_account_and_field_docs(client: TestClient, dataset: Dataset) -> None:
    assert client.get("/api/account").json() == {
        "company": dataset.account["company"],
        "timezone": "Asia/Kolkata",
        "export_version": "3.2",
    }
    docs = client.get("/api/docs/fields").json()
    assert set(docs) == {"customers", "subscriptions", "invoices"}
    assert "cust_id" in docs["customers"] and "amount" in docs["invoices"]


def test_count_includes_soft_deleted(client: TestClient, dataset: Dataset) -> None:
    count = client.get("/api/customers/count").json()["count"]
    live = [c for c in dataset.source["customers"] if not c["deleted"]]
    assert count == len(dataset.source["customers"])
    assert count > len(live)
    assert client.get("/api/invoices/count").json() == {"count": len(dataset.source["invoices"])}


@pytest.mark.parametrize("entity", ["customers", "subscriptions", "invoices"])
def test_pagination_returns_everything_once_in_id_order(
    client: TestClient, dataset: Dataset, entity: str
) -> None:
    items, pages = _collect(client, entity, limit=7)
    assert items == dataset.source[entity]
    assert pages == -(-len(items) // 7)


def test_page_size_exact_multiple_ends_with_null_cursor(client: TestClient, dataset: Dataset) -> None:
    total = len(dataset.source["customers"])
    body = client.get("/api/customers", params={"limit": total}).json()
    assert len(body["items"]) == total and body["next_cursor"] is None
    first = client.get("/api/customers", params={"limit": 5}).json()
    assert first["next_cursor"] == first["items"][-1]["cust_id"]


def test_default_and_max_limit(client: TestClient, dataset: Dataset) -> None:
    body = client.get("/api/invoices").json()
    assert len(body["items"]) == min(100, len(dataset.source["invoices"]))
    assert client.get("/api/invoices", params={"limit": 200}).status_code == 200
    assert client.get("/api/invoices", params={"limit": 0}).status_code == 422
    assert client.get("/api/invoices", params={"limit": 201}).status_code == 422


def test_records_are_raw_legacy_representation(client: TestClient) -> None:
    customer = client.get("/api/customers", params={"limit": 1}).json()["items"][0]
    assert set(customer) == {
        "cust_id",
        "full_name",
        "email",
        "country",
        "status",
        "created",
        "notes",
        "deleted",
    }
    invoice = client.get("/api/invoices", params={"limit": 1}).json()["items"][0]
    assert isinstance(invoice["amount"], str) and invoice["currency"].isupper()


def test_unknown_entity_is_404(client: TestClient) -> None:
    for path in ("/api/payments", "/api/payments/count"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "unknown_entity"


def test_no_faults_without_a_plan(client: TestClient) -> None:
    for _ in range(5):
        assert client.get("/api/customers", params={"limit": 1}).status_code == 200


def test_source_rate_limit_and_server_error_from_plan(dataset: Dataset) -> None:
    plan = FaultPlan(
        rules=[
            FaultRule(kind="rate_limit", after_requests=1, count=1, retry_after_s=2),
            FaultRule(kind="server_error", after_requests=3, count=1),
            FaultRule(
                kind="rate_limit", entity="customers", after_requests=0, count=5
            ),  # entity rules: target only
            FaultRule(kind="partial_accept", after_requests=0, count=5),  # not a source fault kind
        ]
    )
    client = TestClient(legacybill.create_app(dataset, fault_plan=plan))
    statuses = []
    for _ in range(6):
        response = client.get("/api/customers", params={"limit": 2})
        statuses.append(response.status_code)
        if response.status_code == 429:
            assert response.headers["Retry-After"] == "2"
            assert response.json()["error"]["code"] == "rate_limited"
    assert statuses == [200, 429, 200, 503, 200, 200]  # after_requests=N: N requests pass first
    # account / docs / count are never faulted
    assert client.get("/api/customers/count").status_code == 200
