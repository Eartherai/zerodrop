from __future__ import annotations

import ast
import copy
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from zerodrop.models import (
    CheckResult,
    Entity,
    PreservationContract,
    QuarantineItem,
    ReconciliationReport,
    RunStatus,
)
from zerodrop.sandbox import fixtures
from zerodrop.verifier import verify as verify_module
from zerodrop.verifier.verify import is_data_reason, minor_units, report_hash, to_minor, verify

FORBIDDEN_PACKAGES = (
    "zerodrop.engine",
    "zerodrop.dsl",
    "zerodrop.ledger",
    "zerodrop.agent",
    "zerodrop.classify",
    "zerodrop.sandbox",
)
CUSTOMER_KEYS = (
    "external_id",
    "given_name",
    "family_name",
    "email",
    "country",
    "status",
    "created_at",
    "notes",
)
PRICES = [
    {
        "id": "price_pro_m",
        "lookup_key": "PRO_M",
        "currency": "usd",
        "unit_amount_minor": 2900,
        "interval": "month",
    }
]


# ---------------------------------------------------------------------------
# Fakes and helpers
# ---------------------------------------------------------------------------


class FakeSource:
    def __init__(self, records: dict[str, list[dict[str, Any]]], account: dict[str, Any]) -> None:
        self.records = records
        self._account = account

    def iter_records(self, entity: str) -> Any:
        yield from copy.deepcopy(self.records[entity])

    def account(self) -> dict[str, Any]:
        return dict(self._account)


class FakeTarget:
    def __init__(
        self,
        records: dict[str, list[dict[str, Any]]],
        prices: list[dict[str, Any]],
        failures: list[Exception] | None = None,
    ) -> None:
        self.records = records
        self._prices = prices
        self.failures = list(failures or [])

    def list_all(self, entity: str) -> list[dict[str, Any]]:
        if self.failures:
            raise self.failures.pop(0)
        return copy.deepcopy(self.records[entity])

    def prices(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._prices)


class FakeHTTPError(Exception):
    def __init__(self, status: int, retry_after: float | None = None) -> None:
        super().__init__(f"target responded {status}")
        self.status = status
        self.retry_after = retry_after


def target_from_golden(golden: dict[str, Any], v2_from: int | None = None) -> dict[str, list[dict[str, Any]]]:
    """A correct NovaBill state built from the fixture's golden records (independent of verify.py).

    Subscriptions after position `v2_from` carry `price_id` (written after a schema flip).
    """
    cust_ids: dict[str, str] = {}
    customers = []
    for n, g in enumerate(golden["customers"], start=1):
        cust_ids[g["external_id"]] = f"cus_{n:06d}"
        customers.append({"id": cust_ids[g["external_id"]], **{k: g[k] for k in CUSTOMER_KEYS}})
    sub_ids: dict[str, str] = {}
    subscriptions = []
    for n, g in enumerate(golden["subscriptions"], start=1):
        sub_ids[g["external_id"]] = f"sub_{n:06d}"
        v2 = v2_from is not None and n > v2_from
        plan = {"price_id": g["price_id"]} if v2 else {"plan_code": g["plan_code"]}
        subscriptions.append(
            {
                "id": sub_ids[g["external_id"]],
                "external_id": g["external_id"],
                "customer_id": cust_ids[g["customer_external_id"]],
                **plan,
                "status": g["status"],
                "start_at": g["start_at"],
                "quantity": g["quantity"],
            }
        )
    invoices = []
    for n, g in enumerate(golden["invoices"], start=1):
        sub = g["subscription_external_id"]
        invoices.append(
            {
                "id": f"inv_{n:06d}",
                "external_id": g["external_id"],
                "customer_id": cust_ids[g["customer_external_id"]],
                "subscription_id": sub_ids[sub] if sub else None,
                "amount_minor": g["amount_minor"],
                "currency": g["currency"],
                "issued_at": g["issued_at"],
                "status": g["status"],
            }
        )
    return {"customers": customers, "subscriptions": subscriptions, "invoices": invoices}


@cache
def _dataset(seed: int, size: str = "small", orphans: int = 0, duplicates: int = 0) -> fixtures.Dataset:
    return fixtures.generate(seed, size, orphan_invoices=orphans, duplicate_emails=duplicates)


@dataclass
class Scenario:
    dataset: fixtures.Dataset
    source: FakeSource
    target: FakeTarget
    golden_path: str

    @property
    def records(self) -> dict[str, list[dict[str, Any]]]:
        return self.target.records


def make_scenario(tmp_path: Path, seed: int = 7, v2_from: int | None = None, **opts: Any) -> Scenario:
    ds = _dataset(seed, **opts)
    golden_path = ds.write_golden(tmp_path / "golden.json")
    source = FakeSource(copy.deepcopy(ds.source), ds.account)
    target = FakeTarget(target_from_golden(ds.golden, v2_from), copy.deepcopy(ds.prices))
    return Scenario(ds, source, target, str(golden_path))


