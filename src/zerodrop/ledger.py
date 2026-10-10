"""Durable run ledger on SQLite (WAL): runs, per-record states, events, mapping versions, progress.

One connection guarded by a re-entrant lock, so the engine thread and API
readers (e.g. an SSE stream) can share a `Ledger`. Every write commits before
the method returns: after a crash the ledger reflects every completed call.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from zerodrop.models import (
    ENTITY_ORDER,
    EventKind,
    MappingSpec,
    PreservationContract,
    QuarantineItem,
    ReconciliationReport,
    RecordState,
    RunEvent,
    RunStatus,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    scenario TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    agent_claimed_status TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    plan_json TEXT,
    llm_calls INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    error TEXT,
    contract_json TEXT,
    report_json TEXT
);
CREATE TABLE IF NOT EXISTS records (
    run_id TEXT NOT NULL,
    entity TEXT NOT NULL,
    source_id TEXT NOT NULL,
    state TEXT NOT NULL,
    target_id TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    mapping_version INTEGER,
    PRIMARY KEY (run_id, entity, source_id)
);
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    state TEXT,
    entity TEXT,
    message TEXT NOT NULL,
    data_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS mappings (
    run_id TEXT NOT NULL,
    entity TEXT NOT NULL,
    version INTEGER NOT NULL,
    spec_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (run_id, entity, version)
);
CREATE TABLE IF NOT EXISTS progress (
    run_id TEXT NOT NULL,
    entity TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, entity)
);
"""


class RunRecord(BaseModel):
    """One row of the `runs` table."""

    run_id: str
    goal: str
    scenario: str = ""
    status: RunStatus
    agent_claimed_status: RunStatus | None = None
    created_at: float
    updated_at: float
    plan_json: str | None = None
    llm_calls: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    contract_json: str | None = None
    report_json: str | None = None

    def contract(self) -> PreservationContract:
        if not self.contract_json:
            return PreservationContract()
        return PreservationContract.model_validate_json(self.contract_json)

    def report(self) -> ReconciliationReport | None:
        if not self.report_json:
            return None
        return ReconciliationReport.model_validate_json(self.report_json)


