"""LegacyBill: the read-only export API of the old billing system (sandbox, no auth).

Pages are ordered by source id and the cursor is the last id of the previous page.
``/count`` deliberately includes soft-deleted customers. When a fault plan is given,
its ``entity=None`` rules of kind rate_limit / server_error / slow apply to the
paginated list requests (not to account, docs or count).
"""

import bisect
import threading
from typing import Annotated, Any, Protocol

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from zerodrop.models import FaultPlan
from zerodrop.sandbox.chaos import SOURCE_FAULT_KINDS, FaultInjector, interruptible_sleep
from zerodrop.sandbox.fixtures import SOURCE_ID_FIELD

DEFAULT_PAGE = 100
MAX_PAGE = 200


class SourceDataset(Protocol):
    source: dict[str, list[dict[str, Any]]]
    account: dict[str, Any]
    field_docs: dict[str, dict[str, str]]


class _UnknownEntity(Exception):
    def __init__(self, entity: str) -> None:
        super().__init__(entity)
        self.entity = entity


def create_app(dataset: SourceDataset, fault_plan: FaultPlan | dict[str, Any] | None = None) -> FastAPI:
    tables = {
        entity: sorted(dataset.source.get(entity, []), key=lambda r, f=field: r[f])
        for entity, field in SOURCE_ID_FIELD.items()
    }
    ids = {entity: [r[SOURCE_ID_FIELD[entity]] for r in rows] for entity, rows in tables.items()}
    injector = FaultInjector(fault_plan, kinds=SOURCE_FAULT_KINDS, any_entity_only=True)

    app = FastAPI(title="LegacyBill export API (sandbox)", version="3.2")
    app.state.injector = injector
    app.state.stop_stalls = stop_stalls = threading.Event()  # set at server shutdown

    @app.exception_handler(_UnknownEntity)
    async def _unknown(_: Request, exc: _UnknownEntity) -> JSONResponse:
        message = f"unknown entity {exc.entity!r}; expected one of {sorted(tables)}"
        return JSONResponse({"error": {"code": "unknown_entity", "message": message}}, status_code=404)

    def rows_for(entity: str) -> list[dict[str, Any]]:
        if entity not in tables:
            raise _UnknownEntity(entity)
        return tables[entity]

    @app.get("/api/account")
    async def account() -> dict[str, Any]:
        return dict(dataset.account)

    @app.get("/api/docs/fields")
    async def field_docs() -> dict[str, Any]:
        return {entity: dict(fields) for entity, fields in dataset.field_docs.items()}

    @app.get("/api/{entity}/count")
    async def count(entity: str) -> dict[str, int]:
        return {"count": len(rows_for(entity))}

    @app.get("/api/{entity}", response_model=None)
    async def list_records(
        entity: str,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
    ) -> dict[str, Any] | JSONResponse:
        rows = rows_for(entity)
        outcome = injector.evaluate(entity)
        if outcome.delay_s > 0:
            await interruptible_sleep(outcome.delay_s, stop_stalls)
        if outcome.reject is not None:
            rejection = outcome.reject
            return JSONResponse(rejection.body(), status_code=rejection.status, headers=rejection.headers)
        start = bisect.bisect_right(ids[entity], cursor) if cursor else 0
        page = rows[start : start + limit]
        next_cursor = page[-1][SOURCE_ID_FIELD[entity]] if page and start + limit < len(rows) else None
        return {"items": page, "next_cursor": next_cursor}

    return app
