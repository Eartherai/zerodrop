"""Model access for the agent loops: Anthropic client, usage and cost accounting, budget guard, tool loop.

`anthropic` is imported lazily (inside `AnthropicBackend`) because
`telemetry.init_telemetry()` must run before the SDK is first imported.

Request shape for Claude Opus 5.5 (per the claude-api skill):
- thinking is always on: we send ``{"type": "adaptive"}`` and steer depth with
  ``output_config.effort`` (the Opus 5.5 default is ``medium``; we set it explicitly);
- forced ``tool_choice`` (``any``/``tool``) is a 400, so we use ``auto`` and the
  prompt tells the model which tool ends the task; the loop checks a call happened;
- no assistant prefill; history is append-only (preserved thinking);
- server-side refusal fallback: ``fallbacks="default"`` under beta
  ``server-side-fallback-2026-07-01``; ``response.model`` records who served;
- prompt caching: an explicit breakpoint on the system block (caches tools +
  system) plus top-level automatic caching for the growing conversation tail;
- streaming with ``get_final_message()`` and ``eager_input_streaming`` on client
  tools, so every tool input is validated client-side before it runs.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

import jsonschema
from pydantic import ValidationError

from zerodrop import telemetry
from zerodrop.agent.prompts import untrusted_block
from zerodrop.config import Settings

FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models that accept `fallbacks="default"` (Claude API); other models get no fallback parameter.
FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"})
DEFAULT_MAX_TOKENS = 32_000  # streaming: room for adaptive thinking plus a full plan
NONSTREAMING_MAX_TOKENS = 16_000  # the SDK default ceiling for non-streaming requests
MAX_TOKENS_CEILING = 64_000
MAX_TOOL_RESULT_CHARS = 60_000


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Base class for every error raised by the agent layer."""


class LLMConfigError(LLMError):
    """The model cannot be called (no API key configured)."""


class BudgetExceeded(LLMError):
    """Another model call would exceed `max_llm_calls` or `max_cost_usd`."""


class MalformedModelOutput(LLMError):
    """The streamed response could not be parsed (e.g. invalid tool-input JSON).

    `partial` is the message snapshot received before the failure, when available,
    so the tokens already billed can still be accounted for.
    """

    def __init__(self, message: str, partial: Any = None) -> None:
        super().__init__(message)
        self.partial = partial


class AgentError(LLMError):
    """An agent loop ended without an accepted submission."""


class AgentRefused(AgentError):
    """The model (and its server-side fallback) declined the request."""

    def __init__(self, message: str, category: str | None = None) -> None:
        super().__init__(message)
        self.category = category


class AgentTruncated(AgentError):
    """The model hit max_tokens (after one retry with a larger limit, unless already at the ceiling)."""


class AgentGaveUp(AgentError):
    """The model stopped twice without calling the submit tool."""


class AgentTurnsExhausted(AgentError):
    """The loop reached its model-turn limit without an accepted submission."""


