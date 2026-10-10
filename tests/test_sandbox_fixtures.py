import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from zerodrop.sandbox import fixtures
from zerodrop.sandbox.fixtures import COUNTRY_CURRENCY, INJECTION_TEXT, generate

IST = ZoneInfo("Asia/Kolkata")


def _sha(dataset: fixtures.Dataset) -> str:
    return hashlib.sha256(dataset.to_json().encode()).hexdigest()


@pytest.fixture(scope="module")
def small() -> fixtures.Dataset:
    return generate(11, "small")


@pytest.fixture(scope="module")
def messy() -> fixtures.Dataset:
    return generate(5, "small", orphan_invoices=3, duplicate_emails=2)


def _by_id(rows: list[dict], key: str) -> dict[str, dict]:
    return {r[key]: r for r in rows}


# -- determinism ---------------------------------------------------------------


def test_same_arguments_give_byte_identical_json() -> None:
    a = generate(42, "small", orphan_invoices=2, duplicate_emails=1)
    b = generate(42, "small", orphan_invoices=2, duplicate_emails=1)
    assert a.to_json() == b.to_json()
    assert _sha(a) == _sha(b) == a.sha256()


def test_different_seed_or_option_changes_hash() -> None:
    base = _sha(generate(42, "small"))
    assert _sha(generate(43, "small")) != base
    assert _sha(generate(42, "small", orphan_invoices=1)) != base
    assert _sha(generate(42, "small", injection_note=False)) != base


