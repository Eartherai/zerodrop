import threading
import time
from typing import Any

from fastapi.testclient import TestClient

from zerodrop.models import FaultPlan, FaultRule
from zerodrop.sandbox import novabill
from zerodrop.sandbox.chaos import DEFAULT_STALL_S, FaultInjector, format_seconds
from zerodrop.sandbox.fixtures import price_catalog

TOKEN = "nb_live_local_demo_token"
ROTATED = "nb_live_rotated_token"
ADMIN = {"X-Admin-Token": "nb_admin_local"}


def plan(*rules: FaultRule) -> FaultPlan:
    return FaultPlan(seed=1, rules=list(rules))


def customer(n: int) -> dict[str, Any]:
    return {
        "external_id": f"C{n:06d}",
        "given_name": "Ravi",
        "family_name": "Iyer",
        "email": f"ravi{n}@example.com",
        "country": "IN",
        "status": "active",
        "created_at": "2020-01-01T18:30:00Z",
        "notes": None,
    }


def post_customers(client: TestClient, numbers: list[int], token: str = TOKEN):
    items = [{"idempotency_key": f"customers:C{n:06d}", "payload": customer(n)} for n in numbers]
    return client.post(
        "/api/customers:batch", json={"items": items}, headers={"Authorization": f"Bearer {token}"}
    )


def app_client(fault_plan: FaultPlan | None) -> TestClient:
    return TestClient(novabill.create_app(price_catalog(), fault_plan=fault_plan))


def dump(client: TestClient, entity: str = "customers") -> list[dict]:
    return client.get(f"/_admin/dump/{entity}", headers=ADMIN).json()["items"]


# -- FaultInjector unit behaviour ----------------------------------------------------


def statuses(injector: FaultInjector, entities: list[str], **kw: Any) -> list[int | None]:
    out = []
    for entity in entities:
        outcome = injector.evaluate(entity, **kw)
        out.append(None if outcome.reject is None else outcome.reject.status)
    return out


def test_after_requests_and_count_window() -> None:
    injector = FaultInjector(plan(FaultRule(kind="rate_limit", after_requests=2, count=3)))
    assert statuses(injector, ["customers"] * 7) == [None, None, 429, 429, 429, None, None]


def test_entity_filter_counts_only_matching_requests() -> None:
    injector = FaultInjector(
        plan(FaultRule(kind="server_error", entity="invoices", after_requests=1, count=1))
    )
    sequence = ["customers", "invoices", "customers", "invoices", "invoices"]
    assert statuses(injector, sequence) == [None, None, None, 503, None]


def test_counters_are_deterministic() -> None:
    rules = plan(
        FaultRule(kind="rate_limit", after_requests=1, count=2),
        FaultRule(kind="server_error", entity="subscriptions", after_requests=0, count=1),
        FaultRule(kind="partial_accept", after_requests=3, count=1, accept_first=2),
    )
    sequence = ["customers", "subscriptions", "subscriptions", "customers", "invoices", "subscriptions"]
    runs = []
    for _ in range(2):
        injector = FaultInjector(rules)
        for entity in sequence:
            injector.evaluate(entity)
        runs.append(injector.stats()["fired"])
    assert runs[0] == runs[1]


def test_shadowed_rule_keeps_its_count() -> None:
    injector = FaultInjector(
        plan(
            FaultRule(kind="rate_limit", after_requests=0, count=1),
            FaultRule(kind="server_error", after_requests=0, count=1),
        )
    )
    assert statuses(injector, ["customers"] * 3) == [429, 503, None]


def test_non_terminal_faults_combine() -> None:
    injector = FaultInjector(
        plan(
            FaultRule(kind="schema_flip", to_version="v2"),
            FaultRule(kind="slow", delay_s=0.25),
            FaultRule(kind="partial_accept", accept_first=3),
            FaultRule(kind="partial_accept", accept_first=1),
            FaultRule(kind="timeout_after_write"),
        )
    )
    outcome = injector.evaluate("customers")
    assert outcome.flip_to == "v2"
    assert outcome.delay_s == 0.25
    assert outcome.accept_first == 1
    assert outcome.stall_s == DEFAULT_STALL_S
    assert outcome.reject is None
    assert [f["kind"] for f in outcome.fired] == [
        "schema_flip",
        "slow",
        "partial_accept",
        "partial_accept",
        "timeout_after_write",
    ]


