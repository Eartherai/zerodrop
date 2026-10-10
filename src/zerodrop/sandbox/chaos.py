"""Deterministic, counter-based fault injection for the sandbox services.

The agent never sees this module. Every rule keeps its own counters over the
requests it matches (batch writes for NovaBill, paginated reads for LegacyBill):

- ``seen``: matching requests observed so far, whatever their outcome;
- ``fired``: times the rule's effect was actually applied.

A rule is *eligible* for a request when ``seen >= after_requests`` and
``fired < count``. Effects are applied in a fixed order: ``schema_flip`` and
``slow`` first (they never short-circuit), then at most one rejection
(``auth_revoke`` > ``rate_limit`` > ``server_error``), then ``partial_accept``
and ``timeout_after_write``. A rule shadowed by an earlier rejection does not
consume its count, so every rule fires exactly ``count`` times eventually.

``auth_revoke`` is a one-time event: the first matching request on which a rule is
eligible revokes the original token (that request is refused with 401 if it used the
original token). From then on, until the injector is replaced (admin reset), every
request presenting the original token is refused, on any entity, reads included;
those refusals are recorded with ``counted=False``. Only the rotated token works.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from zerodrop.models import FaultPlan, FaultRule

DEFAULT_STALL_S = 3.0  # timeout_after_write when delay_s is 0
DEFAULT_SLOW_S = 1.0  # slow when delay_s is 0
SOURCE_FAULT_KINDS: frozenset[str] = frozenset({"rate_limit", "server_error", "slow"})

_TERMINAL_ORDER: tuple[str, ...] = ("rate_limit", "server_error")


def coerce_plan(plan: FaultPlan | dict[str, Any] | None) -> FaultPlan:
    if plan is None:
        return FaultPlan()
    if isinstance(plan, FaultPlan):
        return plan
    return FaultPlan.model_validate(plan)


def format_seconds(seconds: float) -> str:
    """Render a Retry-After value: whole seconds as integers, otherwise up to 3 decimals."""
    value = max(0.0, float(seconds))
    if value.is_integer():
        return str(int(value))
    return f"{value:.3f}".rstrip("0").rstrip(".")


async def interruptible_sleep(seconds: float, stop: threading.Event, tick_s: float = 0.05) -> None:
    """Sleep for an injected delay, but return early once ``stop`` is set (server shutdown)."""
    deadline = time.monotonic() + seconds
    while not stop.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        await asyncio.sleep(min(remaining, tick_s))


@dataclass(frozen=True)
class Rejection:
    """A whole-request failure the server must return instead of processing the request."""

    status: int
    code: str
    message: str
    headers: dict[str, str] = field(default_factory=dict)

    def body(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message}}


@dataclass
class FaultOutcome:
    """What the server must do for one request."""

    flip_to: str | None = None
    delay_s: float = 0.0
    reject: Rejection | None = None
    accept_first: int | None = None
    stall_s: float = 0.0
    fired: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _RuleState:
    index: int
    rule: FaultRule
    seen: int = 0
    fired: int = 0

    def matches(self, entity: str | None) -> bool:
        return self.rule.entity is None or self.rule.entity == entity

    def eligible(self) -> bool:
        return self.seen >= self.rule.after_requests and self.fired < self.rule.count


def _revoked_rejection() -> Rejection:
    return Rejection(
        401,
        "invalid_token",
        "The API token has been revoked. Use the rotated credentials.",
        {"WWW-Authenticate": 'Bearer error="invalid_token"'},
    )


def _terminal_rejection(rule: FaultRule) -> Rejection:
    if rule.kind == "rate_limit":
        return Rejection(
            429,
            "rate_limited",
            "Too many requests. Retry after the number of seconds in the Retry-After header.",
            {"Retry-After": format_seconds(rule.retry_after_s)},
        )
    return Rejection(503, "service_unavailable", "The service is temporarily unavailable. Try again later.")


class FaultInjector:
    """Applies a :class:`FaultPlan` to a stream of matching requests, deterministically.

    ``kinds`` restricts which rule kinds this injector honours and ``any_entity_only``
    keeps only rules with ``entity=None`` (LegacyBill uses both).
    """

    def __init__(
        self,
        plan: FaultPlan | dict[str, Any] | None = None,
        *,
        kinds: Iterable[str] | None = None,
        any_entity_only: bool = False,
    ) -> None:
        self.plan = coerce_plan(plan)
        allowed = None if kinds is None else frozenset(kinds)
        self._rules = [
            _RuleState(index, rule)
            for index, rule in enumerate(self.plan.rules)
            if (allowed is None or rule.kind in allowed) and (not any_entity_only or rule.entity is None)
        ]
        self._lock = threading.Lock()
        self._requests = 0
        self._fired: list[dict[str, Any]] = []
        self._revoked_by: _RuleState | None = None  # the auth_revoke rule that revoked the original token

    # -- request evaluation -------------------------------------------------

    def evaluate(self, entity: str, *, original_token: bool = True) -> FaultOutcome:
        """Advance the counters for one matching request and return the effects to apply."""
        with self._lock:
            self._requests += 1
            request_no = self._requests
            candidates: dict[str, list[_RuleState]] = {}
            for state in self._rules:
                if not state.matches(entity):
                    continue
                if state.eligible():
                    candidates.setdefault(state.rule.kind, []).append(state)
                state.seen += 1

            outcome = FaultOutcome()
            for state in candidates.get("schema_flip", []):
                outcome.flip_to = state.rule.to_version
                self._fire(outcome, state, entity, request_no)
            for state in candidates.get("slow", []):
                outcome.delay_s += state.rule.delay_s if state.rule.delay_s > 0 else DEFAULT_SLOW_S
                self._fire(outcome, state, entity, request_no)

            self._apply_auth(outcome, candidates, entity, request_no, original_token)
            if outcome.reject is None:
                for kind in _TERMINAL_ORDER:
                    if candidates.get(kind):
                        state = candidates[kind][0]
                        outcome.reject = _terminal_rejection(state.rule)
                        self._fire(outcome, state, entity, request_no)
                        break
            if outcome.reject is None:
                self._apply_post_effects(outcome, candidates, entity, request_no)
            return outcome

    def _apply_auth(
        self,
        outcome: FaultOutcome,
        candidates: dict[str, list[_RuleState]],
        entity: str,
        request_no: int,
        original_token: bool,
    ) -> None:
        if self._revoked_by is None:
            revoking = candidates.get("auth_revoke", [])
            if not revoking:
                return
            self._revoked_by = revoking[0]
            self._fire(outcome, revoking[0], entity, request_no)
        elif original_token:
            # Revocation is global and persistent: later refusals do not consume any count.
            self._fire(outcome, self._revoked_by, entity, request_no, counted=False)
        if original_token:
            outcome.reject = _revoked_rejection()

    def _apply_post_effects(
        self, outcome: FaultOutcome, candidates: dict[str, list[_RuleState]], entity: str, request_no: int
    ) -> None:
        for state in candidates.get("partial_accept", []):
            accept = max(0, state.rule.accept_first)
            outcome.accept_first = (
                accept if outcome.accept_first is None else min(outcome.accept_first, accept)
            )
            self._fire(outcome, state, entity, request_no)
        for state in candidates.get("timeout_after_write", []):
            stall = state.rule.delay_s if state.rule.delay_s > 0 else DEFAULT_STALL_S
            outcome.stall_s = max(outcome.stall_s, stall)
            self._fire(outcome, state, entity, request_no)

    def _fire(
        self,
        outcome: FaultOutcome,
        state: _RuleState,
        entity: str | None,
        request_no: int | None,
        *,
        counted: bool = True,
    ) -> None:
        if counted:
            state.fired += 1
        record = {
            "rule": state.index,
            "kind": state.rule.kind,
            "entity": entity,
            "request": request_no,
            "counted": counted,
        }
        outcome.fired.append(record)
        self._fired.append(record)

    # -- token revocation for non-write requests ----------------------------

    def token_revoked(self) -> bool:
        """True once an ``auth_revoke`` rule has fired: the original token must be refused."""
        with self._lock:
            return self._revoked_by is not None

    def note_revoked_read(self, entity: str | None = None) -> None:
        """Record a read refused because the original token is revoked (does not consume the count)."""
        with self._lock:
            if self._revoked_by is None:
                return
            record = {
                "rule": self._revoked_by.index,
                "kind": "auth_revoke",
                "entity": entity,
                "request": None,
                "counted": False,
            }
            self._fired.append(record)

    # -- reporting ----------------------------------------------------------

    @property
    def fired(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._fired]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "plan": self.plan.model_dump(mode="json"),
                "matching_requests": self._requests,
                "token_revoked": self._revoked_by is not None,
                "rules": [
                    {
                        "index": s.index,
                        "kind": s.rule.kind,
                        "entity": None if s.rule.entity is None else str(s.rule.entity),
                        "seen": s.seen,
                        "fired": s.fired,
                        "exhausted": s.fired >= s.rule.count,
                    }
                    for s in self._rules
                ],
                "fired": [dict(r) for r in self._fired],
            }
