"""NovaBill: the strict, versioned target billing API of the sandbox.

In-memory store, JSON Schemas per version (``additionalProperties: false``),
per-item validation, idempotency keys, external-id uniqueness and admin
controls. Faults come from :mod:`zerodrop.sandbox.chaos`.
"""

import copy
import json
import re
import threading
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from pydantic import ValidationError
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from zerodrop.models import FaultPlan
from zerodrop.sandbox.chaos import FaultInjector, FaultOutcome, coerce_plan, interruptible_sleep

DEFAULT_TOKEN = "nb_live_local_demo_token"
ROTATED_TOKEN = "nb_live_rotated_token"
DEFAULT_ADMIN_TOKEN = "nb_admin_local"
VERSIONS: tuple[str, ...] = ("v1", "v2")
ENTITIES: tuple[str, ...] = ("customers", "subscriptions", "invoices")
ID_PREFIX: dict[str, str] = {"customers": "cus", "subscriptions": "sub", "invoices": "inv"}
MAX_BATCH_ITEMS = 50
DEFAULT_PAGE = 100
MAX_PAGE = 200

ISO_UTC_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$"
EMAIL_PATTERN = r"^[^A-Z\s@]+@[^A-Z\s@]+\.[^A-Z\s@]+$"
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


def _ext_id(noun: str) -> dict[str, Any]:
    return {
        "type": "string",
        "minLength": 1,
        "maxLength": 64,
        "description": f"Identifier of this {noun} in the system you are importing from. Unique among {noun}s.",
    }


def _timestamp(description: str) -> dict[str, Any]:
    return {
        "type": "string",
        "pattern": ISO_UTC_PATTERN,
        "description": f"{description} RFC 3339 timestamp in UTC with a 'Z' suffix, e.g. 2021-03-14T18:30:00Z.",
    }


def _object(title: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "title": title,
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


def _customer_schema() -> dict[str, Any]:
    properties = {
        "external_id": _ext_id("customer"),
        "given_name": {"type": "string", "minLength": 1, "maxLength": 100, "description": "First name."},
        "family_name": {"type": "string", "minLength": 1, "maxLength": 100, "description": "Last name."},
        "email": {
            "type": "string",
            "pattern": EMAIL_PATTERN,
            "description": "Contact e-mail. Must be lower-case. Unique across customers (case-insensitive).",
        },
        "country": {
            "type": "string",
            "pattern": "^[A-Z]{2}$",
            "description": "ISO 3166-1 alpha-2 code, upper-case.",
        },
        "status": {
            "type": "string",
            "enum": ["active", "suspended", "closed"],
            "description": "Account status.",
        },
        "created_at": _timestamp("When the customer account was created."),
        "notes": {"type": ["string", "null"], "description": "Free-text notes, or null."},
    }
    required = ["external_id", "given_name", "family_name", "email", "country", "status", "created_at"]
    return _object("Customer", properties, required)


def _subscription_schema(version: str) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "external_id": _ext_id("subscription"),
        "customer_id": {
            "type": "string",
            "minLength": 1,
            "description": "NovaBill id (cus_...) of an existing customer.",
        },
    }
    if version == "v1":
        properties["plan_code"] = {
            "type": "string",
            "minLength": 1,
            "description": "lookup_key of a row in the prices reference table (GET /api/prices).",
        }
    else:
        properties["price_id"] = {
            "type": "string",
            "minLength": 1,
            "description": "id of a row in the prices reference table (GET /api/prices).",
        }
    properties |= {
        "status": {
            "type": "string",
            "enum": ["active", "delinquent", "canceled", "trialing"],
            "description": "Subscription status.",
        },
        "start_at": _timestamp("When service started."),
        "quantity": {
            "type": "integer",
            "minimum": 1,
            "description": "Number of seats (integer, at least 1).",
        },
    }
    plan_field = "plan_code" if version == "v1" else "price_id"
    required = ["external_id", "customer_id", plan_field, "status", "start_at", "quantity"]
    return _object("Subscription", properties, required)