def test_rejection_shadows_post_effects() -> None:
    injector = FaultInjector(
        plan(FaultRule(kind="rate_limit", count=1), FaultRule(kind="partial_accept", count=1, accept_first=0))
    )
    first = injector.evaluate("customers")
    assert first.reject is not None and first.accept_first is None
    assert injector.evaluate("customers").accept_first == 0


def test_auth_revoke_only_hits_the_original_token() -> None:
    injector = FaultInjector(plan(FaultRule(kind="auth_revoke", after_requests=1, count=2)))
    assert not injector.token_revoked()
    assert statuses(injector, ["customers"], original_token=True) == [None]
    assert not injector.token_revoked()  # eligible is not triggered: reads still work
    assert statuses(injector, ["customers"], original_token=False) == [None]  # triggers, not refused
    assert injector.token_revoked()
    assert statuses(injector, ["customers"] * 3, original_token=True) == [401, 401, 401]
    assert statuses(injector, ["customers"] * 2, original_token=False) == [None, None]
    assert injector.token_revoked()


def test_auth_revoke_is_persistent_whatever_the_count() -> None:
    """Regression: count=1 used to restore the original token after a single 401."""
    injector = FaultInjector(plan(FaultRule(kind="auth_revoke", after_requests=0, count=1)))
    assert statuses(injector, ["customers"] * 5, original_token=True) == [401] * 5
    fired = injector.stats()["fired"]
    assert [f["counted"] for f in fired] == [True, False, False, False, False]
    assert injector.stats()["rules"][0]["fired"] == 1 and injector.stats()["token_revoked"] is True


def test_auth_revoke_waits_for_a_matching_request_then_is_global() -> None:
    """Regression: an invoices-only rule with after_requests=0 used to revoke before any invoice write."""
    injector = FaultInjector(
        plan(FaultRule(kind="auth_revoke", entity="invoices", after_requests=0, count=1))
    )
    assert statuses(injector, ["customers", "subscriptions"], original_token=True) == [None, None]
    assert not injector.token_revoked()
    blocked = injector.evaluate("invoices", original_token=True)
    assert blocked.reject is not None and blocked.reject.status == 401
    assert blocked.fired[0]["counted"] is True
    assert injector.token_revoked()
    later = injector.evaluate("customers", original_token=True)  # global once revoked
    assert later.reject is not None and later.fired[0]["counted"] is False


def test_auth_revoke_after_requests_counts_matching_writes() -> None:
    injector = FaultInjector(
        plan(FaultRule(kind="auth_revoke", entity="invoices", after_requests=2, count=1))
    )
    sequence = ["customers", "invoices", "customers", "invoices", "invoices", "customers"]
    assert statuses(injector, sequence, original_token=True) == [None, None, None, None, 401, 401]


def test_source_restrictions() -> None:
    injector = FaultInjector(
        plan(
            FaultRule(kind="rate_limit", entity="customers"),
            FaultRule(kind="partial_accept"),
            FaultRule(kind="slow", delay_s=0.1),
        ),
        kinds={"rate_limit", "server_error", "slow"},
        any_entity_only=True,
    )
    outcome = injector.evaluate("customers")
    assert outcome.reject is None and outcome.accept_first is None and outcome.delay_s == 0.1
    assert [r["kind"] for r in injector.stats()["rules"]] == ["slow"]


def test_format_seconds() -> None:
    assert format_seconds(0.2) == "0.2"
    assert format_seconds(1.0) == "1"
    assert format_seconds(2.5) == "2.5"
    assert format_seconds(0.0001) == "0"


# -- faults through the NovaBill app -----------------------------------------------