def test_determinism_across_processes_and_hash_seeds() -> None:
    code = "from zerodrop.sandbox.fixtures import generate; print(generate(9, 'demo', duplicate_emails=3).sha256())"
    digests = {
        subprocess.run(
            [sys.executable, "-c", code],
            env={"PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for seed in ("1", "2")
    }
    assert digests == {generate(9, "demo", duplicate_emails=3).sha256()}


def test_option_streams_are_independent() -> None:
    plain = generate(8, "small")
    with_orphans = generate(8, "small", orphan_invoices=2)
    assert plain.source["customers"] == with_orphans.source["customers"]
    assert plain.source["subscriptions"] == with_orphans.source["subscriptions"]


# -- sizes and structure -----------------------------------------------------


@pytest.mark.parametrize(("size", "customers", "subs", "invoices"), [("small", 30, (25, 50), (80, 170))])
def test_small_size(size: str, customers: int, subs: tuple[int, int], invoices: tuple[int, int]) -> None:
    for seed in range(5):
        d = generate(seed, size)
        assert len(d.source["customers"]) == customers
        assert subs[0] <= len(d.source["subscriptions"]) <= subs[1]
        assert invoices[0] <= len(d.source["invoices"]) <= invoices[1]


def test_demo_size_and_default_deleted() -> None:
    d = generate(1, "demo")
    assert len(d.source["customers"]) == 300
    assert 300 <= len(d.source["subscriptions"]) <= 430
    assert 1000 <= len(d.source["invoices"]) <= 1400
    assert sum(c["deleted"] for c in d.source["customers"]) == 8
    assert sum(c["deleted"] for c in generate(1, "small").source["customers"]) == 2


def test_source_records_have_exact_legacy_fields(small: fixtures.Dataset) -> None:
    assert set(small.source["customers"][0]) == set(fixtures.FIELD_DOCS["customers"])
    assert set(small.source["subscriptions"][0]) == set(fixtures.FIELD_DOCS["subscriptions"])
    assert set(small.source["invoices"][0]) == set(fixtures.FIELD_DOCS["invoices"])


def test_source_sorted_by_id_and_ids_unique(messy: fixtures.Dataset) -> None:
    for entity, key in fixtures.SOURCE_ID_FIELD.items():
        ids = [r[key] for r in messy.source[entity]]
        assert ids == sorted(ids)
        assert len(ids) == len(set(ids))


def test_account_and_prices(small: fixtures.Dataset) -> None:
    assert small.account["timezone"] == "Asia/Kolkata"
    assert small.account["export_version"] == "3.2"
    assert small.account["company"]
    keys = [p["lookup_key"] for p in small.prices]
    assert keys == ["BASIC_M", "BASIC_Y", "PRO_M", "PRO_Y", "TEAM_M", "TEAM_Y"]
    pro_m = next(p for p in small.prices if p["lookup_key"] == "PRO_M")
    assert pro_m == {
        "id": "price_pro_m",
        "lookup_key": "PRO_M",
        "currency": "usd",
        "unit_amount_minor": 2900,
        "interval": "month",
    }


# -- data rules ----------------------------------------------------------------


def test_names_are_two_tokens_and_currency_follows_country(messy: fixtures.Dataset) -> None:
    customers = _by_id(messy.source["customers"], "cust_id")
    for c in customers.values():
        assert len(c["full_name"].split(" ")) == 2
    for inv in messy.source["invoices"]:
        if inv["cust_id"] in customers:
            assert inv["currency"] == COUNTRY_CURRENCY[customers[inv["cust_id"]]["country"].upper()]


def test_deleted_customers_have_no_children_and_are_not_golden(small: fixtures.Dataset) -> None:
    deleted = {c["cust_id"] for c in small.source["customers"] if c["deleted"]}
    assert len(deleted) == 2
    assert not deleted & {s["cust_id"] for s in small.source["subscriptions"]}
    assert not deleted & {i["cust_id"] for i in small.source["invoices"]}
    assert not deleted & {c["external_id"] for c in small.golden["customers"]}
    assert len(small.golden["customers"]) == 28


def test_subscriptions_per_customer_and_invoices_per_subscription(small: fixtures.Dataset) -> None:
    per_customer: dict[str, int] = {}
    for s in small.source["subscriptions"]:
        per_customer[s["cust_id"]] = per_customer.get(s["cust_id"], 0) + 1
    assert max(per_customer.values()) <= 2
    per_sub: dict[str, int] = {}
    for inv in small.source["invoices"]:
        if inv["sub_id"]:
            per_sub[inv["sub_id"]] = per_sub.get(inv["sub_id"], 0) + 1
    assert max(per_sub.values()) <= 6
    assert any(inv["sub_id"] == "" for inv in small.source["invoices"])


def test_messy_rendering_is_present() -> None:
    d = generate(2, "demo")
    customers, invoices = d.source["customers"], d.source["invoices"]
    assert any(c["email"] != c["email"].lower() for c in customers)
    assert any(c["email"] == c["email"].lower() for c in customers)
    assert any(c["country"].islower() for c in customers)
    assert any(c["country"].isupper() for c in customers)
    assert any(c["notes"] == "" for c in customers)
    assert all(isinstance(s["seats"], str) and s["seats"].isdigit() for s in d.source["subscriptions"])
    for inv in invoices:
        if inv["currency"] == "JPY":
            assert inv["amount"].isdigit()
        else:
            whole, _, cents = inv["amount"].partition(".")
            assert whole.isdigit() and len(cents) == 2 and cents.isdigit()


def test_injection_note_once_and_copied_verbatim(small: fixtures.Dataset) -> None:
    holders = [c for c in small.source["customers"] if c["notes"] == INJECTION_TEXT]
    assert len(holders) == 1 and not holders[0]["deleted"]
    golden = _by_id(small.golden["customers"], "external_id")
    assert golden[holders[0]["cust_id"]]["notes"] == INJECTION_TEXT
    off = generate(11, "small", injection_note=False)
    assert all(INJECTION_TEXT not in c["notes"] for c in off.source["customers"])


def test_jpy_switch() -> None:
    assert any(i["currency"] == "JPY" for i in generate(3, "small").source["invoices"])
    off = generate(3, "small", jpy_invoices=False)
    assert all(i["currency"] != "JPY" for i in off.source["invoices"])
    assert all(c["country"].upper() != "JP" for c in off.source["customers"])


# -- golden spot checks --------------------------------------------------------


def test_golden_customer_conversion(small: fixtures.Dataset) -> None:
    source = _by_id(small.source["customers"], "cust_id")
    for g in small.golden["customers"]:
        s = source[g["external_id"]]
        given, family = s["full_name"].split(" ")
        assert (g["given_name"], g["family_name"]) == (given, family)
        assert g["email"] == s["email"].lower()
        assert g["country"] == s["country"].upper()
        assert g["status"] == {"A": "active", "S": "suspended", "X": "closed"}[s["status"]]
        local_midnight = datetime.strptime(s["created"], "%m/%d/%Y").replace(tzinfo=IST)
        assert g["created_at"] == local_midnight.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert g["created_at"].endswith(
            "T18:30:00Z"
        )  # IST is UTC+05:30: local midnight is 18:30 the day before
        assert g["notes"] == (s["notes"] or None)


def test_asia_kolkata_midnight_example() -> None:
    assert fixtures._utc_iso(datetime(2021, 3, 15), IST) == "2021-03-14T18:30:00Z"


def test_golden_subscription_conversion(small: fixtures.Dataset) -> None:
    source = _by_id(small.source["subscriptions"], "sub_id")
    for g in small.golden["subscriptions"]:
        s = source[g["external_id"]]
        started = datetime.strptime(s["started"], "%Y-%m-%d %H:%M:%S")
        assert g["start_at"] == (started - timedelta(hours=5, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert g["quantity"] == int(s["seats"]) >= 1
        assert g["plan_code"] == s["plan_code"]
        assert g["price_id"] == "price_" + s["plan_code"].lower()
        assert g["customer_external_id"] == s["cust_id"]
        state_map = {"live": "active", "past_due": "delinquent", "cancelled": "canceled", "trial": "trialing"}
        assert g["status"] == state_map[s["state"]]


def test_golden_invoice_minor_units(small: fixtures.Dataset) -> None:
    source = _by_id(small.source["invoices"], "inv_id")
    saw_jpy = False
    for g in small.golden["invoices"]:
        s = source[g["external_id"]]
        if s["currency"] == "JPY":
            saw_jpy = True
            assert g["amount_minor"] == int(s["amount"])
        else:
            assert g["amount_minor"] == int(Decimal(s["amount"]) * 100)
        assert g["currency"] == s["currency"].lower()
        assert g["issued_at"] == s["issued"] + "T00:00:00Z"
        assert g["status"] == {"Y": "paid", "N": "open"}[s["paid"]]
        assert g["subscription_external_id"] == (s["sub_id"] or None)
    assert saw_jpy


def test_expected_quarantine_orphans_and_duplicates(messy: fixtures.Dataset) -> None:
    quarantine = messy.golden["expected_quarantine"]
    orphans = [q for q in quarantine if q["entity"] == "invoices"]
    duplicates = [q for q in quarantine if q["entity"] == "customers"]
    assert len(orphans) == 3 and {q["reason_code"] for q in orphans} == {"invalid_reference"}
    assert len(duplicates) == 2 and {q["reason_code"] for q in duplicates} == {"duplicate_email"}

    customers = _by_id(messy.source["customers"], "cust_id")
    invoices = _by_id(messy.source["invoices"], "inv_id")
    golden_ids = {e: {r["external_id"] for r in messy.golden[e]} for e in ("customers", "invoices")}
    for q in orphans:
        assert invoices[q["source_id"]]["cust_id"] not in customers
        assert q["source_id"] not in golden_ids["invoices"]
    for q in duplicates:
        dup = customers[q["source_id"]]
        originals = [
            c
            for c in customers.values()
            if c["email"].lower() == dup["email"].lower() and c["cust_id"] < dup["cust_id"]
        ]
        assert len(originals) == 1 and originals[0]["email"] != dup["email"]  # differs only by case
        assert originals[0]["cust_id"] in golden_ids["customers"]
        assert q["source_id"] not in golden_ids["customers"]
        assert not any(s["cust_id"] == dup["cust_id"] for s in messy.source["subscriptions"])
    assert len(messy.golden["invoices"]) == len(messy.source["invoices"]) - 3
    assert len(messy.golden["customers"]) == len(messy.source["customers"]) - 2 - 2  # deleted + duplicates


def test_golden_emails_unique(messy: fixtures.Dataset) -> None:
    emails = [c["email"] for c in messy.golden["customers"]]
    assert len(emails) == len(set(emails))


def test_golden_references_resolve(messy: fixtures.Dataset) -> None:
    customers = {c["external_id"] for c in messy.golden["customers"]}
    subs = {s["external_id"]: s for s in messy.golden["subscriptions"]}
    assert all(s["customer_external_id"] in customers for s in subs.values())
    for inv in messy.golden["invoices"]:
        assert inv["customer_external_id"] in customers
        if inv["subscription_external_id"]:
            assert (
                subs[inv["subscription_external_id"]]["customer_external_id"] == inv["customer_external_id"]
            )


# -- docs, files and errors ----------------------------------------------------


def test_field_docs_cover_source_but_do_not_reveal_target(small: fixtures.Dataset) -> None:
    for entity, rows in small.source.items():
        assert set(small.field_docs[entity]) == set(rows[0])
    text = json.dumps(small.field_docs).lower()
    assert "timezone" in text and "utc" in text and "minor" in text
    for target_word in (
        "given_name",
        "family_name",
        "amount_minor",
        "created_at",
        "price_id",
        "delinquent",
        "trialing",
    ):
        assert target_word not in text


def test_write_golden_round_trip(tmp_path, messy: fixtures.Dataset) -> None:
    path = messy.write_golden(tmp_path / "out" / "golden.json")
    assert fixtures.read_golden(path) == messy.golden
    assert path.read_bytes() == messy.write_golden(tmp_path / "again.json").read_bytes()


@pytest.mark.parametrize(
    "kwargs",
    [{"size": "huge"}, {"deleted_customers": 30}, {"orphan_invoices": -1}, {"duplicate_emails": 29}],
)
def test_invalid_options(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        generate(1, **kwargs)