def _invoice_schema(version: str) -> dict[str, Any]:
    currency = (
        {"type": "string", "pattern": "^[A-Za-z]{3}$", "description": "ISO 4217 currency code."}
        if version == "v1"
        else {"type": "string", "pattern": "^[a-z]{3}$", "description": "ISO 4217 currency code, lower-case."}
    )
    properties = {
        "external_id": _ext_id("invoice"),
        "customer_id": {
            "type": "string",
            "minLength": 1,
            "description": "NovaBill id (cus_...) of an existing customer.",
        },
        "subscription_id": {
            "type": ["string", "null"],
            "minLength": 1,
            "description": "NovaBill id (sub_...) of an existing subscription of the same customer, or null for one-off invoices.",
        },
        "amount_minor": {
            "type": "integer",
            "minimum": 0,
            "description": "Invoice total in the smallest unit of the currency (ISO 4217 minor units), integer >= 0.",
        },
        "currency": currency,
        "issued_at": _timestamp("When the invoice was issued."),
        "status": {"type": "string", "enum": ["paid", "open"], "description": "Payment status."},
    }
    required = ["external_id", "customer_id", "amount_minor", "currency", "issued_at", "status"]
    return _object("Invoice", properties, required)


def entity_schema(entity: str, version: str) -> dict[str, Any]:
    if version not in VERSIONS:
        raise ValueError(f"unknown NovaBill API version {version!r}")
    if entity == "customers":
        return _customer_schema()
    if entity == "subscriptions":
        return _subscription_schema(version)
    if entity == "invoices":
        return _invoice_schema(version)
    raise KeyError(entity)


def schema_document(version: str) -> dict[str, Any]:
    """The body of GET /api/schema for one API version."""
    return {
        "version": version,
        "entities": {entity: entity_schema(entity, version) for entity in ENTITIES},
        "reference_tables": {"prices": "/api/prices"},
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ItemError:
    status: int
    code: str
    field: str | None
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "field": self.field, "message": self.message}


def _invalid(field: str | None, message: str) -> ItemError:
    return ItemError(422, "invalid_value", field, message)


class _CompiledSchema:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema
        self.properties: dict[str, Any] = schema["properties"]
        self.required: list[str] = schema["required"]
        self.validators = {name: Draft202012Validator(sub) for name, sub in self.properties.items()}
        self.nullable_optional = [
            name
            for name, sub in self.properties.items()
            if name not in self.required and "null" in _types(sub)
        ]


def _types(subschema: dict[str, Any]) -> list[str]:
    declared = subschema.get("type", [])
    return [declared] if isinstance(declared, str) else list(declared)


def _field_error(
    name: str, subschema: dict[str, Any], validator: Draft202012Validator, value: Any
) -> ItemError | None:
    types = _types(subschema)
    if "integer" in types and (isinstance(value, bool) or not isinstance(value, int)):
        return _invalid(name, f"{name} must be an integer")
    if name == "email" and isinstance(value, str) and value != value.lower():
        return ItemError(422, "not_lowercase", name, "email must be lower-case")
    error = best_match(validator.iter_errors(value))
    if error is not None:
        pattern = subschema.get("pattern")
        if (
            error.validator == "pattern"
            and isinstance(value, str)
            and pattern is not None
            and value != value.lower()
            and re.search(pattern, value.lower())
        ):
            return ItemError(422, "not_lowercase", name, f"{name} must be lower-case")
        return _invalid(name, f"{name}: {error.message}")
    if subschema.get("pattern") == ISO_UTC_PATTERN and isinstance(value, str):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return _invalid(name, f"{name} is not a valid timestamp")
    return None


