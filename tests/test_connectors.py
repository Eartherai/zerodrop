from __future__ import annotations

import json
import pickle
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest

from zerodrop.connectors.errors import (
    SourceError,
    TargetConnectionError,
    TargetHTTPError,
    TargetTimeout,
    parse_retry_after,
)
from zerodrop.connectors.source import SourceClient
from zerodrop.connectors.target import BatchResult, TargetClient
from zerodrop.models import Entity

Handler = Callable[[httpx.Request], httpx.Response]


def source(handler: Handler) -> SourceClient:
    return SourceClient("http://legacy.test/", transport=httpx.MockTransport(handler))


def target(handler: Handler, token: Callable[[], str] = lambda: "tok") -> TargetClient:
    return TargetClient("http://nova.test", token, transport=httpx.MockTransport(handler))


def nb(status: int, body: Any, version: str | None = "v1", **headers: str) -> httpx.Response:
    hdrs = dict(headers)
    if version:
        hdrs["NovaBill-Version"] = version
    return httpx.Response(status, json=body, headers=hdrs)


# ---------------------------------------------------------------------------
# SourceClient
# ---------------------------------------------------------------------------

RECORDS = [{"cust_id": f"C{i:06d}"} for i in range(1, 8)]


def paging_handler(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        start = int(request.url.params.get("cursor", "0"))
        limit = int(request.url.params["limit"])
        chunk = RECORDS[start : start + limit]
        nxt = start + limit
        return httpx.Response(
            200, json={"items": chunk, "next_cursor": str(nxt) if nxt < len(RECORDS) else None}
        )

    return handler


def test_source_iter_records_follows_cursors() -> None:
    seen: list[httpx.Request] = []
    with source(paging_handler(seen)) as client:
        assert list(client.iter_records(Entity.customers, limit=3)) == RECORDS
    assert [r.url.path for r in seen] == ["/api/customers"] * 3
    assert [r.url.params.get("cursor") for r in seen] == [None, "3", "6"]
    assert {r.url.params["limit"] for r in seen} == {"3"}


def test_source_limit_is_clamped() -> None:
    seen: list[httpx.Request] = []
    client = source(paging_handler(seen))
    list(client.iter_records("customers", limit=5000))
    list(client.iter_records("customers", limit=0))
    assert [r.url.params["limit"] for r in seen] == ["200", "1"] + ["1"] * (len(RECORDS) - 1)


def test_source_simple_endpoints() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        bodies = {
            "/api/account": {"company": "Acme", "timezone": "Asia/Kolkata", "export_version": "3.2"},
            "/api/docs/fields": {"customers": {"cust_id": "id"}},
            "/api/customers/count": {"count": 32},
        }
        return httpx.Response(200, json=bodies[request.url.path])

    client = source(handler)
    assert client.account()["timezone"] == "Asia/Kolkata"
    assert client.field_docs() == {"customers": {"cust_id": "id"}}
    assert client.count("customers") == 32


def test_source_http_error_carries_status_and_retry_after() -> None:
    client = source(
        lambda r: httpx.Response(429, json={"error": "slow down"}, headers={"Retry-After": "0.5"})
    )
    with pytest.raises(SourceError) as info:
        client.account()
    err = info.value
    assert (err.status, err.retry_after, err.timeout, err.transient) == (429, 0.5, False, True)
    assert err.body == {"error": "slow down"}


def test_source_404_is_not_transient() -> None:
    client = source(lambda r: httpx.Response(404, text="unknown entity"))
    with pytest.raises(SourceError) as info:
        client.count("refunds")
    assert info.value.status == 404 and not info.value.transient and info.value.body == "unknown entity"


def test_source_timeout_and_connection_errors() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(SourceError) as info:
        source(timeout).account()
    assert info.value.timeout and info.value.status is None and info.value.transient
    with pytest.raises(SourceError) as info:
        source(refused).account()
    assert not info.value.timeout and info.value.transient


def test_source_pagination_loop_is_detected() -> None:
    client = source(lambda r: httpx.Response(200, json={"items": [{"x": 1}], "next_cursor": "same"}))
    with pytest.raises(SourceError, match="pagination loop"):
        list(client.iter_records("customers"))


@pytest.mark.parametrize(
    "body",
    [{"items": "nope", "next_cursor": None}, {"next_cursor": None}, [1, 2], {"items": [], "next_cursor": 5}],
)
def test_source_malformed_page(body: Any) -> None:
    with pytest.raises(SourceError):
        list(source(lambda r: httpx.Response(200, json=body)).iter_records("customers"))


def test_source_bad_count() -> None:
    with pytest.raises(SourceError):
        source(lambda r: httpx.Response(200, json={"count": "12"})).count("customers")


# ---------------------------------------------------------------------------
# Retry-After parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("0.2", 0.2),
        ("3", 3.0),
        (" 1.5 ", 1.5),
        ("-4", 0.0),
        (None, None),
        ("", None),
        ("soon", None),
        ("nan", None),
    ],
)
def test_parse_retry_after_seconds(header: str | None, expected: float | None) -> None:
    assert parse_retry_after(header) == expected


