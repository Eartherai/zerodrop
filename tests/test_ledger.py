from __future__ import annotations

import itertools
import sqlite3
import threading
from pathlib import Path

import pytest

from zerodrop.ledger import Ledger
from zerodrop.models import (
    Entity,
    FieldMapping,
    MappingSpec,
    PreservationContract,
    QuarantineItem,
    ReconciliationReport,
    RecordState,
    RunStatus,
)


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    ticks = itertools.count(1000)
    with Ledger(tmp_path / "ledger.db", clock=lambda: float(next(ticks))) as led:
        yield led


def spec(entity: Entity = Entity.customers, version: int = 1, target: str = "external_id") -> MappingSpec:
    return MappingSpec(
        entity=entity,
        version=version,
        target_api_version="v1",
        fields=[FieldMapping(target=target, source="cust_id")],
    )


def test_create_and_get_run(ledger: Ledger) -> None:
    contract = PreservationContract(money_by_currency=False)
    run_id = ledger.create_run("move billing", "happy", contract)
    run = ledger.get_run(run_id)
    assert run is not None
    assert run.run_id == run_id and run.goal == "move billing" and run.scenario == "happy"
    assert run.status == RunStatus.CREATED
    assert run.agent_claimed_status is None
    assert run.contract() == contract
    assert run.report() is None
    assert ledger.get_run("nope") is None
    assert ledger.progress(run_id) == {"customers": False, "subscriptions": False, "invoices": False}


def test_explicit_run_id_and_listing(ledger: Ledger) -> None:
    ledger.create_run("a", run_id="run_a")
    ledger.create_run("b", run_id="run_b")
    assert [r.run_id for r in ledger.list_runs()] == ["run_b", "run_a"]
    with pytest.raises(sqlite3.IntegrityError):
        ledger.create_run("dup", run_id="run_a")


def test_status_claim_plan_usage_report_error(ledger: Ledger) -> None:
    run_id = ledger.create_run("g")
    ledger.set_status(run_id, RunStatus.EXECUTING)
    ledger.set_agent_claim(run_id, RunStatus.SUCCESS)
    ledger.set_plan(run_id, '{"x": 1}')
    ledger.set_llm_usage(run_id, 3, 0.25)
    report = ReconciliationReport(run_id=run_id, status=RunStatus.PARTIAL_SUCCESS, checks=[])
    ledger.set_report(run_id, report)
    ledger.set_status(run_id, RunStatus.FAILED, error="boom")
    run = ledger.get_run(run_id)
    assert run is not None
    assert run.status == RunStatus.FAILED and run.error == "boom"
    assert run.agent_claimed_status == RunStatus.SUCCESS
    assert run.plan_json == '{"x": 1}'
    assert (run.llm_calls, run.cost_usd) == (3, 0.25)
    assert run.report() == report
    assert run.updated_at > run.created_at
    ledger.set_error(run_id, None)
    assert ledger.get_run(run_id).error is None  # type: ignore[union-attr]


def test_events_have_monotonic_seq_per_run(ledger: Ledger) -> None:
    a = ledger.create_run("a")
    b = ledger.create_run("b")
    e1 = ledger.append_event(a, "state", "start", state=RunStatus.DISCOVERING)
    e2 = ledger.append_event(a, "batch", "b1", entity="customers", data={"written": 5})
    f1 = ledger.append_event(b, "info", "other run")
    e3 = ledger.append_event(a, "verify", "done", data={"nested": {"k": [1, 2]}})
    assert [e1.seq, e2.seq, e3.seq] == [1, 2, 3]
    assert f1.seq == 1
    assert e2.entity == Entity.customers and e2.data == {"written": 5}
    assert e1.state == RunStatus.DISCOVERING
    assert ledger.events_since(a) == [e1, e2, e3]
    assert ledger.events_since(a, after_seq=1) == [e2, e3]
    assert ledger.events_since(a, after_seq=1, limit=1) == [e2]
    assert ledger.events_since(a, after_seq=3) == []


def test_event_data_is_json_safe(ledger: Ledger) -> None:
    run_id = ledger.create_run("g")
    event = ledger.append_event(run_id, "info", "odd data", data={"path": Path("/x"), "n": 1})
    assert event.data == {"path": "/x", "n": 1}


def test_concurrent_appends_get_unique_seqs(ledger: Ledger) -> None:
    run_id = ledger.create_run("g")

    def worker() -> None:
        for _ in range(25):
            ledger.append_event(run_id, "info", "tick")

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    seqs = [e.seq for e in ledger.events_since(run_id)]
    assert seqs == list(range(1, 101))


def test_mapping_versions_never_reused(ledger: Ledger) -> None:
    run_id = ledger.create_run("g")
    assert ledger.latest_mapping(run_id, "customers") is None
    v1 = ledger.save_mapping(run_id, spec(version=1))
    v2 = ledger.save_mapping(run_id, spec(version=1, target="given_name"))  # stale version is bumped
    v5 = ledger.save_mapping(run_id, spec(version=5))
    assert (v1.version, v2.version, v5.version) == (1, 2, 5)
    assert ledger.latest_mapping(run_id, "customers") == v5
    assert [m.version for m in ledger.mapping_history(run_id, "customers")] == [1, 2, 5]
    assert ledger.latest_mapping(run_id, Entity.subscriptions) is None