def schema_errors(compiled: _CompiledSchema, payload: dict[str, Any]) -> list[ItemError]:
    """Structural errors in priority order: unknown fields, missing fields, then invalid values."""
    errors = [
        ItemError(422, "unknown_field", name, f"unknown field {name!r}")
        for name in sorted(set(payload) - set(compiled.properties))
    ]
    errors += [
        ItemError(422, "missing_field", name, f"missing required field {name!r}")
        for name in compiled.required
        if name not in payload
    ]
    for name, subschema in compiled.properties.items():
        if name in payload:
            error = _field_error(name, subschema, compiled.validators[name], payload[name])
            if error is not None:
                errors.append(error)
    return errors


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


def _result(index: int, status: int, record_id: str | None, error: ItemError | None) -> dict[str, Any]:
    return {
        "index": index,
        "status": status,
        "id": record_id,
        "error": None if error is None else error.as_dict(),
    }


class NovaBillStore:
    """In-memory NovaBill data plus the per-item write rules. Not thread-safe on its own; the app locks it."""

    def __init__(self, prices: Iterable[dict[str, Any]], version: str = "v1") -> None:
        self.prices = [dict(p) for p in prices]
        self._price_ids = {p["id"] for p in self.prices}
        self._lookup_keys = {p["lookup_key"] for p in self.prices}
        self._compiled = {
            (entity, v): _CompiledSchema(entity_schema(entity, v)) for entity in ENTITIES for v in VERSIONS
        }
        self.reset(version)

    def reset(self, version: str = "v1") -> None:
        if version not in VERSIONS:
            raise ValueError(f"unknown NovaBill API version {version!r}")
        self.version = version
        self.records: dict[str, dict[str, dict[str, Any]]] = {e: {} for e in ENTITIES}
        self._by_external: dict[str, dict[str, str]] = {e: {} for e in ENTITIES}
        self._idempotency: dict[str, dict[str, str]] = {e: {} for e in ENTITIES}
        self._emails: dict[str, str] = {}
        self._sequence: Counter[str] = Counter()
        self.item_outcomes: Counter[str] = Counter()

    # -- writes -------------------------------------------------------------

    def process_batch(
        self, entity: str, items: list[dict[str, Any]], accept_first: int | None = None
    ) -> list[dict[str, Any]]:
        results = []
        for index, item in enumerate(items):
            if accept_first is not None and index >= accept_first:
                error = ItemError(503, "temporarily_unavailable", None, "Item not processed; retry it.")
                result = _result(index, 503, None, error)
            else:
                result = self._process_item(entity, index, item["idempotency_key"], item["payload"])
            self.item_outcomes[str(result["status"])] += 1
            results.append(result)
        return results

    def _process_item(self, entity: str, index: int, key: str, payload: Any) -> dict[str, Any]:
        original = self._idempotency[entity].get(key)
        if original is not None:
            return _result(index, 200, original, None)
        if not isinstance(payload, dict):
            return _result(index, 422, None, _invalid(None, "payload must be a JSON object"))
        external_id = payload.get("external_id")
        if isinstance(external_id, str) and external_id in self._by_external[entity]:
            existing = self._by_external[entity][external_id]
            error = ItemError(
                409, "duplicate_external_id", "external_id", f"{external_id!r} already exists as {existing}"
            )
            return _result(index, 409, existing, error)
        error = self.validate(entity, payload)
        if error is not None:
            return _result(index, error.status, None, error)
        return _result(index, 201, self._insert(entity, key, payload), None)

    def validate(self, entity: str, payload: dict[str, Any]) -> ItemError | None:
        """First validation error for a payload under the current version, or None."""
        errors = schema_errors(self._compiled[(entity, self.version)], payload)
        if errors:
            return errors[0]
        if entity == "subscriptions":
            return self._check_subscription_refs(payload)
        if entity == "invoices":
            return self._check_invoice_refs(payload)
        if payload["email"].lower() in self._emails:  # customers; the index holds lower-cased e-mails
            return ItemError(
                422, "duplicate_email", "email", "another customer already uses this e-mail address"
            )
        return None

    def _check_subscription_refs(self, payload: dict[str, Any]) -> ItemError | None:
        if payload["customer_id"] not in self.records["customers"]:
            return ItemError(422, "invalid_reference", "customer_id", "customer does not exist")
        if self.version == "v1" and payload["plan_code"] not in self._lookup_keys:
            return ItemError(422, "invalid_reference", "plan_code", "no price with this lookup_key")
        if self.version != "v1" and payload["price_id"] not in self._price_ids:
            return ItemError(422, "invalid_reference", "price_id", "no price with this id")
        return None

    def _check_invoice_refs(self, payload: dict[str, Any]) -> ItemError | None:
        if payload["customer_id"] not in self.records["customers"]:
            return ItemError(422, "invalid_reference", "customer_id", "customer does not exist")
        subscription_id = payload.get("subscription_id")
        if subscription_id is None:
            return None
        subscription = self.records["subscriptions"].get(subscription_id)
        if subscription is None:
            return ItemError(422, "invalid_reference", "subscription_id", "subscription does not exist")
        if subscription["customer_id"] != payload["customer_id"]:
            return ItemError(
                422, "invalid_reference", "subscription_id", "subscription belongs to another customer"
            )
        return None

    def _insert(self, entity: str, key: str, payload: dict[str, Any]) -> str:
        self._sequence[entity] += 1
        record_id = f"{ID_PREFIX[entity]}_{self._sequence[entity]:06d}"
        compiled = self._compiled[(entity, self.version)]
        record: dict[str, Any] = {"id": record_id}
        record |= {name: None for name in compiled.nullable_optional}
        record |= copy.deepcopy(payload)
        self.records[entity][record_id] = record
        self._by_external[entity][payload["external_id"]] = record_id
        self._idempotency[entity][key] = record_id
        if entity == "customers":
            self._emails[payload["email"].lower()] = record_id
        return record_id

    # -- reads --------------------------------------------------------------

    def lookup(self, entity: str, external_id: str) -> list[dict[str, Any]]:
        record_id = self._by_external[entity].get(external_id)
        return [] if record_id is None else [copy.deepcopy(self.records[entity][record_id])]

    def page(self, entity: str, cursor: str | None, limit: int) -> tuple[list[dict[str, Any]], str | None]:
        ids = list(self.records[entity])  # insertion order == id order
        start = 0
        if cursor:
            start = next((i for i, rid in enumerate(ids) if rid > cursor), len(ids))
        chunk = ids[start : start + limit]
        next_cursor = chunk[-1] if chunk and start + limit < len(ids) else None
        return [copy.deepcopy(self.records[entity][rid]) for rid in chunk], next_cursor

    def dump(self, entity: str) -> list[dict[str, Any]]:
        return [copy.deepcopy(r) for r in self.records[entity].values()]

    def counts(self) -> dict[str, int]:
        return {entity: len(records) for entity, records in self.records.items()}


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}

    def response(self) -> JSONResponse:
        body = {"error": {"code": self.code, "message": self.message}}
        return JSONResponse(body, status_code=self.status, headers=self.headers)