def test_parse_retry_after_http_date() -> None:
    now = datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)
    assert parse_retry_after("Sat, 10 Oct 2026 12:00:07 GMT", now=now) == 7.0
    assert parse_retry_after("Sat, 10 Oct 2026 11:00:00 GMT", now=now) == 0.0


# ---------------------------------------------------------------------------
# TargetClient
# ---------------------------------------------------------------------------


def test_target_sends_fresh_bearer_token_each_request() -> None:
    tokens = iter(["first", "second\n"])
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        return nb(200, {"api_version": "v1"})

    client = target(handler, token=lambda: next(tokens))
    client.meta()
    client.meta()
    assert seen == ["Bearer first", "Bearer second"]


def test_target_set_token_replaces_the_provider() -> None:
    provider_calls: list[int] = []
    seen: list[str] = []

    def provider() -> str:
        provider_calls.append(1)
        return "original"

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        if request.url.path.endswith(":batch"):
            return nb(200, {"results": [{"index": 0, "status": 201, "id": "cus_1"}]})
        return nb(200, {"items": [], "next_cursor": None})

    client = target(handler, token=provider)
    client.meta()
    client.set_token("  rotated\n")
    client.meta()
    client.lookup("customers", "C000001")
    client.batch("customers", [{"idempotency_key": "customers:C000001", "payload": {}}])
    assert seen == ["Bearer original", "Bearer rotated", "Bearer rotated", "Bearer rotated"]
    assert len(provider_calls) == 1  # the constructor's provider is no longer consulted
    client.set_token("rotated-again")
    client.meta()
    assert seen[-1] == "Bearer rotated-again"


@pytest.mark.parametrize("bad", ["", "   ", "\n", None, 42])
def test_target_set_token_refuses_empty_or_non_string_tokens(bad: Any) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["Authorization"])
        return nb(200, {"api_version": "v1"})

    client = target(handler, token=lambda: "tok")
    with pytest.raises(ValueError, match="non-empty string"):
        client.set_token(bad)
    client.meta()
    assert seen == ["Bearer tok"]  # the previous credentials stay in place


def test_target_captures_version_header() -> None:
    versions = iter(["v1", None, "v2"])

    def handler(request: httpx.Request) -> httpx.Response:
        return nb(200, {"api_version": "v1"}, version=next(versions))

    client = target(handler)
    assert client.last_version is None
    client.meta()
    assert client.last_version == "v1"
    client.meta()  # a response without the header keeps the last known version
    assert client.last_version == "v1"
    client.meta()
    assert client.last_version == "v2"


def test_target_version_header_captured_on_errors_too() -> None:
    client = target(lambda r: nb(422, {"detail": "bad"}, version="v2"))
    with pytest.raises(TargetHTTPError):
        client.schema()
    assert client.last_version == "v2"