def test_rate_limit_429_with_retry_after() -> None:
    client = app_client(plan(FaultRule(kind="rate_limit", after_requests=1, count=1, retry_after_s=0.2)))
    assert post_customers(client, [1]).status_code == 200
    limited = post_customers(client, [2])
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "0.2"
    assert limited.headers["NovaBill-Version"] == "v1"
    assert limited.json()["error"]["code"] == "rate_limited"
    assert [r["external_id"] for r in dump(client)] == ["C000001"]  # nothing written
    assert post_customers(client, [2]).status_code == 200


def test_server_error_503() -> None:
    client = app_client(plan(FaultRule(kind="server_error", count=2)))
    assert [post_customers(client, [1]).status_code for _ in range(3)] == [503, 503, 200]
    assert len(dump(client)) == 1


def test_partial_accept_commits_first_items_only() -> None:
    client = app_client(plan(FaultRule(kind="partial_accept", accept_first=2)))
    results = post_customers(client, [1, 2, 3, 4]).json()["results"]
    assert [r["status"] for r in results] == [201, 201, 503, 503]
    assert results[2]["error"] == {
        "code": "temporarily_unavailable",
        "field": None,
        "message": results[2]["error"]["message"],
    }
    assert results[2]["id"] is None
    assert [r["external_id"] for r in dump(client)] == ["C000001", "C000002"]
    retry = post_customers(client, [1, 2, 3, 4]).json()["results"]
    assert [r["status"] for r in retry] == [200, 200, 201, 201]


def test_schema_flip_is_persistent_and_applies_before_processing() -> None:
    client = app_client(plan(FaultRule(kind="schema_flip", after_requests=1, to_version="v2")))
    headers = {"Authorization": f"Bearer {TOKEN}"}

    def sub(n: int, **field: str) -> Any:
        payload = {
            "external_id": f"S{n}",
            "customer_id": "cus_000001",
            "status": "active",
            "start_at": "2023-01-05T04:52:00Z",
            "quantity": 1,
        } | field
        body = {"items": [{"idempotency_key": f"s{n}", "payload": payload}]}
        return client.post("/api/subscriptions:batch", json=body, headers=headers)

    assert post_customers(client, [1]).headers["NovaBill-Version"] == "v1"
    flipped = sub(1, plan_code="PRO_M")
    assert flipped.headers["NovaBill-Version"] == "v2"
    assert flipped.json()["results"][0]["error"]["code"] == "unknown_field"
    assert client.get("/api/meta").json() == {"api_version": "v2"}
    assert sub(2, price_id="price_pro_m").json()["results"][0]["status"] == 201
    assert sub(3, plan_code="PRO_M").json()["results"][0]["status"] == 422  # stays v2
    client.post("/_admin/reset", json={"seed": 0}, headers=ADMIN)
    assert client.get("/api/meta").json() == {"api_version": "v1"}


def test_auth_revoke_through_app() -> None:
    client = app_client(plan(FaultRule(kind="auth_revoke", after_requests=1, count=1000)))
    original = {"Authorization": f"Bearer {TOKEN}"}
    rotated = {"Authorization": f"Bearer {ROTATED}"}
    assert post_customers(client, [1]).status_code == 200
    revoked = post_customers(client, [2])
    assert revoked.status_code == 401 and revoked.json()["error"]["code"] == "invalid_token"
    assert client.get("/api/customers", headers=original).status_code == 401  # reads too, while active
    assert client.get("/api/customers", headers=rotated).status_code == 200
    assert post_customers(client, [2], token=ROTATED).json()["results"][0]["status"] == 201
    kinds = [f["kind"] for f in client.get("/_admin/stats", headers=ADMIN).json()["fired"]]
    assert kinds.count("auth_revoke") == 2


