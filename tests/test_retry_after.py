"""Efficiency regression: rate-limit waits follow the server's Retry-After hint."""

from __future__ import annotations

import pytest

from zerodrop.models import RunStatus
from zerodrop.runner import run_scenario
from zerodrop.scenarios import get_scenario


@pytest.mark.slow
def test_rate_limit_waits_follow_retry_after_instead_of_growing() -> None:
    """Efficiency regression: with Retry-After present, wait what the server asked (plus small jitter).

    Before: waits grew exponentially past the server's hint (S03 took ~12 s for six 0.2 s hints).
    """
    sleeps: list[float] = []
    outcome = run_scenario(get_scenario("S03-rate-limit-storm"), "oracle", sleep=sleeps.append)
    assert outcome.status == RunStatus.SUCCESS
    assert len(sleeps) == 6
    assert all(0.2 <= s <= 0.2 * 1.25 for s in sleeps), sleeps
