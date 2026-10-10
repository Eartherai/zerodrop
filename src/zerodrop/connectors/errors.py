"""Typed connector errors. The connectors never retry; the engine classifies these.

- `TargetHTTPError`: NovaBill answered with a non-success status (429, 5xx, 401, 4xx).
- `TargetTimeout`: no answer in time. ``sent=True`` means the request may have
  reached the server (read or write timeout), so a write is ambiguous.
- `TargetConnectionError`: transport failure. ``sent=True`` when the connection
  broke after the request was sent (e.g. server disconnected without a reply).
- `SourceError`: any LegacyBill failure, carrying status / Retry-After / timeout.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any


class ConnectorError(Exception):
    """Base class for every connector failure."""


class TargetHTTPError(ConnectorError):
    def __init__(self, status: int, retry_after: float | None = None, body: Any = None) -> None:
        super().__init__(
            f"target responded {status}" + (f" (retry after {retry_after}s)" if retry_after else "")
        )
        self.status = status
        self.retry_after = retry_after
        self.body = body

    @property
    def error_code(self) -> str | None:
        """Best-effort error code from the body (``{"error": {"code"}}``, ``{"detail": ...}`` or ``{"code"}``)."""
        return extract_error_code(self.body)

    def __reduce__(self) -> tuple[Any, ...]:
        return (type(self), (self.status, self.retry_after, self.body))


class TargetTimeout(ConnectorError):
    def __init__(self, sent: bool) -> None:
        super().__init__(
            "target timed out after the request was sent" if sent else "target timed out before sending"
        )
        self.sent = sent

    def __reduce__(self) -> tuple[Any, ...]:
        return (type(self), (self.sent,))


class TargetConnectionError(ConnectorError):
    def __init__(self, message: str = "target connection failed", sent: bool = False) -> None:
        super().__init__(message)
        self.sent = sent

    def __reduce__(self) -> tuple[Any, ...]:
        return (type(self), (str(self), self.sent))


class SourceError(ConnectorError):
    def __init__(
        self,
        message: str,
        status: int | None = None,
        retry_after: float | None = None,
        body: Any = None,
        timeout: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.body = body
        self.timeout = timeout

    @property
    def transient(self) -> bool:
        """True for failures worth retrying: timeouts, transport errors, 429 and 5xx."""
        return self.status is None or self.status == 429 or self.status >= 500

    def __reduce__(self) -> tuple[Any, ...]:
        return (type(self), (str(self), self.status, self.retry_after, self.body, self.timeout))


def extract_error_code(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    for key in ("error", "detail"):
        inner = body.get(key)
        if isinstance(inner, dict) and isinstance(inner.get("code"), str):
            return inner["code"]
        if key == "detail" and isinstance(inner, str):
            return inner
    code = body.get("code")
    return code if isinstance(code, str) else None


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Parse a Retry-After header: delta-seconds (fractions allowed) or an HTTP-date.

    Returns seconds to wait (>= 0), or None when absent or unparseable.
    """
    if value is None or not value.strip():
        return None
    text = value.strip()
    try:
        seconds = float(text)
    except ValueError:
        return _retry_after_from_date(text, now)
    if math.isnan(seconds) or math.isinf(seconds):
        return None
    return max(0.0, seconds)


def _retry_after_from_date(text: str, now: datetime | None) -> float | None:
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    reference = now or datetime.now(UTC)
    return max(0.0, (when - reference).total_seconds())