def test_auth_revoke_reads_refused_only_after_the_trigger() -> None:
    client = app_client(plan(FaultRule(kind="auth_revoke", after_requests=1, count=1)))
    original = {"Authorization": f"Bearer {TOKEN}"}
    assert post_customers(client, [1]).status_code == 200
    assert client.get("/api/customers", headers=original).status_code == 200  # not yet revoked
    assert post_customers(client, [2]).status_code == 401
    for _ in range(3):  # persistent: count=1 does not hand the original token back
        assert post_customers(client, [2]).status_code == 401
        assert client.get("/api/customers", headers=original).status_code == 401
    assert post_customers(client, [2], token=ROTATED).json()["results"][0]["status"] == 201
    stats = client.get("/_admin/stats", headers=ADMIN).json()
    assert stats["token_revoked"] is True
    client.post("/_admin/reset", headers=ADMIN, json={"seed": 1})
    assert client.get("/api/customers", headers=original).status_code == 200  # reset clears it


def test_slow_adds_latency() -> None:
    client = app_client(plan(FaultRule(kind="slow", delay_s=0.3)))
    start = time.monotonic()
    assert post_customers(client, [1]).status_code == 200
    assert time.monotonic() - start >= 0.3
    start = time.monotonic()
    post_customers(client, [2])
    assert time.monotonic() - start < 0.3


def test_timeout_after_write_commits_before_the_stall() -> None:
    client = app_client(plan(FaultRule(kind="timeout_after_write", delay_s=1.0)))
    finished = threading.Event()
    response: dict[str, Any] = {}

    def slow_post() -> None:
        response["value"] = post_customers(client, [1, 2])
        finished.set()

    thread = threading.Thread(target=slow_post)
    started = time.monotonic()
    thread.start()
    committed_while_stalled = False
    while not finished.is_set() and time.monotonic() - started < 5:
        if len(dump(client)) == 2:
            committed_while_stalled = not finished.is_set()
            break
        time.sleep(0.02)
    thread.join(timeout=5)
    assert committed_while_stalled
    assert time.monotonic() - started >= 1.0
    assert [r["status"] for r in response["value"].json()["results"]] == [201, 201]
    # a client that timed out and retries with the same keys gets 200s, not duplicates
    assert [r["status"] for r in post_customers(client, [1, 2]).json()["results"]] == [200, 200]
    assert len(dump(client)) == 2


def test_stats_record_every_fired_fault() -> None:
    client = app_client(
        plan(
            FaultRule(kind="rate_limit", count=1),
            FaultRule(kind="partial_accept", after_requests=2, accept_first=0),
        )
    )
    for n in range(4):
        post_customers(client, [n + 1])
    stats = client.get("/_admin/stats", headers=ADMIN).json()
    assert [(f["kind"], f["request"]) for f in stats["fired"]] == [("rate_limit", 1), ("partial_accept", 3)]
    assert stats["requests"]["by_status"]["429"] == 1
    assert stats["items"]["503"] == 1
    assert stats["rules"][0] == {
        "index": 0,
        "kind": "rate_limit",
        "entity": None,
        "seen": 4,
        "fired": 1,
        "exhausted": True,
    }


def test_interruptible_sleep_ends_early_when_stopped() -> None:
    import asyncio

    from zerodrop.sandbox.chaos import interruptible_sleep

    stop = threading.Event()
    start = time.monotonic()
    asyncio.run(interruptible_sleep(0.15, stop))
    assert 0.15 <= time.monotonic() - start < 1.0
    stop.set()
    start = time.monotonic()
    asyncio.run(interruptible_sleep(30.0, stop))
    assert time.monotonic() - start < 0.5


def test_stop_stalls_releases_a_stalled_write_after_commit() -> None:
    app = novabill.create_app(
        price_catalog(), fault_plan=plan(FaultRule(kind="timeout_after_write", delay_s=30))
    )
    client = TestClient(app)
    result: dict[str, Any] = {}
    thread = threading.Thread(target=lambda: result.setdefault("r", post_customers(client, [1])))
    thread.start()
    deadline = time.monotonic() + 5
    while not dump(client) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(dump(client)) == 1 and thread.is_alive()  # committed, still stalling
    app.state.stop_stalls.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert result["r"].json()["results"][0]["status"] == 201