def run(
    sc: Scenario, quarantined: list[QuarantineItem] | None = None, golden: bool = True, **contract: Any
) -> ReconciliationReport:
    pc = PreservationContract(golden_path=sc.golden_path if golden else None, **contract)
    return verify("run-1", sc.source, sc.target, pc, quarantined or [], sleep=lambda _s: None)


def failed(report: ReconciliationReport) -> set[tuple[str, str | None]]:
    return {(c.name, c.entity.value if c.entity else None) for c in report.checks if not c.passed}


def check(report: ReconciliationReport, name: str, entity: str | None = None) -> CheckResult:
    return next(
        c for c in report.checks if c.name == name and (c.entity.value if c.entity else None) == entity
    )


def orphan_item(sc: Scenario, reason: str = "invalid_reference: customer does not exist") -> QuarantineItem:
    expected = sc.dataset.golden["expected_quarantine"]
    (orphan,) = [q for q in expected if q["entity"] == "invoices"]
    return QuarantineItem(entity=Entity.invoices, source_id=orphan["source_id"], reason=reason)


# ---------------------------------------------------------------------------
# Status decisions on fixture data
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("seed", "size"), [(7, "small"), (0, "small"), (42, "small"), (3, "demo")])
def test_perfect_migration_is_success(tmp_path: Path, seed: int, size: str) -> None:
    sc = make_scenario(tmp_path, seed=seed, size=size)
    report = run(sc)
    assert failed(report) == set()
    assert report.status is RunStatus.SUCCESS
    assert report.source_counts == report.target_counts
    assert report.source_counts["customers"] == len(sc.dataset.golden["customers"])
    assert report.money_source_minor == report.money_target_minor
    assert set(report.money_source_minor) <= {"INR", "USD", "EUR", "JPY"}
    names = {c.name for c in report.checks}
    assert {"count", "source_fidelity", "money_by_currency", "golden_records", "golden_quarantine"} <= names
    assert report.report_hash == report_hash(report.checks)


def test_perfect_migration_without_golden_is_success(tmp_path: Path) -> None:
    report = run(make_scenario(tmp_path), golden=False)
    assert report.status is RunStatus.SUCCESS
    assert not any(c.name.startswith("golden") for c in report.checks)


def test_subscriptions_written_across_a_schema_flip_verify(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path, v2_from=10)
    assert any("price_id" in s for s in sc.records["subscriptions"])
    assert any("plan_code" in s for s in sc.records["subscriptions"])
    assert run(sc).status is RunStatus.SUCCESS


