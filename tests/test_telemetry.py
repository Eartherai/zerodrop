"""Telemetry helpers: off by default, and the active Neatlogs trace id is readable when tracing is on."""

import sys
import types

import pytest

from zerodrop import telemetry

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"


def _fake_neatlogs(traceparent: str | None) -> types.ModuleType:
    module = types.ModuleType("neatlogs")

    def inject_trace_context(carrier: dict[str, str]) -> bool:
        if traceparent is None:
            return False  # no active Neatlogs span
        carrier["traceparent"] = traceparent
        return True

    module.inject_trace_context = inject_trace_context  # type: ignore[attr-defined]
    return module


def test_current_trace_id_is_none_when_tracing_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "neatlogs", _fake_neatlogs(f"00-{TRACE_ID}-00f067aa0ba902b7-01"))
    assert telemetry.enabled() is False
    assert telemetry.current_trace_id() is None


def test_current_trace_id_comes_from_the_active_neatlogs_span(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telemetry, "_enabled", True)
    monkeypatch.setitem(sys.modules, "neatlogs", _fake_neatlogs(f"00-{TRACE_ID}-00f067aa0ba902b7-01"))
    assert telemetry.current_trace_id() == TRACE_ID


@pytest.mark.parametrize(
    "traceparent", [None, "garbage", "00-short-00f067aa0ba902b7-01", "00-" + "0" * 32 + "-x-01"]
)
def test_current_trace_id_is_none_without_a_valid_active_span(
    monkeypatch: pytest.MonkeyPatch, traceparent: str | None
) -> None:
    monkeypatch.setattr(telemetry, "_enabled", True)
    monkeypatch.setitem(sys.modules, "neatlogs", _fake_neatlogs(traceparent))
    assert telemetry.current_trace_id() is None