# ---------------------------------------------------------------------------
# Pricing and usage accounting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelPricing:
    """USD per million tokens."""

    input: float
    output: float
    cache_write_5m: float
    cache_write_1h: float
    cache_read: float

    def cost(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_write_5m_tokens: int = 0,
        cache_write_1h_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        total = (
            input_tokens * self.input
            + output_tokens * self.output
            + cache_write_5m_tokens * self.cache_write_5m
            + cache_write_1h_tokens * self.cache_write_1h
            + cache_read_tokens * self.cache_read
        )
        return total / 1_000_000


# Opus 5.5 rates are documented in the claude-api skill ($4 / $20, 5-minute cache
# writes $5, 1-hour writes $8, cache reads $0.20). Where the skill gives only input,
# output and cache-read rates, cache writes use the generic multipliers (1.25x / 2x
# input) and missing cache-read rates use 0.1x input.
OPUS_5_5_PRICING = ModelPricing(
    input=4.00, output=20.00, cache_write_5m=5.00, cache_write_1h=8.00, cache_read=0.20
)
_OPUS_5_TIER = ModelPricing(
    input=5.00, output=25.00, cache_write_5m=6.25, cache_write_1h=10.00, cache_read=0.50
)
_SONNET_5_TIER = ModelPricing(
    input=2.00, output=10.00, cache_write_5m=2.50, cache_write_1h=4.00, cache_read=0.20
)
_FABLE_5_1_TIER = ModelPricing(
    input=10.00, output=50.00, cache_write_5m=12.50, cache_write_1h=20.00, cache_read=0.25
)
_FABLE_5_TIER = ModelPricing(
    input=10.00, output=50.00, cache_write_5m=12.50, cache_write_1h=20.00, cache_read=1.00
)
PRICING: dict[str, ModelPricing] = {
    "claude-opus-5-5": OPUS_5_5_PRICING,
    "claude-opus-5": _OPUS_5_TIER,
    "claude-opus-4-8": _OPUS_5_TIER,
    "claude-sonnet-5-5": _SONNET_5_TIER,
    "claude-sonnet-5": _SONNET_5_TIER,
    "claude-fable-5-1": _FABLE_5_1_TIER,
    "claude-mythos-5-1": _FABLE_5_1_TIER,
    "claude-fable-5": _FABLE_5_TIER,
    "claude-mythos-5": _FABLE_5_TIER,
}
# Conservative for the budget guard: every rate is at least the highest known one.
UNKNOWN_MODEL_PRICING = ModelPricing(
    input=max(p.input for p in PRICING.values()),
    output=max(p.output for p in PRICING.values()),
    cache_write_5m=max(p.cache_write_5m for p in PRICING.values()),
    cache_write_1h=max(p.cache_write_1h for p in PRICING.values()),
    cache_read=max(p.cache_read for p in PRICING.values()),
)


def price_for(model: str | None) -> ModelPricing:
    return PRICING.get(model or "", UNKNOWN_MODEL_PRICING)


@dataclass(frozen=True)
class CallUsage:
    """Token usage and cost of one model call (all attempts, including a server-side fallback)."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cost_usd: float = 0.0
    stop_reason: str | None = None
    fallback_used: bool = False


@dataclass
class UsageTotals:
    """Cumulative usage; the engine's budget guard reads `calls` and `cost_usd`."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cost_usd: float = 0.0
    served_models: dict[str, int] = field(default_factory=dict)
    refusals: int = 0
    fallbacks: int = 0
    truncations: int = 0
    max_call_cost_usd: float = 0.0

    def add(self, call: CallUsage) -> None:
        self.calls += 1
        self.input_tokens += call.input_tokens
        self.output_tokens += call.output_tokens
        self.cache_creation_input_tokens += call.cache_creation_input_tokens
        self.cache_read_input_tokens += call.cache_read_input_tokens
        self.cost_usd += call.cost_usd
        self.max_call_cost_usd = max(self.max_call_cost_usd, call.cost_usd)
        self.served_models[call.model] = self.served_models.get(call.model, 0) + 1
        self.refusals += call.stop_reason == "refusal"
        self.truncations += call.stop_reason == "max_tokens"
        self.fallbacks += call.fallback_used

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "served_models": dict(self.served_models),
            "refusals": self.refusals,
            "fallbacks": self.fallbacks,
            "truncations": self.truncations,
        }