def test_one_missing_record_fails(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    lost = sc.records["invoices"].pop(5)
    report = run(sc)
    assert report.status is RunStatus.FAILED
    assert {("count", "invoices"), ("missing_records_quarantined", "invoices")} <= failed(report)
    assert lost["external_id"] in check(report, "missing_records_quarantined", "invoices").detail
    assert lost["external_id"] in check(report, "golden_records", "invoices").detail


def test_missing_record_without_golden_still_fails(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    sc.records["customers"] = [c for c in sc.records["customers"] if c["external_id"] != "C000001"]
    sc.records["subscriptions"] = []
    sc.records["invoices"] = []
    report = run(sc, golden=False)
    assert report.status is RunStatus.FAILED
    assert ("missing_records_quarantined", "customers") in failed(report)


def test_duplicate_record_fails(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    dup = {**sc.records["customers"][0], "id": "cus_999999"}
    sc.records["customers"].append(dup)
    report = run(sc)
    assert report.status is RunStatus.FAILED
    assert {("no_duplicate_external_ids", "customers"), ("unique_emails", "customers")} <= failed(report)
    assert dup["external_id"] in check(report, "no_duplicate_external_ids", "customers").detail


def test_jpy_amounts_multiplied_by_100_fail_money(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    for inv in sc.records["invoices"]:
        if inv["currency"] == "jpy":
            inv["amount_minor"] *= 100
    report = run(sc, golden=False)
    money = check(report, "money_by_currency", "invoices")
    assert report.status is RunStatus.FAILED
    assert not money.passed
    assert "JPY" in money.detail and "x100" in money.detail
    assert report.money_target_minor["JPY"] == 100 * report.money_source_minor["JPY"]
    assert report.money_target_minor["USD"] == report.money_source_minor["USD"]


def test_wrong_status_mapping_is_caught_by_golden(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    wrong = [s for s in sc.records["subscriptions"] if s["status"] == "delinquent"]
    assert wrong, "fixture precondition: some past_due subscriptions"
    for sub in wrong:
        sub["status"] = "active"  # a naive mapping past_due -> active
    report = run(sc)
    assert report.status is RunStatus.FAILED
    golden = check(report, "golden_records", "subscriptions")
    assert not golden.passed and "expected 'delinquent', got 'active'" in golden.detail
    # Counts, money and references cannot see a wrong enum mapping.
    assert check(report, "count", "subscriptions").passed
    assert check(report, "money_by_currency", "invoices").passed
    assert check(report, "referential_integrity", "subscriptions").passed


def test_wrong_mapping_is_caught_by_source_fidelity_without_golden(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    for cust in sc.records["customers"]:
        # timezone ignored: local midnight treated as UTC midnight
        cust["created_at"] = cust["created_at"][:10] + "T00:00:00Z"
    report = run(sc, golden=False)
    assert report.status is RunStatus.FAILED
    assert failed(report) == {("source_fidelity", "customers")}


def test_silently_truncated_field_is_caught(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    victim = next(c for c in sc.records["customers"] if c["notes"] and len(c["notes"]) > 20)
    victim["notes"] = victim["notes"][:16]
    report = run(sc)
    assert report.status is RunStatus.FAILED
    assert {("source_fidelity", "customers"), ("golden_records", "customers")} == failed(report)
    assert f"{victim['external_id']}.notes" in check(report, "golden_records", "customers").detail


def test_orphan_invoice_quarantined_and_expected_is_partial_success(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path, orphans=1)
    report = run(sc, [orphan_item(sc)])
    assert failed(report) == set()
    assert report.status is RunStatus.PARTIAL_SUCCESS
    assert report.target_counts["invoices"] == report.source_counts["invoices"] - 1
    assert check(report, "count", "invoices").expected == report.target_counts["invoices"]
    assert report.quarantined == [orphan_item(sc)]


def test_orphan_invoice_with_data_reason_without_golden_is_partial_success(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path, orphans=1)
    report = run(sc, [orphan_item(sc, reason="DATA: 422 invalid_reference")], golden=False)
    assert report.status is RunStatus.PARTIAL_SUCCESS
    # Report-level money keeps the raw source total; the check accounts for the quarantined invoice.
    assert sum(report.money_source_minor.values()) >= sum(report.money_target_minor.values())


def test_orphan_invoice_not_quarantined_fails(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path, orphans=1)
    report = run(sc, [])
    assert report.status is RunStatus.FAILED
    assert {("missing_records_quarantined", "invoices"), ("golden_quarantine", None)} <= failed(report)


@pytest.mark.parametrize("golden", [True, False])
def test_quarantine_with_non_data_reason_fails(tmp_path: Path, golden: bool) -> None:
    sc = make_scenario(tmp_path, orphans=1)
    report = run(sc, [orphan_item(sc, reason="TRANSIENT: retries exhausted")], golden=golden)
    assert report.status is RunStatus.FAILED
    expected_failure = ("golden_quarantine", None) if golden else ("quarantine_reasons", None)
    assert expected_failure in failed(report)


def test_unexpected_quarantine_fails_against_golden(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    victim = sc.records["invoices"].pop(0)
    item = QuarantineItem(
        entity=Entity.invoices, source_id=victim["external_id"], reason="invalid_value: amount"
    )
    report = run(sc, [item])
    assert report.status is RunStatus.FAILED
    assert ("golden_quarantine", None) in failed(report)
    # Without golden the same quarantine is an honest PARTIAL_SUCCESS (DATA reason, money accounted for).
    assert run(sc, [item], golden=False).status is RunStatus.PARTIAL_SUCCESS


def test_duplicate_email_customer_quarantined_is_partial_success(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path, duplicates=1)
    (dup,) = sc.dataset.golden["expected_quarantine"]
    item = QuarantineItem(entity=Entity.customers, source_id=dup["source_id"], reason="duplicate_email")
    report = run(sc, [item])
    assert failed(report) == set()
    assert report.status is RunStatus.PARTIAL_SUCCESS


def test_dangling_customer_reference_fails(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    sc.records["invoices"][0]["customer_id"] = "cus_999999"
    report = run(sc, golden=False)
    ri = check(report, "referential_integrity", "invoices")
    assert report.status is RunStatus.FAILED
    assert not ri.passed and "cus_999999" in ri.detail


def test_subscription_reference_problems_fail(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    invoices = sc.records["invoices"]
    with_sub = [i for i in invoices if i["subscription_id"]]
    with_sub[0]["subscription_id"] = "sub_999999"
    other = next(i for i in with_sub[1:] if i["customer_id"] != with_sub[1]["customer_id"])
    with_sub[1]["subscription_id"] = other["subscription_id"]  # subscription of another customer
    sc.records["subscriptions"][0].pop("plan_code", None)
    sc.records["subscriptions"][0]["price_id"] = "price_gold_m"
    report = run(sc, golden=False)
    sub_ri = check(report, "referential_integrity", "subscriptions")
    inv_ri = check(report, "referential_integrity", "invoices")
    assert report.status is RunStatus.FAILED
    assert "price_gold_m" in sub_ri.detail
    assert "sub_999999 not found" in inv_ri.detail.replace("'", "")
    assert "belongs to another customer" in inv_ri.detail


def test_soft_deleted_customer_migrated_fails(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    deleted = next(c for c in sc.dataset.source["customers"] if c["deleted"])
    sc.records["customers"].append(
        {
            **sc.records["customers"][0],
            "id": "cus_999999",
            "external_id": deleted["cust_id"],
            "email": "someone.else@example.com",
        }
    )
    report = run(sc)
    assert report.status is RunStatus.FAILED
    assert "(soft-deleted)" in check(report, "no_unexpected_records", "customers").detail


def test_deleted_customers_expected_when_contract_includes_them(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    report = run(sc, golden=False, exclude_deleted_customers=False)
    assert report.status is RunStatus.FAILED
    assert ("missing_records_quarantined", "customers") in failed(report)


def test_entity_subset_and_disabled_money_check(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    sc.records["invoices"] = []
    report = run(sc, golden=False, entities=[Entity.customers, Entity.subscriptions], money_by_currency=False)
    assert report.status is RunStatus.SUCCESS
    assert {c.entity for c in report.checks} <= {Entity.customers, Entity.subscriptions, None}
    assert report.money_source_minor == {}


def test_target_representation_variants_are_accepted(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    for inv in sc.records["invoices"]:
        inv["currency"] = inv["currency"].upper()  # v1 accepts any case
        inv["issued_at"] = inv["issued_at"].replace("Z", ".000Z")
    assert run(sc).status is RunStatus.SUCCESS


def test_missing_golden_file_fails(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    sc.golden_path = str(tmp_path / "nope.json")
    report = run(sc)
    assert report.status is RunStatus.FAILED
    assert failed(report) == {("golden_load", None)}


# ---------------------------------------------------------------------------
# Hand-written LegacyBill semantics (no fixture generator involved)
# ---------------------------------------------------------------------------


def _tiny() -> tuple[FakeSource, FakeTarget]:
    source = FakeSource(
        {
            "customers": [
                {
                    "cust_id": "C000001",
                    "full_name": "Asha Rao",
                    "email": "Asha.Rao@Example.com",
                    "country": "in",
                    "status": "A",
                    "created": "03/15/2021",
                    "notes": "",
                    "deleted": False,
                },
                {
                    "cust_id": "C000002",
                    "full_name": "Gone Away",
                    "email": "gone@example.com",
                    "country": "US",
                    "status": "X",
                    "created": "01/01/2020",
                    "notes": "",
                    "deleted": True,
                },
            ],
            "subscriptions": [
                {
                    "sub_id": "S000001",
                    "cust_id": "C000001",
                    "plan_code": "PRO_M",
                    "state": "past_due",
                    "started": "2023-01-05 10:22:00",
                    "seats": "3",
                }
            ],
            "invoices": [
                {"inv_id": "I000001", "cust_id": "C000001", "sub_id": "S000001", "amount": "129.00"}
                | {"currency": "USD", "issued": "2024-02-01", "paid": "Y"},
                {"inv_id": "I000002", "cust_id": "C000001", "sub_id": "", "amount": "1500"}
                | {"currency": "JPY", "issued": "2024-02-02", "paid": "N"},
                {"inv_id": "I000003", "cust_id": "C000001", "sub_id": "", "amount": "1.234"}
                | {"currency": "KWD", "issued": "2024-02-03", "paid": "N"},
            ],
        },
        {"company": "Test Co", "timezone": "Asia/Kolkata", "export_version": "3.2"},
    )
    inv = {"customer_id": "cus_000001", "status": "open"}
    target = FakeTarget(
        {
            "customers": [
                {"id": "cus_000001", "external_id": "C000001", "given_name": "Asha", "family_name": "Rao"}
                | {"email": "asha.rao@example.com", "country": "IN", "status": "active"}
                | {"created_at": "2021-03-14T18:30:00Z", "notes": None}
            ],
            "subscriptions": [
                {"id": "sub_000001", "external_id": "S000001", "customer_id": "cus_000001"}
                | {"price_id": "price_pro_m", "status": "delinquent", "start_at": "2023-01-05T04:52:00Z"}
                | {"quantity": 3}
            ],
            "invoices": [
                inv
                | {"id": "inv_000001", "external_id": "I000001", "subscription_id": "sub_000001"}
                | {
                    "amount_minor": 12900,
                    "currency": "usd",
                    "issued_at": "2024-02-01T00:00:00Z",
                    "status": "paid",
                },
                inv
                | {"id": "inv_000002", "external_id": "I000002", "subscription_id": None}
                | {"amount_minor": 1500, "currency": "JPY", "issued_at": "2024-02-02T00:00:00Z"},
                inv
                | {"id": "inv_000003", "external_id": "I000003", "subscription_id": None}
                | {"amount_minor": 1234, "currency": "kwd", "issued_at": "2024-02-03T00:00:00Z"},
            ],
        },
        copy.deepcopy(PRICES),
    )
    return source, target


def test_hand_written_contract_examples_verify() -> None:
    source, target = _tiny()
    report = verify("tiny", source, target, PreservationContract(), [])
    assert failed(report) == set()
    assert report.status is RunStatus.SUCCESS
    assert report.money_source_minor == {"JPY": 1500, "KWD": 1234, "USD": 12900}
    assert report.source_counts == {"customers": 1, "subscriptions": 1, "invoices": 3}


def test_hand_written_wrong_jpy_scaling_fails() -> None:
    source, target = _tiny()
    target.records["invoices"][1]["amount_minor"] = 150000
    report = verify("tiny", source, target, PreservationContract(), [])
    assert ("money_by_currency", "invoices") in failed(report)
    assert ("source_fidelity", "invoices") in failed(report)


def test_minor_units_table_and_conversion() -> None:
    assert minor_units("JPY") == 0
    assert minor_units("jpy") == 0
    assert minor_units("KWD") == 3
    assert minor_units("BHD") == 3
    assert minor_units("USD") == 2
    assert minor_units("INR") == 2
    assert to_minor("129.00", "USD") == 12900
    assert to_minor("1500", "JPY") == 1500
    assert to_minor("1.234", "KWD") == 1234
    assert to_minor("0", "EUR") == 0
    for bad_amount, currency in [
        ("12.5", "JPY"),
        ("1.001", "USD"),
        ("abc", "USD"),
        ("NaN", "USD"),
        (True, "USD"),
    ]:
        with pytest.raises(ValueError):
            to_minor(bad_amount, currency)


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("invalid_reference", True),
        ("422 duplicate_email: email already used by cus_000003", True),
        ("Invalid reference: customer does not exist", True),
        ("DATA: enum_map has no value for 'Z'", True),
        ("not_lowercase", True),
        ("TRANSIENT: retries exhausted", False),
        ("metadata lost", False),
        ("BUDGET", False),
        ("", False),
    ],
)
def test_data_reason_detection(reason: str, expected: bool) -> None:
    assert is_data_reason(reason) is expected


# ---------------------------------------------------------------------------
# Report hash and read failures
# ---------------------------------------------------------------------------


def test_report_hash_is_sha256_of_canonical_checks(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    first, second = run(sc), run(sc)
    canonical = json.dumps(
        [c.model_dump(mode="json") for c in first.checks],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert first.report_hash == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert first.report_hash == second.report_hash
    sc.records["invoices"].pop()
    assert run(sc).report_hash != first.report_hash


def test_transient_read_errors_are_retried(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    sc.target.failures = [FakeHTTPError(503, retry_after=0.1), TimeoutError("read timed out")]
    sleeps: list[float] = []
    report = verify("r", sc.source, sc.target, PreservationContract(), [], sleep=sleeps.append)
    assert report.status is RunStatus.SUCCESS
    assert sleeps == [0.1, 0.5]


def test_persistent_read_error_gives_failed_report(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    sc.target.failures = [FakeHTTPError(429, retry_after=0.0)] * 5
    report = verify("r", sc.source, sc.target, PreservationContract(), [], attempts=3, sleep=lambda _s: None)
    assert report.status is RunStatus.FAILED
    assert [c.name for c in report.checks] == ["read_data"]
    assert report.report_hash == report_hash(report.checks)


def test_auth_error_is_not_retried(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    sc.target.failures = [FakeHTTPError(401)]
    sleeps: list[float] = []
    report = verify("r", sc.source, sc.target, PreservationContract(), [], sleep=sleeps.append)
    assert report.status is RunStatus.FAILED
    assert sleeps == []
    assert "401" in report.checks[0].detail


# ---------------------------------------------------------------------------
# Independence from the agent's mapping
# ---------------------------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_verify_source_does_not_import_engine_dsl_ledger_or_agent() -> None:
    imported = _imported_modules(Path(verify_module.__file__))
    offending = sorted(m for m in imported if m.startswith(FORBIDDEN_PACKAGES))
    assert offending == []


def test_importing_verifier_loads_no_forbidden_module() -> None:
    code = (
        "import sys, zerodrop.verifier.verify\n"
        f"bad = sorted(m for m in sys.modules if m.startswith({FORBIDDEN_PACKAGES!r}))\n"
        "print(','.join(bad))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=True
    )
    assert result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Integration with the real sandbox servers and connectors
# ---------------------------------------------------------------------------


def _write_golden_through_api(target: Any, golden: dict[str, Any]) -> None:
    """Load the golden records into NovaBill through the real batch API, resolving references."""
    ids: dict[str, dict[str, str]] = {"customers": {}, "subscriptions": {}}

    def payload(entity: str, g: dict[str, Any]) -> dict[str, Any]:
        if entity == "customers":
            return {k: g[k] for k in CUSTOMER_KEYS}
        body = {k: v for k, v in g.items() if not k.endswith("external_id") or k == "external_id"}
        body["customer_id"] = ids["customers"][g["customer_external_id"]]
        if entity == "subscriptions":
            body.pop("price_id")
        else:
            sub = g["subscription_external_id"]
            body["subscription_id"] = ids["subscriptions"][sub] if sub else None
        return body

    for entity in ("customers", "subscriptions", "invoices"):
        records = golden[entity]
        for start in range(0, len(records), 50):
            chunk = records[start : start + 50]
            items = [
                {"idempotency_key": f"{entity}:{g['external_id']}", "payload": payload(entity, g)}
                for g in chunk
            ]
            result = target.batch(entity, items)
            assert [r.status for r in result.results] == [201] * len(chunk), result.results[:3]
            if entity in ids:
                ids[entity].update(
                    {g["external_id"]: r.id for g, r in zip(chunk, result.results, strict=True)}
                )


@pytest.mark.slow
def test_verify_against_real_sandbox_and_connectors(tmp_path: Path) -> None:
    from zerodrop.connectors.source import SourceClient
    from zerodrop.connectors.target import TargetClient
    from zerodrop.sandbox.servers import run_sandbox

    dataset = fixtures.generate(7, "small", orphan_invoices=1)
    golden_path = str(dataset.write_golden(tmp_path / "golden.json"))
    (expected_q,) = dataset.golden["expected_quarantine"]
    quarantined = [
        QuarantineItem(entity=Entity.invoices, source_id=expected_q["source_id"], reason="invalid_reference")
    ]
    with run_sandbox(dataset) as handle:
        source = SourceClient(handle.source_url)
        target = TargetClient(handle.target_url, token_provider=lambda: handle.target_token)
        with source, target:
            _write_golden_through_api(target, dataset.golden)
            report = verify(
                "live", source, target, PreservationContract(golden_path=golden_path), quarantined
            )
            assert failed(report) == set()
            assert report.status is RunStatus.PARTIAL_SUCCESS
            assert report.target_counts["invoices"] == len(dataset.golden["invoices"])
            empty = verify("live", source, target, PreservationContract(golden_path=golden_path), [])
            assert empty.status is RunStatus.FAILED


@pytest.mark.slow
def test_verify_retries_source_faults_on_real_sandbox(tmp_path: Path) -> None:
    from zerodrop.connectors.source import SourceClient
    from zerodrop.connectors.target import TargetClient
    from zerodrop.models import FaultPlan, FaultRule
    from zerodrop.sandbox.servers import run_sandbox

    dataset = fixtures.generate(11, "small")
    plan = FaultPlan(
        rules=[
            FaultRule(kind="rate_limit", count=1, retry_after_s=0.05),
            FaultRule(kind="server_error", after_requests=2, count=1),
        ]
    )
    with run_sandbox(dataset, source_fault_plan=plan) as handle:
        source = SourceClient(handle.source_url)
        target = TargetClient(handle.target_url, token_provider=lambda: handle.target_token)
        with source, target:
            _write_golden_through_api(target, dataset.golden)
            sleeps: list[float] = []
            report = verify("faults", source, target, PreservationContract(), [], sleep=sleeps.append)
    assert failed(report) == set()
    assert report.status is RunStatus.SUCCESS
    assert len(sleeps) >= 1


# ---------------------------------------------------------------------------
# Review regressions and extra edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "currency", "minor"),
    [
        ("1500.00", "JPY", 1500),
        ("5.5", "KWD", 5500),
        ("0.001", "BHD", 1),
        ("12.3", "USD", 1230),
        ("1E+2", "USD", 10000),
        ("-0.00", "USD", 0),
        ("0E-1000", "USD", 0),
        # 30 significant digits: beyond the default 28-digit Decimal context, must stay exact.
        (
            "1234567890123456789012345678.12",
            "USD",
            123456789012345678901234567812,
        ),
    ],
)
def test_to_minor_exact_cases(amount: str, currency: str, minor: int) -> None:
    assert to_minor(amount, currency) == minor


@pytest.mark.parametrize(
    ("amount", "currency"),
    [("1.2345", "KWD"), ("1e999999", "USD"), ("1e-999999", "USD"), ("Infinity", "EUR"), (1.5, "USD")],
)
def test_to_minor_rejects_with_value_error(amount: Any, currency: str) -> None:
    # Regression: huge exponents raised decimal.Overflow (not a ValueError) and crashed verify().
    with pytest.raises(ValueError):
        to_minor(amount, currency)


def test_extreme_source_amount_fails_cleanly_instead_of_crashing() -> None:
    source, target = _tiny()
    source.records["invoices"][0]["amount"] = "1e999999"
    report = verify("tiny", source, target, PreservationContract(), [])
    assert report.status is RunStatus.FAILED
    assert {("source_fidelity", "invoices"), ("money_by_currency", "invoices")} <= failed(report)


def test_quarantined_invoice_with_unusable_amount_is_partial_success() -> None:
    # Regression: an unparseable source amount failed the money check even when that
    # invoice was honestly quarantined (and therefore excluded from the expected totals).
    source, target = _tiny()
    source.records["invoices"][2]["amount"] = "1.2.3"
    target.records["invoices"].pop(2)
    item = QuarantineItem(entity=Entity.invoices, source_id="I000003", reason="invalid_value: amount")
    report = verify("tiny", source, target, PreservationContract(), [item])
    assert failed(report) == set()
    assert report.status is RunStatus.PARTIAL_SUCCESS
    # The same unusable amount without a quarantine is still a failure.
    report = verify("tiny", source, target, PreservationContract(), [])
    assert ("money_by_currency", "invoices") in failed(report)
    assert "I000003" in check(report, "money_by_currency", "invoices").detail


def test_three_decimal_currency_scaled_as_two_decimals_fails_money() -> None:
    source, target = _tiny()
    target.records["invoices"][2]["amount_minor"] = 123  # "1.234" KWD treated as 2 decimals
    report = verify("tiny", source, target, PreservationContract(), [])
    money = check(report, "money_by_currency", "invoices")
    assert not money.passed and "KWD: expected 1234, got 123" in money.detail
    assert check(report, "money_by_currency", "invoices").actual["USD"] == 12900


def test_unhashable_target_values_fail_cleanly() -> None:
    # Regression: list/dict ids read from the target raised TypeError in the reference checks.
    source, target = _tiny()
    target.records["subscriptions"][0]["price_id"] = {"id": "price_pro_m"}
    target.records["invoices"][0]["customer_id"] = ["cus_000001"]
    target.records["invoices"][0]["subscription_id"] = ["sub_000001"]
    report = verify("tiny", source, target, PreservationContract(), [])
    assert report.status is RunStatus.FAILED
    assert {("referential_integrity", "subscriptions"), ("referential_integrity", "invoices")} <= failed(
        report
    )


def test_whitespace_only_sub_id_means_one_off_invoice() -> None:
    source, target = _tiny()
    source.records["invoices"][1]["sub_id"] = "  "
    assert verify("tiny", source, target, PreservationContract(), []).status is RunStatus.SUCCESS


def test_report_hash_covers_the_quarantine_list(tmp_path: Path) -> None:
    # Regression: the hash covered only the checks, and no check carried the quarantine
    # list, so SUCCESS and PARTIAL_SUCCESS reports could share a hash.
    sc = make_scenario(tmp_path)
    clean = run(sc, golden=False)
    bogus = QuarantineItem(entity=Entity.invoices, source_id="I999999", reason="invalid_value: amount")
    partial = run(sc, [bogus], golden=False)
    assert (clean.status, partial.status) == (RunStatus.SUCCESS, RunStatus.PARTIAL_SUCCESS)
    assert clean.report_hash != partial.report_hash
    assert check(partial, "quarantine_reasons").actual == ["invoices:I999999"]


def test_malformed_golden_file_fails_cleanly(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"customers": ["C000001"], "expected_quarantine": []}), encoding="utf-8")
    sc.golden_path = str(bad)
    report = run(sc)
    assert failed(report) == {("golden_load", None)}


def test_subscription_start_in_wrong_timezone_is_caught_without_golden(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    source_by_id = {s["sub_id"]: s for s in sc.dataset.source["subscriptions"]}
    for sub in sc.records["subscriptions"]:
        started = source_by_id[sub["external_id"]]["started"]
        sub["start_at"] = started.replace(" ", "T") + "Z"  # naive local time treated as UTC
    report = run(sc, golden=False)
    assert failed(report) == {("source_fidelity", "subscriptions")}


def test_valid_but_wrong_price_is_caught_by_fidelity_and_golden(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path, v2_from=0)
    sub = sc.records["subscriptions"][0]
    other = next(p["id"] for p in sc.dataset.prices if p["id"] != sub["price_id"])
    sub["price_id"] = other  # exists in the catalog, so referential integrity cannot see it
    report = run(sc)
    assert failed(report) == {("source_fidelity", "subscriptions"), ("golden_records", "subscriptions")}
    assert f"{sub['external_id']}.price_id" in check(report, "golden_records", "subscriptions").detail


def test_wrong_plan_code_in_v1_is_caught(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    sub = sc.records["subscriptions"][0]
    sub["plan_code"] = next(p["lookup_key"] for p in sc.dataset.prices if p["lookup_key"] != sub["plan_code"])
    report = run(sc)
    assert failed(report) == {("source_fidelity", "subscriptions"), ("golden_records", "subscriptions")}


def test_invoice_pointing_at_another_existing_customer_is_caught(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    inv = next(i for i in sc.records["invoices"] if i["subscription_id"] is None)
    inv["customer_id"] = next(c["id"] for c in sc.records["customers"] if c["id"] != inv["customer_id"])
    report = run(sc)
    # The reference exists, so only the comparisons with resolved external ids can see it.
    assert check(report, "referential_integrity", "invoices").passed
    assert failed(report) == {("source_fidelity", "invoices"), ("golden_records", "invoices")}
    assert f"{inv['external_id']}.customer_external_id" in check(report, "golden_records", "invoices").detail


def test_dropped_subscription_link_is_caught(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    inv = next(i for i in sc.records["invoices"] if i["subscription_id"] is not None)
    inv["subscription_id"] = None
    report = run(sc)
    assert failed(report) == {("source_fidelity", "invoices"), ("golden_records", "invoices")}


def test_quarantined_record_that_was_also_written_fails(tmp_path: Path) -> None:
    # The ledger claims a record is quarantined while it actually reached the target.
    sc = make_scenario(tmp_path)
    ext = sc.records["invoices"][0]["external_id"]
    item = QuarantineItem(entity=Entity.invoices, source_id=ext, reason="invalid_value: amount")
    report = run(sc, [item], golden=False)
    assert report.status is RunStatus.FAILED
    assert "(quarantined)" in check(report, "no_unexpected_records", "invoices").detail


# ---------------------------------------------------------------------------
# Spot check: the same independent comparison, for the records of one batch
# ---------------------------------------------------------------------------


def _spot(sc: Scenario, entity: str, ids: list[str]) -> Any:
    return verify_module.spot_check(
        sc.source, sc.target, PreservationContract(), Entity(entity), ids, sleep=lambda _s: None
    )


def _ids(sc: Scenario, entity: str, n: int = 10) -> list[str]:
    return [r["external_id"] for r in sc.records[entity][:n]]


def test_spot_check_passes_for_records_written_correctly(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    for entity in ("customers", "subscriptions", "invoices"):
        result = _spot(sc, entity, _ids(sc, entity))
        assert result.passed and result.problems == []
        assert (result.checked, result.matching) == (10, 10)


def test_spot_check_only_looks_at_the_records_it_was_asked_about(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    ids = _ids(sc, "invoices", 5)
    sc.records["invoices"][20]["amount_minor"] *= 100  # wrong, but not one of the five
    del sc.records["invoices"][30:]  # most of the entity is not written yet: that is expected mid-run
    assert _spot(sc, "invoices", ids).passed


def test_spot_check_reports_a_record_missing_from_the_target(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    ids = _ids(sc, "customers", 5)
    sc.records["customers"] = [r for r in sc.records["customers"] if r["external_id"] != ids[2]]
    result = _spot(sc, "customers", ids)
    assert not result.passed and (result.checked, result.matching) == (5, 4)
    assert result.problems == [f"{ids[2]}: missing from target"]


def test_spot_check_reports_field_mismatches_with_expected_and_actual(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    jpy = [r for r in sc.records["invoices"] if r["currency"] == "jpy"][:3]
    for inv in jpy:
        inv["amount_minor"] *= 100
    result = _spot(sc, "invoices", [r["external_id"] for r in jpy])
    assert not result.passed and result.matching == 0
    assert all(".amount_minor: expected " in p for p in result.problems)
    assert f"got {jpy[0]['amount_minor']}" in result.problems[0]


def test_spot_check_sees_one_identity_given_to_many_records(tmp_path: Path) -> None:
    # The real-model mistake of fix 3: every record got the same id, so the target kept one.
    sc = make_scenario(tmp_path)
    ids = _ids(sc, "customers", 8)
    sc.records["customers"] = sc.records["customers"][:1]
    result = _spot(sc, "customers", ids)
    assert not result.passed and result.matching == 1
    assert len(result.problems) == 7 and all(p.endswith("missing from target") for p in result.problems)


def test_spot_check_retries_transient_reads_and_reports_a_read_failure(tmp_path: Path) -> None:
    sc = make_scenario(tmp_path)
    ids = _ids(sc, "customers", 3)
    sc.target.failures = [FakeHTTPError(503)]
    assert _spot(sc, "customers", ids).passed
    sc.target.failures = [FakeHTTPError(503)] * 10
    result = _spot(sc, "customers", ids)
    assert not result.passed and result.problems == []
    assert result.read_error.startswith("could not read both systems")
