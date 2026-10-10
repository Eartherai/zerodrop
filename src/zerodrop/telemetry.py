"""Neatlogs integration: initialise once per process, no-op when no key is configured.

Every module traces through this file so the SDK is imported and initialised in
exactly one place. `init_telemetry()` must run before a model SDK (`anthropic`,
`google.genai`) is imported anywhere (the CLI and API entry points call it first).
"""

from __future__ import annotations

import contextlib
import functools
import os
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

_enabled = False


def init_telemetry(workflow_name: str = "zerodrop-migration", tags: list[str] | None = None) -> bool:
    """Initialise Neatlogs if NEATLOGS_API_KEY is set. Returns True when tracing is active."""
    global _enabled
    if _enabled:
        return True
    api_key = os.getenv("NEATLOGS_API_KEY")
    if not api_key:
        return False
    import neatlogs

    neatlogs.init(api_key=api_key, workflow_name=workflow_name, tags=tags or [])
    _enabled = True
    return True


def enabled() -> bool:
    return _enabled


def wrap_client(client: Any) -> Any:
    """Wrap a model client (Anthropic or google-genai) so every model call becomes an LLM span (no manual LLM spans elsewhere)."""
    if not _enabled:
        return client
    import neatlogs

    return neatlogs.wrap(client)


def span(kind: str, name: str | None = None, **kwargs: Any) -> Callable[[F], F]:
    """Decorator: a Neatlogs span when tracing is active, otherwise the function unchanged.

    The check happens at call time so modules can be imported before init_telemetry().
    """

    def decorator(fn: F) -> F:
        traced: Callable[..., Any] | None = None

        @functools.wraps(fn)
        def wrapper(*args: Any, **kw: Any) -> Any:
            nonlocal traced
            if not _enabled:
                return fn(*args, **kw)
            if traced is None:
                import neatlogs

                traced = neatlogs.span(kind=kind, name=name or fn.__name__, **kwargs)(fn)
            return traced(*args, **kw)

        return wrapper  # type: ignore[return-value]

    return decorator


@contextlib.contextmanager
def trace(name: str, kind: str = "TOOL", **attributes: Any) -> Iterator[Any]:
    """Context manager span; yields the span (or None when tracing is off)."""
    if not _enabled:
        yield None
        return
    import neatlogs

    with neatlogs.trace(name, kind=kind, **attributes) as s:
        yield s


def set_attr(span_obj: Any, key: str, value: Any) -> None:
    if span_obj is None:
        return
    with contextlib.suppress(Exception):
        span_obj.set_attribute(key, value)


def current_trace_id() -> str | None:
    """The active Neatlogs trace id (32 hex characters), or None when tracing is off or no span is active.

    Neatlogs keeps its spans in a private context, so the id is read the supported way: from the
    W3C ``traceparent`` header the SDK writes for outbound propagation.
    """
    if not _enabled:
        return None
    with contextlib.suppress(Exception):
        import neatlogs

        carrier: dict[str, str] = {}
        if neatlogs.inject_trace_context(carrier):
            parts = carrier.get("traceparent", "").split("-")
            if len(parts) == 4 and len(parts[1]) == 32 and int(parts[1], 16) != 0:
                return parts[1]
    return None


def log(message: str, level: str = "info", **data: Any) -> None:
    if not _enabled:
        return
    import neatlogs

    with contextlib.suppress(Exception):
        neatlogs.log(message, level=level, **data)


def shutdown() -> None:
    global _enabled
    if not _enabled:
        return
    import neatlogs

    neatlogs.flush()
    neatlogs.shutdown()
    _enabled = False