def _check_plan_versions(plan: FaultPlan) -> None:
    for rule in plan.rules:
        if rule.kind == "schema_flip" and rule.to_version not in VERSIONS:
            raise ValueError(f"schema_flip to unknown version {rule.to_version!r}")


class _NovaBillState:
    def __init__(
        self,
        prices: Iterable[dict[str, Any]],
        token: str,
        rotated_token: str,
        admin_token: str,
        initial_version: str,
        plan: FaultPlan,
    ) -> None:
        self.lock = threading.RLock()
        self.stop_stalls = threading.Event()  # set at server shutdown: injected delays end early
        self.token, self.rotated_token, self.admin_token = token, rotated_token, admin_token
        self.initial_version = initial_version
        self.store = NovaBillStore(prices, initial_version)
        self.seed = plan.seed
        self.injector = FaultInjector(plan)
        self.status_counts: Counter[str] = Counter()
        self.batch_requests: Counter[str] = Counter()
        self.requests_total = 0

    def reset(self, seed: int, plan: FaultPlan, version: str | None) -> None:
        with self.lock:
            self.store.reset(version or self.initial_version)
            self.seed = seed
            self.injector = FaultInjector(plan)
            self.status_counts.clear()
            self.batch_requests.clear()
            self.requests_total = 0

    def stats(self) -> dict[str, Any]:
        with self.lock:
            faults = self.injector.stats()
            return {
                "version": self.store.version,
                "seed": self.seed,
                "requests": {
                    "total": self.requests_total,
                    "by_status": dict(sorted(self.status_counts.items())),
                    "batch": dict(sorted(self.batch_requests.items())),
                },
                "items": dict(sorted(self.store.item_outcomes.items())),
                "records": self.store.counts(),
                "token_revoked": faults["token_revoked"],
                "fault_plan": faults["plan"],
                "rules": faults["rules"],
                "fired": faults["fired"],
            }


