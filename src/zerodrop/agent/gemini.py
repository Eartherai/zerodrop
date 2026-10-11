"""Gemini as a second planner provider: an adapter behind `llm.LLMBackend`.

`GeminiBackend.create` receives the Anthropic-shaped request `LLMClient.build_request` emits,
calls `client.models.generate_content` (google-genai SDK, Gemini Developer API) and returns an
Anthropic-shaped message, so the tool loop, the planner and the diagnoser are provider-neutral.

`google.genai` is imported lazily (inside `GeminiBackend`), like `anthropic` in `llm.py`.

Translation rules (from Google's generateContent docs and the installed SDK; no live call was
made while writing this, see hackathon.md):
- thinking models sign their parts (`thought_signature`) and expect model turns back exactly
  as received, so every block keeps its raw response part and model turns are rebuilt from
  those parts: same objects, same order, nothing merged or dropped;
- a tool turn also finishes with STOP: tool use is detected from function-call parts;
- a function response needs the function name (and the call id when Gemini sent one), which an
  Anthropic `tool_result` does not carry: it is looked up from the earlier call;
- request, contents and config are plain dicts, so tests need no SDK types and the Neatlogs
  wrapper (which reads dict tools) records the tool definitions.
"""

from __future__ import annotations

import itertools
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from zerodrop import telemetry
from zerodrop.agent.llm import LLMError, MalformedModelOutput

TRANSLATED_REQUEST_KEYS = frozenset({"model", "max_tokens", "system", "messages", "tools", "output_config"})
# Anthropic-only request keys, dropped on purpose: Gemini thinking is steered by thinking_level
# (from output_config.effort), caching is implicit, there is no server-side fallback, and
# tool_choice "auto" is function-calling mode AUTO, which is always sent. Per-block
# `cache_control` and per-tool `eager_input_streaming` are dropped the same way (only named
# fields are read). Any other key is an error rather than a silent drop.
DROPPED_REQUEST_KEYS = frozenset({"thinking", "cache_control", "tool_choice", "betas", "fallbacks"})
# effort -> thinking_level; every current Gemini 3 text model accepts low, medium and high.
THINKING_LEVELS = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}
# Finish reasons that mean "output blocked": reported as a refusal, the reason is the category.
REFUSAL_FINISH_REASONS = frozenset(
    {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "LANGUAGE"}
)

RETRY_HINT = re.compile(r"retry in ([0-9]+(?:\.[0-9]+)?)s")
SERVER_ERROR_CODES = frozenset({500, 502, 503, 504})
MAX_SERVER_ERROR_RETRIES = 5  # waits of 2, 4, 8, 16 and 30 s: one minute in total
MAX_SERVER_ERROR_WAIT_S = 30.0
CHARS_PER_TOKEN_ESTIMATE = 3
DEFAULT_RATE_LIMIT_WAIT_S = 20.0
MAX_RATE_LIMIT_WAIT_S = 65.0


@dataclass
class GeminiBlock:
    """One response part in the block vocabulary `llm.normalize_response` reads, plus the part itself."""

    type: str  # "text", "tool_use", or "thinking" for parts that are only echoed back
    part: Any  # the raw response part: sent back verbatim (it may carry a thought signature)
    text: str | None = None
    id: str | None = None
    name: str | None = None
    input: Any = None


@dataclass
class GeminiUsage:
    input_tokens: int = 0  # uncached prompt tokens
    output_tokens: int = 0  # visible output plus thinking (both bill at the output rate)
    cache_creation_input_tokens: int = 0  # always 0: implicit caching has no write surcharge
    cache_read_input_tokens: int = 0


@dataclass
class GeminiStopDetails:
    category: str | None = None


@dataclass
class GeminiMessage:
    content: list[GeminiBlock]
    stop_reason: str
    model: str
    usage: GeminiUsage
    stop_details: GeminiStopDetails | None = None


