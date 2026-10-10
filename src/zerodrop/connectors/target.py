"""NovaBill client (sync httpx). No retries: the engine owns the retry policy.

Timeouts and transport failures are mapped to typed errors with a `sent` flag so
the engine can tell a request that never left from an ambiguous write.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Self

import httpx
from pydantic import BaseModel, ValidationError

from zerodrop.connectors.errors import (
    TargetConnectionError,
    TargetHTTPError,
    TargetTimeout,
    parse_retry_after,
)
from zerodrop.models import TargetItemError

VERSION_HEADER = "NovaBill-Version"
MAX_BATCH_ITEMS = 50
LIST_PAGE_LIMIT = 100

# Transport errors raised before any request bytes could reach the server.
_NOT_SENT_ERRORS: tuple[type[Exception], ...] = (
    httpx.ConnectError,
    httpx.UnsupportedProtocol,
    httpx.ProxyError,
    httpx.LocalProtocolError,
)


class ItemResult(BaseModel):
    index: int
    status: int
    id: str | None = None
    error: TargetItemError | None = None


class BatchResult(BaseModel):
    results: list[ItemResult]
    version: str | None = None
    status_code: int


class TargetClient:
    def __init__(
        self,
        base_url: str,
        token_provider: Callable[[], str],
        timeout: float = 2.0,
        *,
        transport: httpx.BaseTransport | None = None,
        trust_env: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token_provider = token_provider
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout, transport=transport, trust_env=trust_env
        )
        self._last_version: str | None = None

    @property
    def last_version(self) -> str | None:
        """`NovaBill-Version` of the most recent response that carried the header."""
        return self._last_version

    # -- API ---------------------------------------------------------------

    def meta(self) -> dict[str, Any]:
        return self._get_object("/api/meta")

    def schema(self) -> dict[str, Any]:
        return self._get_object("/api/schema")

    def prices(self) -> list[dict[str, Any]]:
        """Rows of the `/api/prices` reference table."""
        return _items(self._get_object("/api/prices"))

    def batch(self, entity: str, items: list[dict[str, Any]]) -> BatchResult:
        """POST `{"items": items}`; each item is `{"idempotency_key": str, "payload": dict}`."""
        if not 1 <= len(items) <= MAX_BATCH_ITEMS:
            raise ValueError(f"a batch holds 1..{MAX_BATCH_ITEMS} items, got {len(items)}")
        response = self._request("POST", f"/api/{entity}:batch", json={"items": items})
        body = _json(response)
        raw_results = body.get("results") if isinstance(body, dict) else None
        if not isinstance(raw_results, list):
            raise TargetHTTPError(response.status_code, None, body)
        try:
            results = [ItemResult.model_validate(raw) for raw in raw_results]
        except ValidationError as exc:
            raise TargetHTTPError(response.status_code, None, body) from exc
        results.sort(key=lambda r: r.index)
        return BatchResult(
            results=results,
            version=response.headers.get(VERSION_HEADER),
            status_code=response.status_code,
        )

    def lookup(self, entity: str, external_id: str) -> dict[str, Any] | None:
        """The stored record with this external id, or None."""
        items = _items(self._get_object(f"/api/{entity}", params={"external_id": external_id}))
        return items[0] if items else None

    def list_page(
        self, entity: str, cursor: str | None = None, limit: int = LIST_PAGE_LIMIT
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        body = self._get_object(f"/api/{entity}", params=params)
        next_cursor = body.get("next_cursor")
        if not (next_cursor is None or isinstance(next_cursor, str)):
            raise TargetHTTPError(200, None, body)
        return _items(body), next_cursor

    def list_all(self, entity: str) -> list[dict[str, Any]]:
        """Every stored record of `entity`, following cursors."""
        records: list[dict[str, Any]] = []
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            items, cursor = self.list_page(entity, cursor)
            records.extend(items)
            if cursor is None:
                return records
            if cursor in seen:
                message = f"cursor {cursor!r} repeated while listing {entity}"
                raise TargetHTTPError(200, None, {"error": {"code": "pagination_loop", "message": message}})
            seen.add(cursor)

    # -- lifecycle -----------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- internals -----------------------------------------------------------

    def _get_object(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._request("GET", path, params=params)
        body = _json(response)
        if not isinstance(body, dict):
            raise TargetHTTPError(response.status_code, None, body)
        return body

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._token_provider().strip()}"}
        try:
            response = self._client.request(method, path, params=params, json=json, headers=headers)
        except (httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            raise TargetTimeout(sent=False) from exc
        except httpx.TimeoutException as exc:  # read or write timeout: the server may have the request
            raise TargetTimeout(sent=True) from exc
        except _NOT_SENT_ERRORS as exc:
            raise TargetConnectionError(f"{method} {path}: {type(exc).__name__}", sent=False) from exc
        except httpx.HTTPError as exc:  # read/write errors, server disconnects: possibly received
            raise TargetConnectionError(f"{method} {path}: {type(exc).__name__}", sent=True) from exc
        version = response.headers.get(VERSION_HEADER)
        if version:
            self._last_version = version
        if not 200 <= response.status_code < 300:
            raise TargetHTTPError(
                response.status_code,
                parse_retry_after(response.headers.get("Retry-After")),
                _json(response),
            )
        return response


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _items(body: dict[str, Any]) -> list[dict[str, Any]]:
    items = body.get("items")
    if not isinstance(items, list):
        raise TargetHTTPError(200, None, body)
    return items
