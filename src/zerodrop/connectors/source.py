"""Read-only LegacyBill client (sync httpx). No retries: failures raise `SourceError`."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Self

import httpx

from zerodrop.connectors.errors import SourceError, parse_retry_after

MAX_PAGE_LIMIT = 200


class SourceClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 5.0,
        *,
        transport: httpx.BaseTransport | None = None,
        trust_env: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout, transport=transport, trust_env=trust_env
        )

    # -- API ---------------------------------------------------------------

    def account(self) -> dict[str, Any]:
        return self._get_object("/api/account")

    def field_docs(self) -> dict[str, Any]:
        return self._get_object("/api/docs/fields")

    def count(self, entity: str) -> int:
        body = self._get_object(f"/api/{entity}/count")
        count = body.get("count")
        if isinstance(count, bool) or not isinstance(count, int):
            raise SourceError(f"source count for {entity} is not an integer", status=200, body=body)
        return count

    def page(
        self, entity: str, cursor: str | None = None, limit: int = MAX_PAGE_LIMIT
    ) -> tuple[list[dict[str, Any]], str | None]:
        """One page of records and the next cursor (None on the last page)."""
        params: dict[str, Any] = {"limit": _clamp_limit(limit)}
        if cursor is not None:
            params["cursor"] = cursor
        body = self._get_object(f"/api/{entity}", params=params)
        items = body.get("items")
        next_cursor = body.get("next_cursor")
        if not isinstance(items, list) or not (next_cursor is None or isinstance(next_cursor, str)):
            raise SourceError(f"malformed page for {entity}", status=200, body=body)
        return items, next_cursor

    def iter_records(self, entity: str, limit: int = MAX_PAGE_LIMIT) -> Iterator[dict[str, Any]]:
        """Every record of `entity`, following cursors in the source's stable order."""
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            items, cursor = self.page(entity, cursor, limit)
            yield from items
            if cursor is None:
                return
            if cursor in seen:
                raise SourceError(f"pagination loop for {entity}: cursor {cursor!r} repeated")
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
        try:
            response = self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise SourceError(f"source timed out: GET {path}", timeout=True) from exc
        except httpx.HTTPError as exc:
            raise SourceError(f"source connection failed: GET {path}: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise SourceError(
                f"source responded {response.status_code}: GET {path}",
                status=response.status_code,
                retry_after=parse_retry_after(response.headers.get("Retry-After")),
                body=_body(response),
            )
        body = _body(response)
        if not isinstance(body, dict):
            raise SourceError(f"source returned a non-object body: GET {path}", status=200, body=body)
        return body


def _clamp_limit(limit: int) -> int:
    return max(1, min(MAX_PAGE_LIMIT, int(limit)))


def _body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text