def test_record_lifecycle_and_id_map(ledger: Ledger) -> None:
    run_id = ledger.create_run("g")
    ledger.ensure_records(run_id, "customers", ["C1", "C2", "C3"], mapping_version=1)
    ledger.mark_attempts(run_id, "customers", ["C1", "C2"])
    ledger.mark_attempt(run_id, "customers", "C2", error="503")
    ledger.mark_written(run_id, "customers", "C1", "cus_1", mapping_version=2)
    ledger.mark_quarantined(run_id, "customers", "C2", "duplicate_email: email: taken")
    assert ledger.record_states(run_id, "customers") == {
        "C1": RecordState.WRITTEN,
        "C2": RecordState.QUARANTINED,
        "C3": RecordState.PENDING,
    }
    assert ledger.id_map(run_id, "customers", "C1") == "cus_1"
    assert ledger.id_map(run_id, "customers", "C2") is None
    assert ledger.id_map(run_id, "customers", "C3") is None
    c1 = ledger.record(run_id, "customers", "C1")
    c2 = ledger.record(run_id, "customers", "C2")
    assert c1 is not None and c1["attempts"] == 1 and c1["mapping_version"] == 2 and c1["last_error"] is None
    assert c2 is not None and c2["attempts"] == 2


def test_ensure_records_does_not_reset_existing_rows(ledger: Ledger) -> None:
    run_id = ledger.create_run("g")
    ledger.mark_written(run_id, "customers", "C1", "cus_1")
    ledger.ensure_records(run_id, "customers", ["C1", "C2"], mapping_version=3)
    assert ledger.record_states(run_id, "customers") == {"C1": RecordState.WRITTEN, "C2": RecordState.PENDING}


def test_written_records_are_never_downgraded(ledger: Ledger) -> None:
    run_id = ledger.create_run("g")
    ledger.mark_written(run_id, "invoices", "I1", "inv_1")
    ledger.mark_quarantined(run_id, "invoices", "I1", "late failure")
    ledger.mark_failed(run_id, "invoices", "I1", "late failure")
    assert ledger.record_states(run_id, "invoices") == {"I1": RecordState.WRITTEN}
    assert ledger.id_map(run_id, "invoices", "I1") == "inv_1"


def test_mark_written_many_and_failed(ledger: Ledger) -> None:
    run_id = ledger.create_run("g")
    ledger.mark_failed(run_id, "subscriptions", "S9", "exhausted")
    ledger.mark_written_many(run_id, "subscriptions", [("S1", "sub_1"), ("S2", "sub_2"), ("S9", "sub_9")])
    assert ledger.record_states(run_id, "subscriptions") == {
        "S1": RecordState.WRITTEN,
        "S2": RecordState.WRITTEN,
        "S9": RecordState.WRITTEN,
    }
    assert ledger.record(run_id, "subscriptions", "S9")["last_error"] is None  # type: ignore[index]


def test_counts_and_quarantine_listing(ledger: Ledger) -> None:
    run_id = ledger.create_run("g")
    other = ledger.create_run("other")
    ledger.ensure_records(run_id, "customers", ["C1", "C2", "C3", "C4"])
    ledger.mark_written(run_id, "customers", "C1", "cus_1")
    ledger.mark_quarantined(run_id, "customers", "C2", "duplicate_email: x")
    ledger.mark_failed(run_id, "customers", "C3", "boom")
    ledger.mark_quarantined(run_id, "invoices", "I7", "invalid_reference: customer_id: missing")
    ledger.mark_quarantined(other, "invoices", "I8", "elsewhere")
    counts = ledger.counts(run_id)
    assert counts["customers"] == {"total": 4, "written": 1, "quarantined": 1, "failed": 1, "pending": 1}
    assert counts["invoices"] == {"total": 1, "written": 0, "quarantined": 1, "failed": 0, "pending": 0}
    assert counts["subscriptions"]["total"] == 0
    assert ledger.quarantined_items(run_id) == [
        QuarantineItem(entity=Entity.customers, source_id="C2", reason="duplicate_email: x"),
        QuarantineItem(
            entity=Entity.invoices, source_id="I7", reason="invalid_reference: customer_id: missing"
        ),
    ]


def test_progress_flags(ledger: Ledger) -> None:
    run_id = ledger.create_run("g")
    assert not ledger.entity_done(run_id, "customers")
    ledger.set_entity_done(run_id, "customers")
    assert ledger.entity_done(run_id, Entity.customers)
    ledger.set_entity_done(run_id, "customers", done=False)
    assert not ledger.entity_done(run_id, "customers")


def test_state_survives_reopening_the_file(tmp_path: Path) -> None:
    path = tmp_path / "durable.db"
    first = Ledger(path)
    run_id = first.create_run("g")
    first.mark_written(run_id, "customers", "C1", "cus_1")
    first.append_event(run_id, "info", "before crash")
    first.save_mapping(run_id, spec())
    first.close()
    second = Ledger(path)
    assert second.id_map(run_id, "customers", "C1") == "cus_1"
    assert second.append_event(run_id, "info", "after restart").seq == 2
    assert second.latest_mapping(run_id, "customers") == spec()
    assert second._conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    second.close()


def test_two_connections_on_one_file_share_state(tmp_path: Path) -> None:
    path = tmp_path / "shared.db"
    writer, reader = Ledger(path), Ledger(path)
    run_id = writer.create_run("g")
    writer.append_event(run_id, "info", "hello")
    assert [e.message for e in reader.events_since(run_id)] == ["hello"]
    writer.close()
    reader.close()


def test_in_memory_ledger_works() -> None:
    with Ledger() as led:
        run_id = led.create_run("g")
        led.mark_written(run_id, "customers", "C1", "cus_1")
        assert led.counts(run_id)["customers"]["written"] == 1
