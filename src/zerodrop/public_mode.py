"""Public demo mode: guard rails for running the dashboard API on the open internet.

Settings come from the environment (prefix ``ZERODROP_PUBLIC_``) or a git-ignored ``.env``
file, like ``config.Settings``. With ``enabled`` true, the dashboard API (``zerodrop.api``):

- lets anyone start runs with the deterministic oracle planner ($0, no model calls); every
  other planner, including ``claude`` and ``gemini``, needs the ``X-ZeroDrop-Access-Code`` header to match
  ``access_code`` (compared in constant time). A request that names no planner gets ``oracle``;
- allows at most ``max_runs_per_hour`` runs in any rolling hour, for every planner, counted
  from the run ledger (so a restart does not reset the window);
- refuses new model runs, ``claude`` and ``gemini`` alike (HTTP 402), once the LLM cost recorded in the ledger
  (``runs.cost_usd``, summed over all runs) has reached ``spend_cap_usd``.

The access code is a ``SecretStr``: it is never logged, returned or put in an error message,
and validation errors hide their input. The spend cap is checked before a run starts, so the
worst case is the cap plus one run's own cost limit (``Settings.max_cost_usd``).
"""

from __future__ import annotations

import hashlib
import hmac
import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ACCESS_CODE_HEADER = "X-ZeroDrop-Access-Code"
OPEN_PLANNER = "oracle"  # deterministic, no model calls, $0: the only planner open to everyone
FREE_PLANNERS = frozenset({"oracle", "naive"})  # offline fakes; every other planner is paid and capped
MIN_ACCESS_CODE_LENGTH = 16
RATE_WINDOW_S = 3600.0


class PublicSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ZERODROP_PUBLIC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,  # a rejected access code must not appear in a startup error
    )

    enabled: bool = False
    access_code: SecretStr | None = None
    spend_cap_usd: float = Field(default=5.0, ge=0)
    max_runs_per_hour: int = Field(default=12, ge=0)  # 0 = nobody can start runs (replays only)

    @field_validator("access_code")
    @classmethod
    def _long_enough(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or not value.get_secret_value().strip():
            return None  # unset or blank: model runs stay closed
        if len(value.get_secret_value()) < MIN_ACCESS_CODE_LENGTH:
            raise ValueError(
                f"must be at least {MIN_ACCESS_CODE_LENGTH} characters; generate one with "
                "python -c 'import secrets; print(secrets.token_urlsafe(24))'"
            )
        return value


@dataclass(frozen=True)
class Refusal:
    """Why a run may not start: an HTTP status, a message safe to show anyone, optional headers."""

    status: int
    detail: str
    headers: dict[str, str] = field(default_factory=dict)


def access_code_matches(settings: PublicSettings, provided: str | None) -> bool:
    """Constant-time comparison (of SHA-256 digests, so the length is not leaked either)."""
    if settings.access_code is None or not provided:
        return False
    expected = hashlib.sha256(settings.access_code.get_secret_value().encode("utf-8")).digest()
    given = hashlib.sha256(provided.encode("utf-8")).digest()
    return hmac.compare_digest(expected, given)


def effective_planner(requested: str | None, server_default: str, settings: PublicSettings) -> str:
    """The planner a run uses: as requested, else the server default (``oracle`` in public mode)."""
    if requested:
        return requested
    return OPEN_PLANNER if settings.enabled else server_default


def default_planner(server_default: str, settings: PublicSettings) -> str:
    return effective_planner(None, server_default, settings)


def claude_runs_allowed(settings: PublicSettings, spend_used_usd: float) -> bool:
    """Whether the policy lets paid model runs start (in public mode: with the access code, under the cap).

    The name is kept for the `/api/meta` key; it covers every paid planner (claude, gemini).
    It does not check that a model key is configured; without one a model run fails before
    it starts.
    """
    if not settings.enabled:
        return True
    return settings.access_code is not None and spend_used_usd < settings.spend_cap_usd


def check_access(settings: PublicSettings, planner: str, provided_code: str | None) -> Refusal | None:
    """Stateless check: planners other than oracle need the access code in public mode."""
    if not settings.enabled or planner == OPEN_PLANNER:
        return None
    if settings.access_code is None:
        return Refusal(
            403,
            f"Planner '{planner}' is turned off on this public demo. "
            f"Planner '{OPEN_PLANNER}' (deterministic, $0) is open to everyone.",
        )
    if not access_code_matches(settings, provided_code):
        return Refusal(
            403,
            f"Planner '{planner}' needs a valid {ACCESS_CODE_HEADER} header on this public demo. "
            f"Planner '{OPEN_PLANNER}' (deterministic, $0) is open to everyone.",
        )
    return None


def check_budget(
    settings: PublicSettings,
    planner: str,
    *,
    spend_used_usd: float,
    recent_run_times: Sequence[float],
    now: float,
) -> Refusal | None:
    """Stateful checks: the model spend cap (every paid planner), then the hourly run limit.

    ``recent_run_times`` holds the creation times (epoch seconds) of the newest
    ``max_runs_per_hour`` runs in the ledger, in any order.
    """
    if not settings.enabled:
        return None
    if planner not in FREE_PLANNERS and spend_used_usd >= settings.spend_cap_usd:
        return Refusal(
            402,
            f"Model spend cap reached on this public demo: ${spend_used_usd:.2f} of "
            f"${settings.spend_cap_usd:.2f} used. Planner '{OPEN_PLANNER}' (deterministic, $0) "
            "is still available.",
        )
    limit = settings.max_runs_per_hour
    if limit == 0:
        return Refusal(
            403, "Starting runs is turned off on this public demo; recorded runs can still be opened."
        )
    in_window = sorted((t for t in recent_run_times if t > now - RATE_WINDOW_S), reverse=True)
    if len(in_window) >= limit:
        # A slot frees up when the limit-th newest run leaves the window (older ones leave first).
        retry_after = max(1, math.ceil(in_window[limit - 1] + RATE_WINDOW_S - now))
        return Refusal(
            429,
            f"Run limit reached: this public demo allows {limit} runs per hour. "
            f"Try again in {retry_after} s, or open a recorded run.",
            {"Retry-After": str(retry_after)},
        )
    return None