class Ledger:
    def __init__(self, path: str | Path = ":memory:", clock: Callable[[], float] = time.time) -> None:
        self.path = str(path)
        self._clock = clock
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            if self.path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # -- lifecycle -------------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> Ledger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock, self._conn:
            yield self._conn

    def _query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    # -- runs ------------------------------------------------------------------

    def create_run(
        self,
        goal: str,
        scenario: str = "",
        contract: PreservationContract | None = None,
        run_id: str | None = None,
    ) -> str:
        run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        now = self._clock()
        contract_json = (contract or PreservationContract()).model_dump_json()
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO runs (run_id, goal, scenario, status, created_at, updated_at, contract_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, goal, scenario, RunStatus.CREATED.value, now, now, contract_json),
            )
            for entity in ENTITY_ORDER:
                conn.execute(
                    "INSERT OR IGNORE INTO progress (run_id, entity, done) VALUES (?, ?, 0)",
                    (run_id, entity.value),
                )
        return run_id

    def get_run(self, run_id: str) -> RunRecord | None:
        rows = self._query("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        return RunRecord.model_validate(dict(rows[0])) if rows else None

    def list_runs(self, limit: int = 50) -> list[RunRecord]:
        rows = self._query("SELECT * FROM runs ORDER BY created_at DESC, run_id LIMIT ?", (limit,))
        return [RunRecord.model_validate(dict(row)) for row in rows]

    def set_status(self, run_id: str, status: RunStatus, error: str | None = None) -> None:
        with self._tx() as conn:
            if error is None:
                conn.execute(
                    "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                    (status.value, self._clock(), run_id),
                )
            else:
                conn.execute(
                    "UPDATE runs SET status = ?, error = ?, updated_at = ? WHERE run_id = ?",
                    (status.value, error, self._clock(), run_id),
                )

    def set_agent_claim(self, run_id: str, status: RunStatus | None) -> None:
        self._update_run(run_id, agent_claimed_status=None if status is None else status.value)

    def set_plan(self, run_id: str, plan_json: str) -> None:
        self._update_run(run_id, plan_json=plan_json)

    def set_llm_usage(self, run_id: str, calls: int, cost_usd: float) -> None:
        self._update_run(run_id, llm_calls=int(calls), cost_usd=float(cost_usd))

    def set_report(self, run_id: str, report: ReconciliationReport) -> None:
        self._update_run(run_id, report_json=report.model_dump_json())

    def set_error(self, run_id: str, error: str | None) -> None:
        self._update_run(run_id, error=error)

    def _update_run(self, run_id: str, **columns: Any) -> None:
        assignments = ", ".join(f"{name} = ?" for name in columns)
        with self._tx() as conn:
            conn.execute(
                f"UPDATE runs SET {assignments}, updated_at = ? WHERE run_id = ?",
                (*columns.values(), self._clock(), run_id),
            )

    # -- events ----------------------------------------------------------------

    def append_event(
        self,
        run_id: str,
        kind: EventKind,
        message: str,
        state: RunStatus | None = None,
        entity: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> RunEvent:
        ts = self._clock()
        data_json = json.dumps(data or {}, sort_keys=True, default=str)
        with self._tx() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE run_id = ?", (run_id,)
            ).fetchone()
            seq = int(row[0])
            conn.execute(
                "INSERT INTO events (run_id, seq, ts, kind, state, entity, message, data_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    seq,
                    ts,
                    kind,
                    None if state is None else state.value,
                    None if entity is None else str(entity),
                    message,
                    data_json,
                ),
            )
        return _event(run_id, seq, ts, kind, state, entity, message, data_json)

    def events_since(self, run_id: str, after_seq: int = 0, limit: int | None = None) -> list[RunEvent]:
        sql = "SELECT * FROM events WHERE run_id = ? AND seq > ? ORDER BY seq"
        params: list[Any] = [run_id, after_seq]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return [
            _event(
                row["run_id"],
                row["seq"],
                row["ts"],
                row["kind"],
                None if row["state"] is None else RunStatus(row["state"]),
                row["entity"],
                row["message"],
                row["data_json"],
            )
            for row in self._query(sql, params)
        ]

    # -- mappings --------------------------------------------------------------

    def save_mapping(self, run_id: str, spec: MappingSpec) -> MappingSpec:
        """Store a mapping version; the version is bumped past any stored one, never reused."""
        with self._tx() as conn:
            row = conn.execute(
                "SELECT MAX(version) FROM mappings WHERE run_id = ? AND entity = ?",
                (run_id, spec.entity.value),
            ).fetchone()
            latest = row[0]
            version = spec.version if latest is None or spec.version > latest else latest + 1
            stored = spec.model_copy(update={"version": version})
            conn.execute(
                "INSERT INTO mappings (run_id, entity, version, spec_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (run_id, spec.entity.value, version, stored.model_dump_json(), self._clock()),
            )
        return stored

    def latest_mapping(self, run_id: str, entity: str) -> MappingSpec | None:
        rows = self._query(
            "SELECT spec_json FROM mappings WHERE run_id = ? AND entity = ? ORDER BY version DESC LIMIT 1",
            (run_id, str(entity)),
        )
        return MappingSpec.model_validate_json(rows[0]["spec_json"]) if rows else None

    def mapping_history(self, run_id: str, entity: str) -> list[MappingSpec]:
        rows = self._query(
            "SELECT spec_json FROM mappings WHERE run_id = ? AND entity = ? ORDER BY version",
            (run_id, str(entity)),
        )
        return [MappingSpec.model_validate_json(row["spec_json"]) for row in rows]

    # -- records ---------------------------------------------------------------

    def ensure_records(
        self, run_id: str, entity: str, source_ids: Iterable[str], mapping_version: int | None = None
    ) -> None:
        """Insert PENDING rows for ids the ledger has not seen; existing rows are untouched."""
        with self._tx() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO records (run_id, entity, source_id, state, mapping_version)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    (run_id, str(entity), sid, RecordState.PENDING.value, mapping_version)
                    for sid in source_ids
                ],
            )

    def mark_written(
        self,
        run_id: str,
        entity: str,
        source_id: str,
        target_id: str,
        mapping_version: int | None = None,
    ) -> None:
        self.mark_written_many(run_id, entity, [(source_id, target_id)], mapping_version)

    def mark_written_many(
        self,
        run_id: str,
        entity: str,
        pairs: Iterable[tuple[str, str]],
        mapping_version: int | None = None,
    ) -> None:
        """Record (source_id, target_id) pairs as WRITTEN in one transaction."""
        rows = [
            (run_id, str(entity), sid, RecordState.WRITTEN.value, tid, mapping_version) for sid, tid in pairs
        ]
        with self._tx() as conn:
            conn.executemany(
                "INSERT INTO records (run_id, entity, source_id, state, target_id, mapping_version)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (run_id, entity, source_id) DO UPDATE SET"
                " state = excluded.state, target_id = excluded.target_id, last_error = NULL,"
                " mapping_version = COALESCE(excluded.mapping_version, records.mapping_version)",
                rows,
            )

    def mark_quarantined(self, run_id: str, entity: str, source_id: str, reason: str) -> None:
        self._set_state(run_id, entity, [(source_id, reason)], RecordState.QUARANTINED)

    def mark_failed(self, run_id: str, entity: str, source_id: str, error: str) -> None:
        self._set_state(run_id, entity, [(source_id, error)], RecordState.FAILED)

    def _set_state(
        self, run_id: str, entity: str, items: Iterable[tuple[str, str]], state: RecordState
    ) -> None:
        with self._tx() as conn:
            conn.executemany(
                "INSERT INTO records (run_id, entity, source_id, state, last_error) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (run_id, entity, source_id) DO UPDATE SET"
                " state = excluded.state, last_error = excluded.last_error"
                " WHERE records.state != 'WRITTEN'",
                [(run_id, str(entity), sid, state.value, reason) for sid, reason in items],
            )

    def mark_attempt(self, run_id: str, entity: str, source_id: str, error: str | None = None) -> None:
        self.mark_attempts(run_id, entity, [source_id], error)

    def mark_attempts(
        self, run_id: str, entity: str, source_ids: Iterable[str], error: str | None = None
    ) -> None:
        with self._tx() as conn:
            conn.executemany(
                "UPDATE records SET attempts = attempts + 1, last_error = COALESCE(?, last_error)"
                " WHERE run_id = ? AND entity = ? AND source_id = ?",
                [(error, run_id, str(entity), sid) for sid in source_ids],
            )

    def record_states(self, run_id: str, entity: str) -> dict[str, RecordState]:
        rows = self._query(
            "SELECT source_id, state FROM records WHERE run_id = ? AND entity = ?", (run_id, str(entity))
        )
        return {row["source_id"]: RecordState(row["state"]) for row in rows}

    def record(self, run_id: str, entity: str, source_id: str) -> dict[str, Any] | None:
        rows = self._query(
            "SELECT * FROM records WHERE run_id = ? AND entity = ? AND source_id = ?",
            (run_id, str(entity), source_id),
        )
        return dict(rows[0]) if rows else None

    def id_map(self, run_id: str, entity: str, source_id: str) -> str | None:
        rows = self._query(
            "SELECT target_id FROM records WHERE run_id = ? AND entity = ? AND source_id = ? AND state = ?",
            (run_id, str(entity), source_id, RecordState.WRITTEN.value),
        )
        return rows[0]["target_id"] if rows else None

    def quarantined_items(self, run_id: str) -> list[QuarantineItem]:
        rows = self._query(
            "SELECT entity, source_id, last_error FROM records WHERE run_id = ? AND state = ?"
            " ORDER BY entity, source_id",
            (run_id, RecordState.QUARANTINED.value),
        )
        items = [
            QuarantineItem(entity=row["entity"], source_id=row["source_id"], reason=row["last_error"] or "")
            for row in rows
        ]
        order = {entity.value: i for i, entity in enumerate(ENTITY_ORDER)}
        return sorted(items, key=lambda q: (order.get(q.entity.value, 99), q.source_id))

    def counts(self, run_id: str) -> dict[str, dict[str, int]]:
        """Per entity: total, written, quarantined, failed, pending (never-resolved rows)."""
        result = {
            entity.value: {"total": 0, "written": 0, "quarantined": 0, "failed": 0, "pending": 0}
            for entity in ENTITY_ORDER
        }
        rows = self._query(
            "SELECT entity, state, COUNT(*) AS n FROM records WHERE run_id = ? GROUP BY entity, state",
            (run_id,),
        )
        keys = {
            RecordState.WRITTEN.value: "written",
            RecordState.QUARANTINED.value: "quarantined",
            RecordState.FAILED.value: "failed",
            RecordState.PENDING.value: "pending",
        }
        for row in rows:
            bucket = result.setdefault(
                row["entity"], {"total": 0, "written": 0, "quarantined": 0, "failed": 0, "pending": 0}
            )
            bucket[keys[row["state"]]] += row["n"]
            bucket["total"] += row["n"]
        return result

    # -- progress --------------------------------------------------------------

    def set_entity_done(self, run_id: str, entity: str, done: bool = True) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO progress (run_id, entity, done) VALUES (?, ?, ?)"
                " ON CONFLICT (run_id, entity) DO UPDATE SET done = excluded.done",
                (run_id, str(entity), int(done)),
            )

    def entity_done(self, run_id: str, entity: str) -> bool:
        rows = self._query("SELECT done FROM progress WHERE run_id = ? AND entity = ?", (run_id, str(entity)))
        return bool(rows and rows[0]["done"])

    def progress(self, run_id: str) -> dict[str, bool]:
        rows = self._query("SELECT entity, done FROM progress WHERE run_id = ?", (run_id,))
        return {row["entity"]: bool(row["done"]) for row in rows}


def _event(
    run_id: str,
    seq: int,
    ts: float,
    kind: str,
    state: RunStatus | None,
    entity: str | None,
    message: str,
    data_json: str,
) -> RunEvent:
    return RunEvent.model_validate(
        {
            "run_id": run_id,
            "seq": seq,
            "ts": ts,
            "kind": kind,
            "message": message,
            "state": state,
            "entity": entity,
            "data": json.loads(data_json),
        }
    )