def test_target_schema_and_prices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/schema":
            return nb(200, {"version": "v1", "entities": {}, "reference_tables": {"prices": "/api/prices"}})
        return nb(200, {"items": [{"id": "price_pro_m", "lookup_key": "PRO_M"}]})

    client = target(handler)
    assert client.schema()["version"] == "v1"
    assert client.prices() == [{"id": "price_pro_m", "lookup_key": "PRO_M"}]


def test_target_batch_parses_per_item_results() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return nb(
            200,
            {
                "results": [
                    {
                        "index": 2,
                        "status": 422,
                        "id": None,
                        "error": {"code": "invalid_value", "field": "email", "message": "bad"},
                    },
                    {"index": 0, "status": 201, "id": "cus_1", "error": None},
                    {
                        "index": 1,
                        "status": 409,
                        "id": "cus_9",
                        "error": {"code": "duplicate_external_id", "field": None, "message": ""},
                    },
                    {
                        "index": 3,
                        "status": 503,
                        "id": None,
                        "error": {"code": "temporarily_unavailable", "field": None, "message": "x"},
                    },
                ]
            },
            version="v2",
        )

    items = [{"idempotency_key": f"customers:C{i}", "payload": {"external_id": f"C{i}"}} for i in range(4)]
    result = target(handler).batch(Entity.customers, items)
    assert captured == {"method": "POST", "path": "/api/customers:batch", "body": {"items": items}}
    assert isinstance(result, BatchResult)
    assert (result.status_code, result.version) == (200, "v2")
    assert [r.index for r in result.results] == [0, 1, 2, 3]
    assert [r.status for r in result.results] == [201, 409, 422, 503]
    assert result.results[1].id == "cus_9"
    assert result.results[2].error is not None and result.results[2].error.field == "email"
    assert result.results[0].error is None


def test_target_batch_size_limits() -> None:
    client = target(lambda r: nb(200, {"results": []}))
    with pytest.raises(ValueError):
        client.batch("customers", [])
    with pytest.raises(ValueError):
        client.batch("customers", [{"idempotency_key": str(i), "payload": {}} for i in range(51)])


@pytest.mark.parametrize(
    "body",
    [
        {"results": "x"},
        {"nope": []},
        {"results": [{"index": "zero", "status": 201}]},
        ["not", "an", "object"],
    ],
)
def test_target_batch_malformed_body(body: Any) -> None:
    client = target(lambda r: nb(200, body))
    with pytest.raises(TargetHTTPError) as info:
        client.batch("customers", [{"idempotency_key": "k", "payload": {}}])
    assert info.value.status == 200


def test_target_429_carries_retry_after() -> None:
    client = target(lambda r: nb(429, {"error": {"code": "rate_limited"}}, **{"Retry-After": "0.2"}))
    with pytest.raises(TargetHTTPError) as info:
        client.batch("invoices", [{"idempotency_key": "k", "payload": {}}])
    err = info.value
    assert (err.status, err.retry_after, err.error_code) == (429, 0.2, "rate_limited")