def _int(obj: Any, name: str) -> int:
    value = getattr(obj, name, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _cache_write_split(obj: Any) -> tuple[int, int]:
    """(5-minute, 1-hour) cache-write tokens; everything counts as 5-minute without a breakdown."""
    total = _int(obj, "cache_creation_input_tokens")
    breakdown = getattr(obj, "cache_creation", None)
    one_hour = _int(breakdown, "ephemeral_1h_input_tokens") if breakdown is not None else 0
    return max(total - one_hour, 0), min(one_hour, total)


def _entry_cost(entry: Any, model: str) -> float:
    write_5m, write_1h = _cache_write_split(entry)
    return price_for(model).cost(
        input_tokens=_int(entry, "input_tokens"),
        output_tokens=_int(entry, "output_tokens"),
        cache_write_5m_tokens=write_5m,
        cache_write_1h_tokens=write_1h,
        cache_read_tokens=_int(entry, "cache_read_input_tokens"),
    )


def _iteration_cost(entry: Any, requested_model: str, served: str) -> float:
    """One `usage.iterations` entry at its own model's rates.

    A `message` entry may omit `model` (it is optional in the SDK) and can be the
    declined hop (requested model) or a serving hop (served model): price it at the
    higher of the two so the budget guard never undercounts.
    """
    model = getattr(entry, "model", None)
    if model:
        return _entry_cost(entry, model)
    return max(_entry_cost(entry, requested_model), _entry_cost(entry, served))


def usage_from_response(response: Any, requested_model: str) -> CallUsage:
    """Usage and cost of one response.

    With a server-side fallback, `usage.iterations` is the per-attempt source of
    truth (top-level usage covers only the serving attempt), so we sum every
    sampling attempt at its own model's rates. Declined attempts are counted too,
    which can only overestimate cost (the safe side for a budget guard).
    """
    served = getattr(response, "model", None) or requested_model
    usage = getattr(response, "usage", None)
    stop_reason = getattr(response, "stop_reason", None)
    if usage is None:
        return CallUsage(model=served, stop_reason=stop_reason)
    entries = [
        e
        for e in (getattr(usage, "iterations", None) or [])
        if getattr(e, "type", None) in ("message", "fallback_message")
    ]
    fallback_used = any(getattr(e, "type", None) == "fallback_message" for e in entries)
    if not entries:
        cost = _entry_cost(usage, served)
        entries = [usage]
    else:
        cost = sum(_iteration_cost(e, requested_model, served) for e in entries)
    return CallUsage(
        model=served,
        input_tokens=sum(_int(e, "input_tokens") for e in entries),
        output_tokens=sum(_int(e, "output_tokens") for e in entries),
        cache_creation_input_tokens=sum(_int(e, "cache_creation_input_tokens") for e in entries),
        cache_read_input_tokens=sum(_int(e, "cache_read_input_tokens") for e in entries),
        cost_usd=cost,
        stop_reason=stop_reason,
        fallback_used=fallback_used,
    )


# ---------------------------------------------------------------------------
# Normalized responses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any] | None
    input_error: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    content: list[Any]  # assistant blocks to append back verbatim (append-only history)
    stop_reason: str | None
    stop_details: Any
    model: str
    usage: CallUsage
    tool_calls: list[ToolCall]
    text: str

    @property
    def refusal_category(self) -> str | None:
        return getattr(self.stop_details, "category", None) if self.stop_details is not None else None


def _block_type(block: Any) -> str | None:
    return block.get("type") if isinstance(block, dict) else getattr(block, "type", None)


def _attr(block: Any, name: str) -> Any:
    return block.get(name) if isinstance(block, dict) else getattr(block, name, None)


def echo_content(content: Sequence[Any]) -> list[Any]:
    """Blocks to append back: after a mid-output fallback, drop the declined attempt's
    thinking / tool_use blocks that precede the last `fallback` block (per the docs)."""
    blocks = list(content)
    boundary = max((i for i, b in enumerate(blocks) if _block_type(b) == "fallback"), default=-1)
    if boundary < 0:
        return blocks
    dropped = {"thinking", "redacted_thinking", "tool_use"}
    return [b for i, b in enumerate(blocks) if i > boundary or _block_type(b) not in dropped]


def _tool_call(block: Any) -> ToolCall:
    raw = _attr(block, "input")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            return ToolCall(
                _attr(block, "id"), _attr(block, "name"), None, f"tool input is not valid JSON: {exc}"
            )
    if not isinstance(raw, dict):
        return ToolCall(_attr(block, "id"), _attr(block, "name"), None, "tool input must be a JSON object")
    return ToolCall(_attr(block, "id"), _attr(block, "name"), raw)


def normalize_response(response: Any, requested_model: str) -> LLMResponse:
    content = echo_content(getattr(response, "content", None) or [])
    return LLMResponse(
        content=content,
        stop_reason=getattr(response, "stop_reason", None),
        stop_details=getattr(response, "stop_details", None),
        model=getattr(response, "model", None) or requested_model,
        usage=usage_from_response(response, requested_model),
        tool_calls=[_tool_call(b) for b in content if _block_type(b) == "tool_use"],
        text="".join(_attr(b, "text") or "" for b in content if _block_type(b) == "text"),
    )


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class LLMBackend(Protocol):
    """Sends one Messages API request (keyword arguments of `client.beta.messages.create`)."""

    def create(self, request: dict[str, Any]) -> Any: ...


class AnthropicBackend:
    """The real backend: a telemetry-wrapped `anthropic.Anthropic` client."""

    def __init__(
        self, api_key: str, *, streaming: bool = True, max_retries: int = 3, http_client: Any = None
    ) -> None:
        import anthropic  # lazy: telemetry must initialise before the SDK is imported

        self._anthropic = anthropic
        options: dict[str, Any] = {"api_key": api_key, "max_retries": max_retries}
        if http_client is not None:  # tests inject an offline transport
            options["http_client"] = http_client
        self._client = telemetry.wrap_client(anthropic.Anthropic(**options))
        self.streaming = streaming

    def create(self, request: dict[str, Any]) -> Any:
        if not self.streaming:
            return self._client.beta.messages.create(**request)
        with self._client.beta.messages.stream(**request) as stream:
            try:
                for _ in stream:  # iterate so the telemetry wrapper sees every event
                    pass
            except ValueError as exc:  # unparseable streamed tool input; typed API errors pass through
                if isinstance(exc, self._anthropic.APIError):
                    raise
                raise MalformedModelOutput(str(exc), partial=_snapshot(stream)) from exc
            return stream.get_final_message()


def _snapshot(stream: Any) -> Any:
    try:
        return stream.current_message_snapshot
    except Exception:  # no message_start received yet, or a wrapper without the property
        return None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class LLMClient:
    """One budgeted, accounted conversation endpoint shared by the planner and the diagnoser."""

    def __init__(
        self,
        settings: Settings,
        backend: LLMBackend | None = None,
        *,
        streaming: bool = True,
        max_tokens: int | None = None,
    ) -> None:
        self.settings = settings
        self.streaming = streaming
        self.max_tokens = max_tokens or (DEFAULT_MAX_TOKENS if streaming else NONSTREAMING_MAX_TOKENS)
        if backend is None:
            if settings.zerodrop_anthropic_key is None:
                raise LLMConfigError(
                    "ZERODROP_ANTHROPIC_KEY is not set; use the fake planner or configure a key"
                )
            backend = AnthropicBackend(
                settings.zerodrop_anthropic_key.get_secret_value(), streaming=streaming
            )
        self.backend = backend
        self.usage = UsageTotals()
        self.history: list[CallUsage] = []
        self._baseline_calls = 0
        self._baseline_cost = 0.0

    @property
    def calls(self) -> int:
        return self.usage.calls

    @property
    def cost_usd(self) -> float:
        return self.usage.cost_usd

    @property
    def input_tokens(self) -> int:
        return self.usage.input_tokens

    @property
    def output_tokens(self) -> int:
        return self.usage.output_tokens

    def reset_budget(self) -> None:
        """Start a new budget window (limits apply to usage after this point; totals keep counting)."""
        self._baseline_calls = self.usage.calls
        self._baseline_cost = self.usage.cost_usd

    def ensure_budget(self) -> None:
        """Raise BudgetExceeded if one more call would break a limit.

        The next call's cost is estimated as the most expensive call so far.
        """
        calls = self.usage.calls - self._baseline_calls
        if calls + 1 > self.settings.max_llm_calls:
            raise BudgetExceeded(f"LLM call budget reached ({calls}/{self.settings.max_llm_calls} calls)")
        cost = self.usage.cost_usd - self._baseline_cost
        estimate = self.usage.max_call_cost_usd
        if cost >= self.settings.max_cost_usd or cost + estimate > self.settings.max_cost_usd:
            raise BudgetExceeded(
                f"LLM cost budget would be exceeded (${cost:.4f} spent, next call ~${estimate:.4f}, "
                f"limit ${self.settings.max_cost_usd:.2f})"
            )

    def build_request(
        self,
        *,
        system: str,
        tools: Sequence[dict[str, Any]],
        messages: list[Any],
        effort: str | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        model = self.settings.model
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens or self.max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort or self.settings.effort_plan},
            "cache_control": {"type": "ephemeral"},
        }
        if tools:
            extra = {"eager_input_streaming": True} if self.streaming else {}
            request["tools"] = [{**tool, **extra} for tool in tools]
            request["tool_choice"] = {"type": "auto"}
        if model in FALLBACK_MODELS:
            request["betas"] = [FALLBACK_BETA]
            request["fallbacks"] = "default"
        return request

    def complete(
        self,
        *,
        system: str,
        tools: Sequence[dict[str, Any]],
        messages: list[Any],
        effort: str | None = None,
    ) -> LLMResponse:
        """One model turn. Retries once with a doubled limit on max_tokens, and once on malformed output.

        Never mutates `messages`. Callers must check `stop_reason` before using content.
        """
        max_tokens = self.max_tokens
        ceiling = MAX_TOKENS_CEILING if self.streaming else NONSTREAMING_MAX_TOKENS
        malformed_retry = truncation_retry = True
        while True:
            request = self.build_request(
                system=system, tools=tools, messages=messages, effort=effort, max_tokens=max_tokens
            )
            self.ensure_budget()
            try:
                raw = self.backend.create(request)
            except MalformedModelOutput as exc:
                self._record(self._malformed_usage(exc))
                if not malformed_retry:
                    raise
                malformed_retry = False
                continue
            response = normalize_response(raw, self.settings.model)
            self._record(response.usage)
            if response.stop_reason == "max_tokens" and truncation_retry and max_tokens < ceiling:
                truncation_retry = False
                max_tokens = min(max_tokens * 2, ceiling)
                continue
            return response

    def _malformed_usage(self, exc: MalformedModelOutput) -> CallUsage:
        """Usage of a call whose stream failed to parse: its partial snapshot, else the costliest call so far."""
        model = self.settings.model
        if exc.partial is not None:
            usage = usage_from_response(exc.partial, model)
            if usage.cost_usd > 0:
                return replace(usage, stop_reason="malformed")
        return CallUsage(model=model, cost_usd=self.usage.max_call_cost_usd, stop_reason="malformed")

    def _record(self, call: CallUsage) -> None:
        self.usage.add(call)
        self.history.append(call)