class _VersionHeaderMiddleware:
    """Pure ASGI middleware: adds ``NovaBill-Version`` to every response and counts statuses.

    (Starlette's ``BaseHTTPMiddleware`` turns a request cancelled at shutdown, e.g. one stalled by
    ``timeout_after_write``, into an error traceback; a plain ASGI wrapper does not.)
    """

    def __init__(self, app: ASGIApp, state: "_NovaBillState") -> None:
        self.app, self.state = app, state

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_version(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["NovaBill-Version"] = self.state.store.version
                with self.state.lock:
                    self.state.requests_total += 1
                    self.state.status_counts[str(message["status"])] += 1
            await send(message)

        await self.app(scope, receive, send_with_version)


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None


def _unauthorized(message: str = "Missing or invalid API token.") -> ApiError:
    return ApiError(401, "invalid_token", message, {"WWW-Authenticate": 'Bearer error="invalid_token"'})


def _require_entity(entity: str) -> str:
    if entity not in ENTITIES:
        raise ApiError(404, "unknown_entity", f"unknown entity {entity!r}; expected one of {list(ENTITIES)}")
    return entity


def _parse_items(body: Any) -> list[dict[str, Any]]:
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_BATCH_ITEMS:
        raise ApiError(
            400, "invalid_request", f"body must be {{'items': [...]}} with 1..{MAX_BATCH_ITEMS} items"
        )
    for position, item in enumerate(items):
        key = item.get("idempotency_key") if isinstance(item, dict) else None
        if not isinstance(key, str) or not key or "payload" not in item:
            raise ApiError(
                400,
                "invalid_request",
                f"items[{position}] needs a non-empty 'idempotency_key' string and a 'payload'",
            )
    return items


def create_app(
    prices: Iterable[dict[str, Any]],
    token: str = DEFAULT_TOKEN,
    admin_token: str = DEFAULT_ADMIN_TOKEN,
    initial_version: str = "v1",
    *,
    rotated_token: str = ROTATED_TOKEN,
    fault_plan: FaultPlan | dict[str, Any] | None = None,
) -> FastAPI:
    """Build the NovaBill app. ``fault_plan`` can also be (re)installed later via POST /_admin/reset."""
    if initial_version not in VERSIONS:
        raise ValueError(f"unknown NovaBill API version {initial_version!r}")
    plan = coerce_plan(fault_plan)
    _check_plan_versions(plan)
    state = _NovaBillState(prices, token, rotated_token, admin_token, initial_version, plan)
    app = FastAPI(title="NovaBill API (sandbox)", version="2.0")
    app.state.novabill = state
    app.state.stop_stalls = state.stop_stalls

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return exc.response()

    app.add_middleware(_VersionHeaderMiddleware, state=state)

    def authorize_read(request: Request, entity: str | None = None) -> None:
        presented = _bearer(request)
        if presented == state.rotated_token:
            return
        if presented == state.token:
            if not state.injector.token_revoked():
                return
            state.injector.note_revoked_read(entity)
            raise _unauthorized("The API token has been revoked. Use the rotated credentials.")
        raise _unauthorized()

    def require_admin(request: Request) -> None:
        if request.headers.get("x-admin-token") != state.admin_token:
            raise ApiError(401, "invalid_admin_token", "Missing or invalid X-Admin-Token.")

    @app.get("/api/meta")
    async def meta() -> dict[str, Any]:
        return {"api_version": state.store.version}

    @app.get("/api/schema")
    async def schema() -> dict[str, Any]:
        return schema_document(state.store.version)

    @app.get("/api/prices")
    async def prices_table() -> dict[str, Any]:
        return {"items": [dict(p) for p in state.store.prices]}

    @app.post("/api/{entity}:batch")
    async def batch(entity: str, request: Request) -> JSONResponse:
        presented = _bearer(request)
        if presented not in (state.token, state.rotated_token):
            raise _unauthorized()
        _require_entity(entity)
        # A malformed envelope is refused before fault evaluation: it never advances or consumes a rule.
        items = _parse_items(await _json_body(request))
        with state.lock:
            state.batch_requests[entity] += 1
        outcome = state.injector.evaluate(entity, original_token=presented == state.token)
        if outcome.flip_to is not None:
            with state.lock:
                state.store.version = outcome.flip_to
        if outcome.delay_s > 0:
            await interruptible_sleep(outcome.delay_s, state.stop_stalls)
        if outcome.reject is not None:
            rejection = outcome.reject
            return JSONResponse(rejection.body(), status_code=rejection.status, headers=rejection.headers)
        return await _commit_batch(entity, items, outcome)

    async def _commit_batch(entity: str, items: list[dict[str, Any]], outcome: FaultOutcome) -> JSONResponse:
        with state.lock:
            results = state.store.process_batch(entity, items, outcome.accept_first)
        if outcome.stall_s > 0:  # timeout-after-write: the batch is already committed
            await interruptible_sleep(outcome.stall_s, state.stop_stalls)
        return JSONResponse({"results": results})

    @app.get("/api/{entity}")
    async def list_or_lookup(
        entity: str,
        request: Request,
        external_id: str | None = None,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
    ) -> dict[str, Any]:
        authorize_read(request, entity if entity in ENTITIES else None)
        _require_entity(entity)
        with state.lock:
            if external_id is not None:
                return {"items": state.store.lookup(entity, external_id)}
            items, next_cursor = state.store.page(entity, cursor, limit)
        return {"items": items, "next_cursor": next_cursor}

    @app.post("/_admin/reset", include_in_schema=False)
    async def admin_reset(request: Request) -> dict[str, Any]:
        require_admin(request)
        body = await _json_body(request, allow_empty=True) or {}
        if not isinstance(body, dict):
            raise ApiError(400, "invalid_request", "body must be a JSON object")
        try:
            plan = coerce_plan(body.get("fault_plan"))
            _check_plan_versions(plan)
            seed = int(body.get("seed", plan.seed))
        except (ValidationError, ValueError, TypeError) as exc:
            raise ApiError(400, "invalid_request", str(exc)) from exc
        version = body.get("version")
        if version is not None and version not in VERSIONS:
            raise ApiError(400, "invalid_request", f"unknown version {version!r}")
        state.reset(seed, plan, version)
        return {"ok": True, "seed": seed, "version": state.store.version}

    @app.get("/_admin/stats", include_in_schema=False)
    async def admin_stats(request: Request) -> dict[str, Any]:
        require_admin(request)
        return state.stats()

    @app.get("/_admin/dump/{entity}", include_in_schema=False)
    async def admin_dump(entity: str, request: Request) -> dict[str, Any]:
        require_admin(request)
        _require_entity(entity)
        with state.lock:
            return {"items": state.store.dump(entity)}

    return app


async def _json_body(request: Request, allow_empty: bool = False) -> Any:
    raw = await request.body()
    if not raw.strip():
        if allow_empty:
            return None
        raise ApiError(400, "invalid_request", "request body must be JSON")
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise ApiError(400, "invalid_request", "request body must be valid JSON") from exc
