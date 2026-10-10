import socket

import httpx
import pytest

from zerodrop.models import FaultPlan, FaultRule
from zerodrop.sandbox.fixtures import generate
from zerodrop.sandbox.servers import SandboxHandle, load_fault_plan, run_sandbox

pytestmark = pytest.mark.slow  # starts real uvicorn servers (each test still takes ~1 s)


def _client() -> httpx.Client:
    return httpx.Client(timeout=5.0, trust_env=False)


def _refuses_connections(url: str) -> bool:
    host, port = url.removeprefix("http://").split(":")
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, int(port))) != 0


def test_run_sandbox_starts_and_stops_both_servers() -> None:
    dataset = generate(3, "small")
    with run_sandbox(dataset) as handle:
        assert isinstance(handle, SandboxHandle)
        assert handle.source_url != handle.target_url
        with _client() as client:
            assert client.get(f"{handle.source_url}/api/account").json()["timezone"] == "Asia/Kolkata"
            count = client.get(f"{handle.source_url}/api/customers/count").json()["count"]
            assert count == len(dataset.source["customers"])
            meta = client.get(f"{handle.target_url}/api/meta")
            assert meta.json() == {"api_version": "v1"} and meta.headers["NovaBill-Version"] == "v1"
            auth = {"Authorization": f"Bearer {handle.target_token}"}
            assert client.get(f"{handle.target_url}/api/customers", headers=auth).status_code == 200
        assert handle.admin("GET", "/_admin/stats")["records"]["customers"] == 0
        assert handle.rotated_token == "nb_live_rotated_token"
        urls = (handle.source_url, handle.target_url)
    assert all(_refuses_connections(url) for url in urls)


def test_timeout_after_write_real_client_timeout_then_lookup() -> None:
    plan = FaultPlan(rules=[FaultRule(kind="timeout_after_write", delay_s=0.8)])
    payload = {
        "external_id": "C000001",
        "given_name": "Mia",
        "family_name": "Clark",
        "email": "mia.clark@example.com",
        "country": "US",
        "status": "active",
        "created_at": "2022-05-01T18:30:00Z",
        "notes": None,
    }
    with run_sandbox(generate(3, "small"), plan) as handle, _client() as client:
        auth = {"Authorization": f"Bearer {handle.target_token}"}
        body = {"items": [{"idempotency_key": "customers:C000001", "payload": payload}]}
        with pytest.raises(httpx.ReadTimeout):
            client.post(f"{handle.target_url}/api/customers:batch", json=body, headers=auth, timeout=0.3)
        found = client.get(
            f"{handle.target_url}/api/customers", params={"external_id": "C000001"}, headers=auth
        )
        assert found.json()["items"][0]["id"] == "cus_000001"  # the ambiguous write landed
        replay = client.post(f"{handle.target_url}/api/customers:batch", json=body, headers=auth)
        assert replay.json()["results"][0]["status"] == 200
        fired = handle.stats()["fired"]
        assert [f["kind"] for f in fired] == ["timeout_after_write"]


def test_admin_reset_through_handle_and_source_faults() -> None:
    source_plan = FaultPlan(rules=[FaultRule(kind="rate_limit", count=1, retry_after_s=1)])
    with run_sandbox(generate(3, "small"), source_fault_plan=source_plan) as handle, _client() as client:
        first = client.get(f"{handle.source_url}/api/customers")
        assert first.status_code == 429 and first.headers["Retry-After"] == "1"
        assert client.get(f"{handle.source_url}/api/customers").status_code == 200
        handle.reset(seed=2, fault_plan={"rules": [{"kind": "schema_flip", "to_version": "v2"}]})
        assert handle.stats()["seed"] == 2


def test_load_fault_plan_from_yaml_and_json(tmp_path) -> None:
    yaml_path = tmp_path / "plan.yaml"
    yaml_path.write_text("seed: 3\nrules:\n  - kind: rate_limit\n    after_requests: 2\n", encoding="utf-8")
    json_path = tmp_path / "plan.json"
    json_path.write_text('{"rules": [{"kind": "schema_flip", "entity": "subscriptions"}]}', encoding="utf-8")
    assert load_fault_plan(yaml_path) == FaultPlan(
        seed=3, rules=[FaultRule(kind="rate_limit", after_requests=2)]
    )
    assert load_fault_plan(json_path).rules[0].entity == "subscriptions"
    assert load_fault_plan(None) is None


def _sandbox_threads() -> list[str]:
    import threading

    return [t.name for t in threading.enumerate() if t.name.startswith("sandbox-")]


def _port(url: str) -> int:
    return int(url.rsplit(":", 1)[1])


def test_no_thread_leak_and_fixed_ports_are_reusable_immediately() -> None:
    dataset = generate(3, "small")
    with run_sandbox(dataset) as handle:
        assert sorted(_sandbox_threads()) == ["sandbox-legacybill", "sandbox-novabill"]
        ports = (_port(handle.source_url), _port(handle.target_url))
    assert _sandbox_threads() == []
    with run_sandbox(dataset, None, *ports) as again, _client() as client:
        assert (_port(again.source_url), _port(again.target_url)) == ports
        assert client.get(f"{again.source_url}/api/account").status_code == 200
    assert _sandbox_threads() == []


def test_port_conflict_raises_and_stops_the_started_server() -> None:
    dataset = generate(3, "small")
    with run_sandbox(dataset) as handle:
        taken = _port(handle.target_url)
        with pytest.raises(OSError), run_sandbox(dataset, source_port=0, target_port=taken):
            pass  # pragma: no cover
        assert sorted(_sandbox_threads()) == ["sandbox-legacybill", "sandbox-novabill"]
    assert _sandbox_threads() == []


def test_shutdown_is_prompt_with_a_stalled_write_in_flight() -> None:
    """Regression: a timeout_after_write stall held shutdown for the graceful timeout and logged a traceback."""
    import concurrent.futures
    import time

    plan = FaultPlan(rules=[FaultRule(kind="timeout_after_write", delay_s=30)])
    body = {"items": [{"idempotency_key": "k", "payload": {}}]}
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        with run_sandbox(generate(3, "small"), plan) as handle:
            auth = {"Authorization": f"Bearer {handle.target_token}"}
            url = f"{handle.target_url}/api/customers:batch"
            future = pool.submit(httpx.post, url, json=body, headers=auth, timeout=10, trust_env=False)
            time.sleep(0.3)
            assert not future.done()
            leaving = time.monotonic()
        assert time.monotonic() - leaving < 1.5
        assert future.result(timeout=2).status_code == 200  # answered, not cancelled
    assert _sandbox_threads() == []


def test_bind_host_is_configurable_for_containers_and_defaults_to_loopback() -> None:
    dataset = generate(3, "small")
    with run_sandbox(dataset) as handle:
        assert handle.source_url.startswith("http://127.0.0.1:")
    # In a container the servers must listen on all interfaces to be published; the handle
    # still talks to them over loopback.
    with run_sandbox(dataset, bind_host="0.0.0.0") as handle:
        assert handle.target_url.startswith("http://127.0.0.1:")
        with _client() as client:
            assert client.get(f"{handle.target_url}/api/meta").json() == {"api_version": "v1"}
