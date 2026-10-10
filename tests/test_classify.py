from __future__ import annotations

import httpx
import pytest
from hypothesis import given
from hypothesis import strategies as st

from zerodrop.classify import (
    BatchVerdict,
    BudgetExceeded,
    classify_batch,
    classify_exception,
    classify_status,
    contract_signal,
)
from zerodrop.connectors.errors import SourceError, TargetConnectionError, TargetHTTPError, TargetTimeout
from zerodrop.connectors.target import ItemResult
from zerodrop.models import FailureClass, TargetItemError

T, A, C, D, AU, B, U = (
    FailureClass.TRANSIENT,
    FailureClass.AMBIGUOUS_WRITE,
    FailureClass.CONTRACT,
    FailureClass.DATA,
    FailureClass.AUTH,
    FailureClass.BUDGET,
    FailureClass.UNKNOWN,
)


def ok(index: int, status: int = 201) -> ItemResult:
    return ItemResult(index=index, status=status, id=f"cus_{index:06d}")


def err(index: int, code: str, status: int = 422) -> ItemResult:
    return ItemResult(index=index, status=status, error=TargetItemError(code=code, field="f", message="m"))


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (TargetHTTPError(429, 1.0), T),
        (TargetHTTPError(500), T),
        (TargetHTTPError(503), T),
        (TargetHTTPError(408), T),
        (TargetHTTPError(401), AU),
        (TargetHTTPError(403), AU),
        (TargetHTTPError(400), U),
        (TargetHTTPError(404), U),
        (TargetHTTPError(422), D),
        (TargetTimeout(sent=True), A),
        (TargetTimeout(sent=False), T),
        (TargetConnectionError("reset", sent=True), A),
        (TargetConnectionError("refused", sent=False), T),
        (SourceError("slow", status=429, retry_after=0.5), T),
        (SourceError("down", status=503), T),
        (SourceError("timeout", timeout=True), T),
        (SourceError("gone", status=404), U),
        (SourceError("denied", status=401), AU),
        (BudgetExceeded("cap"), B),
        (httpx.ReadTimeout("t"), A),
        (ValueError("bug"), U),
    ],
)
def test_classify_exception_for_writes(exc: BaseException, expected: FailureClass) -> None:
    assert classify_exception(exc) == expected


def test_timeouts_on_reads_are_transient_not_ambiguous() -> None:
    assert classify_exception(TargetTimeout(sent=True), write=False) == T
    assert classify_exception(TargetConnectionError("x", sent=True), write=False) == T
    assert classify_exception(httpx.ReadTimeout("t"), write=False) == T


def test_classify_status_none_is_transient() -> None:
    assert classify_status(None) == T
    assert classify_status(302) == U


def test_all_written_including_replays_and_conflicts() -> None:
    verdict = classify_batch([ok(0), ok(1, 200), ok(2, 409)])
    assert verdict == BatchVerdict(contract_suspect=False, dominant_code=None, per_item=[], written=[0, 1, 2])


def test_per_item_503_is_transient() -> None:
    verdict = classify_batch([ok(0), err(1, "temporarily_unavailable", 503), err(2, "x", 503)])
    assert verdict.per_item == [(1, T), (2, T)]
    assert verdict.written == [0]
    assert not verdict.contract_suspect


def test_isolated_422_is_data() -> None:
    results = [ok(i) for i in range(9)] + [err(9, "invalid_value")]
    verdict = classify_batch(results)
    assert verdict.per_item == [(9, D)]
    assert verdict.dominant_code == "invalid_value"
    assert not verdict.contract_suspect


def test_majority_same_422_code_is_contract() -> None:
    results = [err(i, "unknown_field") for i in range(5)] + [ok(i) for i in range(5, 10)]
    verdict = classify_batch(results)
    assert verdict.contract_suspect
    assert verdict.dominant_code == "unknown_field"
    assert verdict.indices(C) == [0, 1, 2, 3, 4]


def test_below_half_is_data() -> None:
    results = [err(i, "invalid_reference") for i in range(4)] + [ok(i) for i in range(4, 10)]
    verdict = classify_batch(results)
    assert not verdict.contract_suspect
    assert verdict.indices(D) == [0, 1, 2, 3]


def test_mixed_codes_need_one_code_at_half() -> None:
    results = [err(0, "invalid_value"), err(1, "invalid_reference"), err(2, "not_lowercase"), ok(3)]
    assert not classify_batch(results).contract_suspect


def test_two_item_batch_with_one_failure_is_data() -> None:
    verdict = classify_batch([ok(0), err(1, "invalid_value")])
    assert not verdict.contract_suspect
    assert verdict.per_item == [(1, D)]


def test_contract_batch_marks_other_422_codes_as_contract_too() -> None:
    results = [err(0, "unknown_field"), err(1, "unknown_field"), err(2, "invalid_value")]
    verdict = classify_batch(results)
    assert verdict.contract_suspect
    assert verdict.per_item == [(0, C), (1, C), (2, C)]