# ---------------------------------------------------------------------------
# Bounded manual tool loop
# ---------------------------------------------------------------------------


class ToolInputError(Exception):
    """A tool rejected its input; the message goes back to the model as an is_error result."""


class SubmitRejected(Exception):
    """The submit tool rejected a submission; each error goes back to the model."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Tool:
    """A read-only client tool: `run` returns the tool_result text or raises (-> is_error result)."""

    name: str
    description: str
    input_schema: dict[str, Any]
    run: Callable[[dict[str, Any]], str]

    def definition(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


@dataclass(frozen=True)
class SubmitTool[T]:
    """The tool that ends the loop: `accept` returns the parsed value or raises SubmitRejected/ValidationError."""

    name: str
    description: str
    input_schema: dict[str, Any]
    accept: Callable[[dict[str, Any]], T]

    def definition(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


def format_validation_error(exc: ValidationError, limit: int = 20) -> list[str]:
    out = []
    for err in exc.errors()[:limit]:
        loc = ".".join(str(p) for p in err.get("loc", ())) or "<input>"
        out.append(f"{loc}: {err.get('msg', 'invalid')}")
    return out


def schema_errors(schema: dict[str, Any], value: Any, limit: int = 10) -> list[str]:
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(value), key=lambda e: [str(p) for p in e.absolute_path])
    return [f"{'.'.join(str(p) for p in e.absolute_path) or '<input>'}: {e.message}" for e in errors[:limit]]


def _clip(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + f"\n...[truncated {len(text) - limit} characters]"


def _result(call_id: str, text: str, is_error: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": call_id, "content": _clip(text)}
    if is_error:
        block["is_error"] = True
    return block


def _run_tool(tool: Tool | None, call: ToolCall) -> dict[str, Any]:
    with telemetry.trace(f"tool.{call.name}", kind="TOOL") as span:
        if tool is None:
            telemetry.set_attr(span, "tool.is_error", True)
            return _result(call.id, f"Error: unknown tool {call.name!r}.", is_error=True)
        if call.input is None:
            telemetry.set_attr(span, "tool.is_error", True)
            return _result(call.id, f"Error: {call.input_error}", is_error=True)
        problems = schema_errors(tool.input_schema, call.input)
        if problems:
            telemetry.set_attr(span, "tool.is_error", True)
            return _result(call.id, "Error: invalid input:\n" + "\n".join(problems), is_error=True)
        try:
            text = tool.run(call.input)
        except Exception as exc:  # tool failures go back to the model, never up the stack
            telemetry.set_attr(span, "tool.is_error", True)
            # the message can echo upstream data (source/target responses): mark it as untrusted
            detail = untrusted_block("tool_error", f"{type(exc).__name__}: {exc}")
            return _result(call.id, f"Error: the {call.name} tool failed:\n{detail}", is_error=True)
        telemetry.set_attr(span, "tool.is_error", False)
        return _result(call.id, text)


def _try_submit[T](submit: SubmitTool[T], call: ToolCall) -> tuple[T | None, dict[str, Any]]:
    with telemetry.trace(f"tool.{call.name}", kind="TOOL") as span:
        if call.input is None:
            errors = [str(call.input_error)]
        else:
            try:
                value = submit.accept(call.input)
            except ValidationError as exc:
                errors = format_validation_error(exc)
            except SubmitRejected as exc:
                errors = exc.errors
            else:
                telemetry.set_attr(span, "submit.accepted", True)
                return value, _result(call.id, "Accepted.")
        telemetry.set_attr(span, "submit.accepted", False)
        text = f"Rejected; fix these problems and call {submit.name} again:\n" + "\n".join(
            f"- {e}" for e in errors
        )
        return None, _result(call.id, text, is_error=True)


@dataclass
class LoopStats:
    turns: int = 0
    tool_calls: int = 0
    submissions: int = 0


def run_tool_loop[T](
    llm: LLMClient,
    *,
    system: str,
    user_message: str,
    tools: Sequence[Tool],
    submit: SubmitTool[T],
    max_turns: int,
    effort: str | None = None,
    nudge: str,
    stats: LoopStats | None = None,
) -> T:
    """Run the model with read-only tools until `submit` accepts a submission.

    Tool errors and rejected submissions become is_error tool results. The model is
    asked once more if it stops without submitting. History is append-only.
    """
    stats = stats if stats is not None else LoopStats()
    by_name = {t.name: t for t in tools}
    definitions = [t.definition() for t in tools] + [submit.definition()]
    messages: list[Any] = [{"role": "user", "content": user_message}]
    nudged = False
    for turn in range(1, max_turns + 1):
        stats.turns = turn
        response = llm.complete(system=system, tools=definitions, messages=messages, effort=effort)
        if response.stop_reason == "refusal":
            category = response.refusal_category
            raise AgentRefused(f"the model declined the request (category: {category})", category)
        if response.stop_reason == "max_tokens":
            raise AgentTruncated("the model response hit max_tokens (after one retry with a larger limit)")
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason == "pause_turn":
            continue  # re-send so the server resumes the paused turn
        if not response.tool_calls:
            if nudged:
                raise AgentGaveUp(f"the model stopped twice without calling {submit.name}")
            nudged = True
            messages.append({"role": "user", "content": nudge})
            continue
        results: list[dict[str, Any]] = []
        for call in response.tool_calls:
            stats.tool_calls += 1
            if call.name == submit.name:
                stats.submissions += 1
                value, block = _try_submit(submit, call)
                if value is not None:
                    return value
                results.append(block)
            else:
                results.append(_run_tool(by_name.get(call.name), call))
        content: list[dict[str, Any]] = list(results)
        remaining = max_turns - turn
        if 0 < remaining <= 2:
            content.append({"type": "text", "text": _turn_note(remaining, submit.name)})
        messages.append({"role": "user", "content": content})
    raise AgentTurnsExhausted(f"no accepted {submit.name} within {max_turns} model turns")


def _turn_note(remaining: int, submit_name: str) -> str:
    return f"Only {remaining} model turn(s) remain. Call {submit_name} as soon as your mappings pass."