@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (500, {"detail": "boom"}, "boom"),
        (503, "Service Unavailable", None),
        (401, {"error": {"code": "invalid_token", "message": "rotated"}}, "invalid_token"),
        (401, {"detail": {"code": "invalid_token"}}, "invalid_token"),
        (404, {"code": "unknown_entity"}, "unknown_entity"),
    ],
)
def test_target_error_statuses(status: int, body: Any, code: str | None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return nb(status, body)

    with pytest.raises(TargetHTTPError) as info:
        target(handler).meta()
    err = info.value
    assert (err.status, err.retry_after, err.error_code, err.body) == (status, None, code, body)


def raising(exc_type: type[httpx.TransportError]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_type("simulated", request=request)

    return handler


@pytest.mark.parametrize(
    ("exc_type", "sent"),
    [
        (httpx.ReadTimeout, True),
        (httpx.WriteTimeout, True),
        (httpx.ConnectTimeout, False),
        (httpx.PoolTimeout, False),
    ],
)
def test_target_timeouts(exc_type: type[httpx.TransportError], sent: bool) -> None:
    client = target(raising(exc_type))
    with pytest.raises(TargetTimeout) as info:
        client.batch("customers", [{"idempotency_key": "k", "payload": {}}])
    assert info.value.sent is sent


@pytest.mark.parametrize(
    ("exc_type", "sent"),
    [(httpx.ConnectError, False), (httpx.RemoteProtocolError, True), (httpx.ReadError, True)],
)
def test_target_connection_errors(exc_type: type[httpx.TransportError], sent: bool) -> None:
    with pytest.raises(TargetConnectionError) as info:
        target(raising(exc_type)).meta()
    assert info.value.sent is sent


def test_target_lookup() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        ext = request.url.params["external_id"]
        items = [{"id": "cus_1", "external_id": ext}] if ext == "C000001" else []
        return nb(200, {"items": items})

    client = target(handler)
    assert client.lookup(Entity.customers, "C000001") == {"id": "cus_1", "external_id": "C000001"}
    assert client.lookup("customers", "C404") is None
    assert seen[0].url.path == "/api/customers"


def test_target_list_all_paginates() -> None:
    rows = [{"id": f"inv_{i}"} for i in range(5)]
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        start = int(request.url.params.get("cursor", "0"))
        nxt = start + 2
        return nb(200, {"items": rows[start:nxt], "next_cursor": str(nxt) if nxt < len(rows) else None})

    assert target(handler).list_all("invoices") == rows
    assert [r.url.params.get("cursor") for r in seen] == [None, "2", "4"]
    assert all(r.url.params["limit"] == "100" for r in seen)


def test_target_list_all_detects_cursor_loop() -> None:
    client = target(lambda r: nb(200, {"items": [], "next_cursor": "again"}))
    with pytest.raises(TargetHTTPError) as info:
        client.list_all("customers")
    assert info.value.error_code == "pagination_loop"


def test_errors_pickle_round_trip() -> None:
    for err in (
        TargetHTTPError(429, 0.2, {"a": 1}),
        TargetTimeout(sent=True),
        TargetConnectionError("x", sent=True),
        SourceError("y", status=503, retry_after=1.0, timeout=False),
    ):
        clone = pickle.loads(pickle.dumps(err))
        assert type(clone) is type(err) and vars(clone) == vars(err)


# ---------------------------------------------------------------------------
# Real localhost server: the batch is committed, then the response stalls
# ---------------------------------------------------------------------------


class _StallAfterWrite(BaseHTTPRequestHandler):
    committed: list[dict[str, Any]] = []
    stall_s = 1.0

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        self.committed.append(json.loads(self.rfile.read(length)))
        time.sleep(self.stall_s)  # longer than the client timeout
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return


@pytest.fixture
def stall_server() -> Iterator[str]:
    _StallAfterWrite.committed = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StallAfterWrite)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_real_timeout_after_write_is_sent_true(stall_server: str) -> None:
    client = TargetClient(stall_server, lambda: "tok", timeout=0.2)
    started = time.monotonic()
    with pytest.raises(TargetTimeout) as info:
        client.batch("customers", [{"idempotency_key": "customers:C1", "payload": {"external_id": "C1"}}])
    assert info.value.sent is True
    assert time.monotonic() - started < 0.9
    assert _StallAfterWrite.committed[0]["items"][0]["idempotency_key"] == "customers:C1"
    client.close()


def test_real_connection_refused_is_not_sent() -> None:
    with ThreadingHTTPServer(("127.0.0.1", 0), _StallAfterWrite) as probe:
        port = probe.server_address[1]
    client = TargetClient(f"http://127.0.0.1:{port}", lambda: "tok", timeout=0.5)
    with pytest.raises((TargetConnectionError, TargetTimeout)) as info:
        client.meta()
    assert info.value.sent is False


# ---------------------------------------------------------------------------
# Against the real sandbox services (skipped until the sandbox modules exist)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_connectors_against_real_sandbox() -> None:
    fixtures = pytest.importorskip("zerodrop.sandbox.fixtures")
    servers = pytest.importorskip("zerodrop.sandbox.servers")
    dataset = fixtures.generate(3, "small")
    customers = sorted(dataset.source["customers"], key=lambda r: r["cust_id"])
    target_faults = {
        "rules": [
            {"kind": "timeout_after_write", "entity": "customers", "after_requests": 2, "delay_s": 0.6},
            {"kind": "rate_limit", "entity": "invoices", "retry_after_s": 0.25},
        ]
    }
    source_faults = {"rules": [{"kind": "rate_limit", "retry_after_s": 0.3}]}
    with servers.run_sandbox(dataset, target_faults, source_fault_plan=source_faults) as sandbox:
        src = SourceClient(sandbox.source_url)
        with pytest.raises(SourceError) as source_err:
            src.page("customers")
        assert (source_err.value.status, source_err.value.retry_after) == (429, 0.3)
        assert src.account()["timezone"] == "Asia/Kolkata"
        assert set(src.field_docs()) == {"customers", "subscriptions", "invoices"}
        assert src.count("customers") == len(customers)  # includes soft-deleted rows
        assert list(src.iter_records("customers", limit=7)) == customers
        with pytest.raises(SourceError) as missing:
            src.count("refunds")
        assert missing.value.status == 404

        token = {"value": sandbox.target_token}
        tgt = TargetClient(sandbox.target_url, lambda: token["value"], timeout=0.3)
        golden = {g["external_id"]: g for g in dataset.golden["customers"]}
        first = golden[next(iter(golden))]
        payload = {k: first[k] for k in first}
        item = [{"idempotency_key": f"customers:{first['external_id']}", "payload": payload}]
        created = tgt.batch("customers", item)
        assert [r.status for r in created.results] == [201]
        assert created.version == tgt.last_version == "v1"
        replay = tgt.batch("customers", item)  # same idempotency key -> original id, no new record
        assert [(r.status, r.id) for r in replay.results] == [(200, created.results[0].id)]

        second = golden[list(golden)[1]]
        with pytest.raises(TargetTimeout) as stalled:  # committed, then the response stalls
            tgt.batch(
                "customers", [{"idempotency_key": f"customers:{second['external_id']}", "payload": second}]
            )
        assert stalled.value.sent is True
        assert (tgt.lookup("customers", second["external_id"]) or {}).get("email") == second["email"]
        assert tgt.lookup("customers", "C999999") is None
        assert {r["external_id"] for r in tgt.list_all("customers")} == {
            first["external_id"],
            second["external_id"],
        }

        with pytest.raises(TargetHTTPError) as limited:
            tgt.batch("invoices", [{"idempotency_key": "invoices:x", "payload": {}}])
        assert (limited.value.status, limited.value.retry_after, limited.value.error_code) == (
            429,
            0.25,
            "rate_limited",
        )

        sandbox.reset(1, {"rules": [{"kind": "auth_revoke"}, {"kind": "schema_flip", "to_version": "v2"}]})
        third = golden[list(golden)[2]]
        batch_item = [{"idempotency_key": f"customers:{third['external_id']}", "payload": third}]
        with pytest.raises(TargetHTTPError) as revoked:
            tgt.batch("customers", batch_item)
        assert (revoked.value.status, revoked.value.error_code) == (401, "invalid_token")
        token["value"] = sandbox.rotated_token  # the provider is consulted on every request
        assert [r.status for r in tgt.batch("customers", batch_item).results] == [201]
        assert tgt.last_version == "v2" and tgt.meta() == {"api_version": "v2"}
        prices = tgt.prices()
        assert prices and {"id", "lookup_key"} <= set(prices[0])