class GeminiBackend:
    """The Gemini backend: a telemetry-wrapped `genai.Client` behind the `LLMBackend` protocol."""

    def __init__(
        self,
        api_key: str,
        *,
        attempts: int = 3,
        timeout_s: float = 300.0,
        client: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        max_rate_limit_waits: int = 12,
        max_server_error_retries: int = MAX_SERVER_ERROR_RETRIES,
    ) -> None:
        if client is None:  # tests inject a fake or an offline SDK client
            from google import genai  # lazy: telemetry must initialise before the SDK is imported

            # Key and API flavour are passed explicitly so ambient GOOGLE_* variables cannot change
            # them. The SDK has no timeout and no retries unless told (timeout is in milliseconds).
            client = genai.Client(
                api_key=api_key,
                vertexai=False,
                http_options={"timeout": int(timeout_s * 1000), "retry_options": {"attempts": attempts}},
            )
        self._client = telemetry.wrap_client(client)  # the only capture: no manual LLM span elsewhere
        self._leaks: Callable[[str], bool] = lambda text: bool(api_key) and api_key in text
        self._ids = itertools.count(1)
        self._sleep = sleep
        self._max_rate_limit_waits = max_rate_limit_waits
        self._max_server_error_retries = max_server_error_retries

    def create(self, request: dict[str, Any]) -> GeminiMessage:
        undecided = set(request) - TRANSLATED_REQUEST_KEYS - DROPPED_REQUEST_KEYS
        if undecided:
            raise ValueError(f"request keys with no Gemini translation: {', '.join(sorted(undecided))}")
        contents, config = _contents(request["messages"]), _config(request)
        waits = busy = 0
        while True:
            try:
                response = self._client.models.generate_content(
                    model=request["model"], contents=contents, config=config
                )
            except Exception as exc:  # SDK errors pass through; their text ends up in the public run record
                if self._leaks(str(exc)):
                    raise LLMError(
                        f"the Gemini request failed ({type(exc).__name__}); the error text contained "
                        "the API key and was withheld"
                    ) from None
                if getattr(exc, "code", None) in SERVER_ERROR_CODES:
                    # The provider is overloaded or briefly down: wait longer each time, then give up.
                    if busy >= self._max_server_error_retries:
                        raise
                    busy += 1
                    self._sleep(min(2.0**busy, MAX_SERVER_ERROR_WAIT_S))
                    continue
                delay = _rate_limit_delay(exc)
                if delay is None or waits >= self._max_rate_limit_waits:
                    raise
                waits += 1
                self._sleep(delay)  # a per-minute quota 429 means "wait", not "broken" (as for NovaBill)
                continue
            return self._message(response, request["model"], contents)

    def _message(self, response: Any, requested_model: str, contents: list[dict[str, Any]]) -> GeminiMessage:
        model = getattr(response, "model_version", None) or requested_model
        meta = getattr(response, "usage_metadata", None)
        # No usage metadata at all would make the call look free to the cost cap: estimate it high.
        usage = _usage(meta) if meta is not None else _estimated_usage(contents, response)

        def malformed(problem: str) -> MalformedModelOutput:
            # the partial carries the billed tokens, so LLMClient still accounts for the call
            return MalformedModelOutput(problem, partial=GeminiMessage([], "malformed", model, usage))

        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            blocked = _name(getattr(getattr(response, "prompt_feedback", None), "block_reason", None))
            if blocked is None:
                raise malformed("Gemini returned no candidates and no block reason")
            return GeminiMessage([], "refusal", model, usage, GeminiStopDetails(blocked.lower()))
        candidate = candidates[0]
        reason = _name(getattr(candidate, "finish_reason", None))
        if reason in REFUSAL_FINISH_REASONS:
            return GeminiMessage([], "refusal", model, usage, GeminiStopDetails(str(reason).lower()))
        if reason not in ("STOP", "MAX_TOKENS"):  # MALFORMED_FUNCTION_CALL, OTHER, ... and unknown ones
            raise malformed(f"Gemini ended the turn with finish reason {reason}")
        parts = getattr(getattr(candidate, "content", None), "parts", None) or []
        blocks = [self._block(part) for part in parts]
        if reason == "MAX_TOKENS":  # the limit covers thinking too, so the content may be empty
            return GeminiMessage(blocks, "max_tokens", model, usage)
        calls = [b for b in blocks if b.type == "tool_use"]
        if any(not b.name for b in calls):
            raise malformed("Gemini returned a function call without a name")
        return GeminiMessage(blocks, "tool_use" if calls else "end_turn", model, usage)

    def _block(self, part: Any) -> GeminiBlock:
        call = getattr(part, "function_call", None)
        if call is not None:
            # ids are needed to pair results with calls; Gemini 3 sends one, older models may not
            call_id = getattr(call, "id", None) or f"gemini_call_{next(self._ids):04d}"
            args = getattr(call, "args", None)
            return GeminiBlock(
                "tool_use", part, id=call_id, name=getattr(call, "name", None), input=dict(args or {})
            )
        text = getattr(part, "text", None)
        if text is not None and not getattr(part, "thought", None):
            return GeminiBlock("text", part, text=text)
        return GeminiBlock("thinking", part)  # thought summaries and anything else: echo only


def _name(value: Any) -> str | None:
    """Upper-case name of an SDK enum member or a plain string (the SDK enum lags the REST one)."""
    return None if value is None else str(getattr(value, "name", value)).upper()


def _usage(meta: Any) -> GeminiUsage:
    def count(name: str) -> int:
        value = getattr(meta, name, None)  # every count is optional: absent means None, not 0
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    cached = count("cached_content_token_count")  # already included in prompt_token_count
    return GeminiUsage(
        # tool-use prompt tokens are added on top: this can only overcount (the safe side)
        input_tokens=max(count("prompt_token_count") - cached, 0) + count("tool_use_prompt_token_count"),
        output_tokens=count("candidates_token_count") + count("thoughts_token_count"),
        cache_read_input_tokens=cached,
    )


