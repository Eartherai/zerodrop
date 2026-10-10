"""Deterministic failure classification for target and source errors.

`classify_exception` maps a raised connector error to a `FailureClass`;
`classify_batch` turns the per-item results of one NovaBill batch write into a
`BatchVerdict`, deciding whether the failures point at the target contract (the
mapping is wrong for most items: replan) or at individual records (quarantine).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from zerodrop.connectors.errors import SourceError, TargetConnectionError, TargetHTTPError, TargetTimeout
from zerodrop.models import FailureClass

# 422 codes that only a wrong mapping can produce (the field set is the same for every record).
STRUCTURAL_CODES: frozenset[str] = frozenset({"unknown_field", "missing_field"})
# 422 codes that describe a conflict between records, never a contract change.
DATA_ONLY_CODES: frozenset[str] = frozenset({"duplicate_email"})
# Per-item statuses that mean the record is stored in the target.
WRITTEN_STATUSES: frozenset[int] = frozenset({200, 201, 409})


class BudgetExceeded(Exception):
    """An LLM-call, cost or wall-clock cap was reached."""


@dataclass(frozen=True)
class BatchVerdict:
    """Classification of one batch response.

    ``per_item`` lists only the items that were not stored, as ``(index, class)``.
    ``written`` holds the indices stored in the target (201 created, 200 replayed
    idempotency key, 409 already present under another key).
    """

    contract_suspect: bool
    dominant_code: str | None
    per_item: list[tuple[int, FailureClass]] = field(default_factory=list)
    written: list[int] = field(default_factory=list)

    def indices(self, failure: FailureClass) -> list[int]:
        return [index for index, cls in self.per_item if cls == failure]


def classify_status(status: int | None) -> FailureClass:
    """Failure class for an HTTP status (whole request or a single batch item)."""
    if status is None:
        return FailureClass.TRANSIENT
    if status in (401, 403):
        return FailureClass.AUTH
    if status in (408, 429) or status >= 500:
        return FailureClass.TRANSIENT
    if status == 422:
        return FailureClass.DATA
    return FailureClass.UNKNOWN


def classify_exception(exc: BaseException, *, write: bool = True) -> FailureClass:
    """Classify a raised error.

    A timeout or broken connection after the request was sent is AMBIGUOUS_WRITE
    for writes (the target may have committed it) and TRANSIENT for reads.
    """
    if isinstance(exc, BudgetExceeded) or type(exc).__name__ == "BudgetExceeded":  # incl. the agent layer's
        return FailureClass.BUDGET
    if isinstance(exc, TargetHTTPError):
        return classify_status(exc.status)
    if isinstance(exc, TargetTimeout | TargetConnectionError):
        return FailureClass.AMBIGUOUS_WRITE if (exc.sent and write) else FailureClass.TRANSIENT
    if isinstance(exc, SourceError):
        if exc.status in (401, 403):
            return FailureClass.AUTH
        return FailureClass.TRANSIENT if exc.transient else FailureClass.UNKNOWN
    if isinstance(exc, httpx.TimeoutException | httpx.TransportError):
        return FailureClass.AMBIGUOUS_WRITE if write else FailureClass.TRANSIENT
    return FailureClass.UNKNOWN


# The name docs/CONTRACTS.md section 4 uses for the exception classifier.
classify = classify_exception


def contract_signal(
    codes: Sequence[str | None], structural: Iterable[str] = STRUCTURAL_CODES
) -> tuple[bool, str | None]:
    """Decide whether item failures look like a contract (mapping-wide) problem.

    ``codes`` has one entry per evaluated item: its error code, or None if it
    succeeded. Contract when one code covers at least half of the items and at
    least two of them, or when a single evaluated item failed with a structural
    code. Codes in DATA_ONLY_CODES never count. Returns ``(suspect, dominant)``.
    """
    counted = Counter(code for code in codes if code is not None and code not in DATA_ONLY_CODES)
    failing = [code for code in codes if code is not None]
    if not counted:
        return False, _most_common(Counter(failing))
    dominant = _most_common(counted)
    assert dominant is not None
    hits = counted[dominant]
    if len(codes) == 1:
        return dominant in frozenset(structural), dominant
    return hits >= 2 and 2 * hits >= len(codes), dominant


def classify_batch(results: Sequence[Any]) -> BatchVerdict:
    """Classify the per-item results of a batch write.

    Accepts objects with ``index``/``status``/``error`` attributes (the connector's
    `ItemResult`) or equivalent dicts. Items answered 503 were not evaluated by
    the target, so the contract ratio is computed over the other items only.
    """
    rows = [_row(position, result) for position, result in enumerate(results)]
    evaluated = [(index, status, code) for index, status, code in rows if not _not_processed(status)]
    codes = [code if status == 422 else None for _, status, code in evaluated]
    suspect, dominant = contract_signal(codes)
    per_item: list[tuple[int, FailureClass]] = []
    written: list[int] = []
    for index, status, code in rows:
        if status in WRITTEN_STATUSES:
            written.append(index)
        elif status == 422:
            contract = suspect and code not in DATA_ONLY_CODES
            per_item.append((index, FailureClass.CONTRACT if contract else FailureClass.DATA))
        else:
            per_item.append((index, classify_status(status)))
    return BatchVerdict(contract_suspect=suspect, dominant_code=dominant, per_item=per_item, written=written)


def _row(position: int, result: Any) -> tuple[int, int, str | None]:
    if isinstance(result, dict):
        index, status, error = result.get("index", position), result.get("status"), result.get("error")
    else:
        index = getattr(result, "index", position)
        status, error = getattr(result, "status", None), getattr(result, "error", None)
    code = error.get("code") if isinstance(error, dict) else getattr(error, "code", None)
    return int(index), int(status) if status is not None else 0, code


def _not_processed(status: int) -> bool:
    return status == 503


def _most_common(counter: Counter[str]) -> str | None:
    if not counter:
        return None
    return min(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0]