@pytest.mark.parametrize("code", ["unknown_field", "missing_field"])
def test_single_item_structural_error_is_contract(code: str) -> None:
    verdict = classify_batch([err(0, code)])
    assert verdict.contract_suspect
    assert verdict.per_item == [(0, C)]


@pytest.mark.parametrize("code", ["invalid_value", "invalid_reference", "not_lowercase", "duplicate_email"])
def test_single_item_value_error_is_data(code: str) -> None:
    verdict = classify_batch([err(0, code)])
    assert not verdict.contract_suspect
    assert verdict.per_item == [(0, D)]


def test_duplicate_email_never_suggests_a_contract_change() -> None:
    results = [err(i, "duplicate_email") for i in range(6)] + [ok(6)]
    verdict = classify_batch(results)
    assert not verdict.contract_suspect
    assert verdict.dominant_code == "duplicate_email"
    assert verdict.indices(D) == list(range(6))


def test_unprocessed_503_items_do_not_dilute_the_contract_ratio() -> None:
    # partial accept: 3 items evaluated (all unknown_field), 7 never processed.
    results = [err(i, "unknown_field") for i in range(3)] + [
        err(i, "temporarily_unavailable", 503) for i in range(3, 10)
    ]
    verdict = classify_batch(results)
    assert verdict.contract_suspect
    assert verdict.indices(C) == [0, 1, 2]
    assert verdict.indices(T) == list(range(3, 10))


def test_single_evaluated_item_among_503s_uses_the_single_item_rule() -> None:
    results = [err(0, "missing_field"), err(1, "temporarily_unavailable", 503)]
    assert classify_batch(results).contract_suspect


def test_per_item_auth_and_unknown_statuses() -> None:
    verdict = classify_batch([err(0, "invalid_token", 401), err(1, "bad", 400), err(2, "x", 500)])
    assert verdict.per_item == [(0, AU), (1, U), (2, T)]


def test_accepts_plain_dicts() -> None:
    results = [
        {"index": 0, "status": 422, "id": None, "error": {"code": "unknown_field", "field": "plan_code"}},
        {"index": 1, "status": 422, "id": None, "error": {"code": "unknown_field", "field": "plan_code"}},
        {"index": 2, "status": 201, "id": "sub_000001", "error": None},
    ]
    verdict = classify_batch(results)
    assert verdict.contract_suspect
    assert verdict.written == [2]


def test_contract_signal_ties_break_alphabetically() -> None:
    suspect, dominant = contract_signal(["b_code", "a_code", "b_code", "a_code"])
    assert suspect
    assert dominant == "a_code"


def test_contract_signal_custom_structural_codes() -> None:
    assert contract_signal(["missing_param"], structural={"missing_param"}) == (True, "missing_param")
    assert contract_signal(["missing_param"]) == (False, "missing_param")
    assert contract_signal([None, None]) == (False, None)


codes_strategy = st.lists(
    st.one_of(st.none(), st.sampled_from(["unknown_field", "invalid_value", "duplicate_email"])),
    min_size=1,
    max_size=60,
)


@given(codes_strategy)
def test_contract_signal_matches_its_definition(codes: list[str | None]) -> None:
    suspect, dominant = contract_signal(codes)
    eligible = [c for c in codes if c is not None and c != "duplicate_email"]
    if not eligible:
        assert not suspect
        return
    best = max(eligible.count(c) for c in set(eligible))
    assert dominant is not None and eligible.count(dominant) == best
    if len(codes) == 1:
        assert suspect == (dominant == "unknown_field")
    else:
        assert suspect == (best >= 2 and 2 * best >= len(codes))


@given(
    st.lists(
        st.sampled_from([(201, None), (200, None), (409, None), (503, "temporarily_unavailable")])
        | st.sampled_from([(422, "invalid_value"), (422, "unknown_field"), (422, "duplicate_email")]),
        min_size=1,
        max_size=50,
    )
)
def test_classify_batch_partitions_every_item(rows: list[tuple[int, str | None]]) -> None:
    results = [
        ItemResult(
            index=i,
            status=status,
            id="x" if code is None else None,
            error=None if code is None else TargetItemError(code=code),
        )
        for i, (status, code) in enumerate(rows)
    ]
    verdict = classify_batch(results)
    failed = [index for index, _ in verdict.per_item]
    assert sorted(failed + verdict.written) == list(range(len(rows)))
    for index, cls in verdict.per_item:
        status, code = rows[index]
        if status == 503:
            assert cls == T
        elif code == "duplicate_email":
            assert cls == D
        else:
            assert cls == (C if verdict.contract_suspect else D)


def test_contract_name_classify_is_the_exception_classifier() -> None:
    from zerodrop.classify import classify, classify_exception

    assert classify is classify_exception
    assert classify(TargetHTTPError(429, 1.0)) == FailureClass.TRANSIENT