def _estimated_usage(contents: list[dict[str, Any]], response: Any) -> GeminiUsage:
    """Usage guessed from text sizes at three characters per token (ordinary text is nearer four)."""
    candidates = getattr(response, "candidates", None) or []
    parts = getattr(getattr(candidates[0], "content", None), "parts", None) or [] if candidates else []
    sent, received = len(repr(contents)), sum(len(repr(part)) for part in parts)
    return GeminiUsage(
        input_tokens=sent // CHARS_PER_TOKEN_ESTIMATE + 1,
        output_tokens=received // CHARS_PER_TOKEN_ESTIMATE + 1,
        cache_read_input_tokens=0,
    )


def _config(request: dict[str, Any]) -> dict[str, Any]:
    config: dict[str, Any] = {
        "system_instruction": "\n\n".join(block["text"] for block in request["system"]),
        "max_output_tokens": request["max_tokens"],
        "automatic_function_calling": {"disable": True},  # the tool loop executes tools, not the SDK
    }
    level = THINKING_LEVELS.get(request.get("output_config", {}).get("effort"))
    if level:  # an unknown effort leaves the model's default level
        config["thinking_config"] = {"thinking_level": level}
    if request.get("tools"):
        declarations = [
            # the raw JSON Schema; jsonschema validation in the tool loop stays the real check
            {"name": t["name"], "description": t["description"], "parameters_json_schema": t["input_schema"]}
            for t in request["tools"]
        ]
        config["tools"] = [{"function_declarations": declarations}]
        config["tool_config"] = {"function_calling_config": {"mode": "AUTO"}}
    return config


def _contents(messages: list[Any]) -> list[dict[str, Any]]:
    """A fresh Gemini history; `messages` and its blocks are never mutated."""
    contents: list[dict[str, Any]] = []
    calls: dict[str, Any] = {}  # tool_use id -> the block that made the call
    for message in messages:
        content = message["content"]
        if message["role"] == "assistant":
            role, parts = "model", [_raw_part(block) for block in content]
            calls.update({b.id: b for b in content if b.type == "tool_use"})
        elif isinstance(content, str):
            role, parts = "user", [{"text": content}]
        else:
            role, parts = "user", _user_parts(content, calls)
        if not parts:
            continue  # a model turn without parts is not sent back
        if role == "user" and contents and contents[-1]["role"] == "user":
            # keep roles alternating after a skipped model turn
            previous = contents[-1]["parts"]
            if "function_response" in previous[-1] and all(set(part) == {"text"} for part in parts):
                # text beside function responses is not documented: carry it as the response's note
                answer = previous[-1]["function_response"]["response"]
                texts = [answer["note"]] if "note" in answer else []
                answer["note"] = "\n".join(texts + [part["text"] for part in parts])
            else:
                previous.extend(parts)
        else:
            contents.append({"role": role, "parts": parts})
    return contents


def _raw_part(block: Any) -> Any:
    part = getattr(block, "part", None)
    if part is None:
        raise ValueError("assistant history block without its Gemini part (history from another provider?)")
    return part


def _user_parts(blocks: list[dict[str, Any]], calls: dict[str, Any]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for block in blocks:
        if block["type"] == "tool_result":
            call = calls.get(block["tool_use_id"])
            if call is None:
                raise ValueError(f"tool_result {block['tool_use_id']!r} has no function call in the history")
            # the text stays one string value: a parsed object could be read as a media reference
            answer: dict[str, Any] = {
                "name": call.name,
                "response": {"error" if block.get("is_error") else "output": block["content"]},
            }
            original_id = getattr(call.part.function_call, "id", None)
            if original_id:  # a synthesised id is ours, not Gemini's
                answer["id"] = original_id
            parts.append({"function_response": answer})
        elif parts and "function_response" in parts[-1]:
            # the loop's turn note: carried inside the last response, because text beside
            # function responses in one turn is not documented
            parts[-1]["function_response"]["response"]["note"] = block["text"]
        else:
            parts.append({"text": block["text"]})
    return parts


def _rate_limit_delay(exc: Exception) -> float | None:
    """Seconds to wait before retrying a per-minute quota 429; None when waiting cannot help."""
    if getattr(exc, "code", None) != 429:
        return None
    text = str(exc)
    if "PerDay" in text:  # a daily quota does not come back within a run
        return None
    hint = RETRY_HINT.search(text)
    if hint is None:
        return DEFAULT_RATE_LIMIT_WAIT_S
    return min(float(hint.group(1)) + 1.0, MAX_RATE_LIMIT_WAIT_S)
