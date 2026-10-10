"""Gemini backend: request and response translation, round trip, finish reasons, usage and cost.

No test here calls a model. Most use a fake `genai` client that records the keyword arguments of
`models.generate_content`; the last section drives the real google-genai SDK over an offline
transport to check what would reach the wire.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from zerodrop.agent.gemini import GeminiBackend, GeminiBlock
from zerodrop.agent.llm import (
    PRICING,
    AgentGaveUp,
    AgentRefused,
    AgentTruncated,
    LLMClient,
    LLMConfigError,
    LLMError,
    MalformedModelOutput,
    SubmitTool,
    Tool,
    price_for,
    run_tool_loop,
)
from zerodrop.config import Settings

MODEL = "gemini-3.8-flash"
KEY = "synthetic-gemini-key-0123456789"  # test value only


@dataclass
class FakeCall:
    name: str | None
    args: Any = None
    id: str | None = None


@dataclass
class FakePart:
    text: str | None = None
    function_call: FakeCall | None = None
    thought_signature: bytes | None = None
    thought: bool | None = None


@dataclass
class FakeContent:
    parts: list[FakePart] | None
    role: str = "model"


@dataclass
class FakeCandidate:
    content: FakeContent | None
    finish_reason: Any = "STOP"


@dataclass
class FakeUsageMetadata:
    prompt_token_count: int | None = 1000
    candidates_token_count: int | None = 200
    thoughts_token_count: int | None = None
    cached_content_token_count: int | None = None
    tool_use_prompt_token_count: int | None = None


@dataclass
class FakeFeedback:
    block_reason: Any = None


@dataclass
class FakeResponse:
    candidates: list[FakeCandidate] | None
    usage_metadata: FakeUsageMetadata | None = field(default_factory=FakeUsageMetadata)
    model_version: str | None = MODEL
    prompt_feedback: FakeFeedback | None = None


class FakeModels:
    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeGenai:
    """Stands in for `genai.Client`: only `models.generate_content` exists."""

    def __init__(self, script: list[Any]) -> None:
        self.models = FakeModels(script)


def call_part(
    name: str | None, args: Any = None, id: str | None = None, signature: bytes | None = None
) -> FakePart:
    return FakePart(function_call=FakeCall(name, args, id), thought_signature=signature)


def reply(*parts: FakePart, finish: Any = "STOP", **kwargs: Any) -> FakeResponse:
    return FakeResponse([FakeCandidate(FakeContent(list(parts)), finish)], **kwargs)


def text_reply(text: str = "Done.") -> FakeResponse:
    return reply(FakePart(text=text))


def settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {"model": "claude-opus-5-5", "max_llm_calls": 30, "max_cost_usd": 1.5}
    return Settings(_env_file=None, **(base | overrides))  # type: ignore[call-arg]


def client(script: list[Any], **overrides: Any) -> tuple[LLMClient, FakeModels]:
    fake = FakeGenai(script)
    return LLMClient(settings(**overrides), GeminiBackend(KEY, client=fake), model=MODEL), fake.models


def complete(llm: LLMClient, **kwargs: Any) -> Any:
    return llm.complete(system="sys", tools=[], messages=[{"role": "user", "content": "hi"}], **kwargs)


ECHO_SCHEMA = {
    "type": "object",
    "properties": {"value": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": None}},
    "additionalProperties": False,
}


def echo_tool(log: list[Any]) -> Tool:
    def run(args: dict[str, Any]) -> str:
        log.append(args)
        if args.get("value") == -1:
            raise ValueError("negative")
        return f"echo {args.get('value')}"

    return Tool("echo", "Echo a value.", ECHO_SCHEMA, run)


def loop(llm: LLMClient, tools: list[Tool], max_turns: int = 6) -> int:
    return run_tool_loop(
        llm,
        system="sys",
        user_message="go",
        tools=tools,
        submit=SubmitTool("submit_answer", "Submit.", {"type": "object"}, lambda args: int(args["answer"])),
        max_turns=max_turns,
        nudge="call submit_answer",
    )


# ---------------------------------------------------------------------------
# Request translation
# ---------------------------------------------------------------------------


def test_request_is_translated_to_generate_content_arguments() -> None:
    llm, models = client([text_reply()])
    tool = {"name": "t", "description": "d", "input_schema": ECHO_SCHEMA}
    llm.complete(system="SYSTEM", tools=[tool], messages=[{"role": "user", "content": "hi"}], effort="medium")
    call = models.calls[0]
    assert set(call) == {"model", "contents", "config"}
    assert call["model"] == MODEL
    assert call["contents"] == [{"role": "user", "parts": [{"text": "hi"}]}]
    assert call["config"] == {
        "system_instruction": "SYSTEM",
        "max_output_tokens": 32_000,
        "automatic_function_calling": {"disable": True},
        "thinking_config": {"thinking_level": "medium"},
        # the JSON Schema goes through untouched (anyOf, default, additionalProperties included)
        "tools": [
            {
                "function_declarations": [
                    {"name": "t", "description": "d", "parameters_json_schema": ECHO_SCHEMA}
                ]
            }
        ],
        "tool_config": {"function_calling_config": {"mode": "AUTO"}},
    }
    # exact equality: no Anthropic-only key (thinking, cache_control, tool_choice) and no sampling parameter


def test_request_without_tools_sends_no_tool_configuration() -> None:
    llm, models = client([text_reply()])
    complete(llm)
    assert "tools" not in models.calls[0]["config"] and "tool_config" not in models.calls[0]["config"]


@pytest.mark.parametrize(
    ("effort", "level"),
    [("low", "low"), ("medium", "medium"), ("high", "high"), ("xhigh", "high"), ("max", "high")],
)
def test_effort_maps_to_a_thinking_level(effort: str, level: str) -> None:
    llm, models = client([text_reply()])
    complete(llm, effort=effort)
    assert models.calls[0]["config"]["thinking_config"] == {"thinking_level": level}


def test_unknown_effort_leaves_the_model_default() -> None:
    llm, models = client([text_reply()])
    complete(llm, effort="extreme")
    assert "thinking_config" not in models.calls[0]["config"]


def test_a_request_key_nobody_decided_about_is_an_error_not_a_silent_drop() -> None:
    backend = GeminiBackend(KEY, client=FakeGenai([text_reply()]))
    request = LLMClient(settings(), backend, model=MODEL).build_request(system="s", tools=[], messages=[])
    with pytest.raises(ValueError, match="top_k"):
        backend.create(request | {"top_k": 5})


def test_backend_does_not_mutate_the_request() -> None:
    llm, _ = client([reply(call_part("echo", {"value": 1}, "c1")), text_reply()])
    first = complete(llm)
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": first.content},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "ok"}]},
    ]
    snapshot = json.dumps(messages, default=repr)
    llm.complete(system="sys", tools=[], messages=messages)
    assert json.dumps(messages, default=repr) == snapshot


# ---------------------------------------------------------------------------
# Response translation
# ---------------------------------------------------------------------------


def test_text_response() -> None:
    llm, _ = client([text_reply("hello")])
    response = complete(llm)
    assert (response.stop_reason, response.text, response.tool_calls) == ("end_turn", "hello", [])
    assert response.model == MODEL


def test_one_function_call_keeps_its_id_and_arguments() -> None:
    llm, _ = client([reply(call_part("echo", {"value": 3}, "call-a"))])
    response = complete(llm)
    assert response.stop_reason == "tool_use"  # Gemini finishes tool turns with STOP
    (call,) = response.tool_calls
    assert (call.id, call.name, call.input, call.input_error) == ("call-a", "echo", {"value": 3}, None)


def test_several_function_calls_stay_in_order_one_block_per_part() -> None:
    parts = [
        FakePart(text="thinking aloud", thought=True),
        FakePart(text="I will call two tools."),
        call_part("echo", {"value": 1}, "a", signature=b"sig-1"),
        call_part("echo", {"value": 2}, "b"),
    ]
    llm, _ = client([reply(*parts)])
    response = complete(llm)
    assert [b.type for b in response.content] == ["thinking", "text", "tool_use", "tool_use"]
    assert [b.part for b in response.content] == parts  # the raw parts ride along, in order
    assert all(b.part is p for b, p in zip(response.content, parts, strict=True))
    assert response.text == "I will call two tools."  # a thought summary is not answer text
    assert [(c.id, c.input) for c in response.tool_calls] == [("a", {"value": 1}), ("b", {"value": 2})]


def test_missing_arguments_become_an_empty_object_and_missing_ids_are_synthesised() -> None:
    llm, _ = client([reply(call_part("echo"), call_part("echo"))])
    calls = complete(llm).tool_calls
    assert [c.input for c in calls] == [{}, {}]
    assert all(c.id for c in calls) and calls[0].id != calls[1].id


# ---------------------------------------------------------------------------
# Round trip through the tool loop
# ---------------------------------------------------------------------------


def test_loop_echoes_the_raw_parts_and_answers_every_call_by_name_and_id() -> None:
    log: list[Any] = []
    first = [
        FakePart(text="plan"),
        call_part("echo", {"value": 1}, "id-1", signature=b"\x00sig"),
        call_part("echo", {"value": -1}, "id-2"),
    ]
    second = [call_part("submit_answer", {"answer": 42}, "id-3", signature=b"sig-2")]
    llm, models = client([reply(*first), reply(*second)])
    assert loop(llm, [echo_tool(log)]) == 42
    assert log == [{"value": 1}, {"value": -1}]
    user, model, results = models.calls[1]["contents"]
    assert user == {"role": "user", "parts": [{"text": "go"}]}
    assert model["role"] == "model" and len(model["parts"]) == 3
    assert all(sent is raw for sent, raw in zip(model["parts"], first, strict=True))  # signatures intact
    assert results["role"] == "user"
    ok, failed = results["parts"]
    assert ok == {"function_response": {"name": "echo", "id": "id-1", "response": {"output": "echo 1"}}}
    assert failed["function_response"]["name"] == "echo" and failed["function_response"]["id"] == "id-2"
    assert "negative" in failed["function_response"]["response"]["error"]  # is_error -> {"error": ...}
    assert models.calls[0]["contents"] == [user]  # history is append-only


def test_synthesised_ids_resolve_the_name_but_are_not_sent_to_gemini() -> None:
    llm, models = client(
        [reply(call_part("echo", {"value": 5})), reply(call_part("submit_answer", {"answer": 1}))]
    )
    loop(llm, [echo_tool([])])
    (part,) = models.calls[1]["contents"][2]["parts"]
    assert part == {"function_response": {"name": "echo", "response": {"output": "echo 5"}}}


def test_the_turn_note_rides_in_the_last_function_response() -> None:
    llm, models = client(
        [reply(call_part("echo", {"value": 1}, "a")), reply(call_part("submit_answer", {"answer": 1}, "b"))]
    )
    loop(llm, [echo_tool([])], max_turns=2)
    (part,) = models.calls[1]["contents"][2]["parts"]  # no text part beside the function response
    assert part["function_response"]["response"]["output"] == "echo 1"
    assert "1 model turn(s) remain" in part["function_response"]["response"]["note"]


def test_an_empty_model_turn_is_not_sent_back() -> None:
    llm, models = client([reply(), reply(call_part("submit_answer", {"answer": 7}, "a"))])
    assert loop(llm, []) == 7
    assert models.calls[1]["contents"] == [
        {"role": "user", "parts": [{"text": "go"}, {"text": "call submit_answer"}]}
    ]


def test_text_only_turns_are_nudged_then_given_up() -> None:
    llm, models = client([text_reply("a"), text_reply("b")])
    with pytest.raises(AgentGaveUp):
        loop(llm, [])
    assert [c["role"] for c in models.calls[1]["contents"]] == ["user", "model", "user"]


def test_a_tool_result_without_its_call_is_a_clear_error() -> None:
    backend = GeminiBackend(KEY, client=FakeGenai([text_reply()]))
    llm = LLMClient(settings(), backend, model=MODEL)
    orphan = [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "nope", "content": "x"}]}]
    with pytest.raises(ValueError, match="nope"):
        llm.complete(system="s", tools=[], messages=orphan)
    foreign = [{"role": "assistant", "content": [{"type": "text", "text": "from another provider"}]}]
    with pytest.raises(ValueError, match="Gemini part"):
        llm.complete(system="s", tools=[], messages=foreign)


# ---------------------------------------------------------------------------
# Finish reasons, blocked prompts, malformed output
# ---------------------------------------------------------------------------


@dataclass
class EnumLike:
    """The SDK returns str-enum members; only `.name` is relied on."""

    name: str


def test_max_tokens_is_retried_with_a_doubled_limit_then_truncated() -> None:
    truncated = FakeResponse([FakeCandidate(FakeContent(None), EnumLike("MAX_TOKENS"))])  # empty content
    llm, models = client([truncated, truncated])
    with pytest.raises(AgentTruncated):
        loop(llm, [])
    assert [c["config"]["max_output_tokens"] for c in models.calls] == [32_000, 64_000]
    assert llm.usage.truncations == 2


@pytest.mark.parametrize(
    "reason", ["SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "LANGUAGE"]
)
def test_blocked_output_is_a_refusal_with_the_reason_as_category(reason: str) -> None:
    llm, _ = client([FakeResponse([FakeCandidate(None, EnumLike(reason))])])
    with pytest.raises(AgentRefused) as info:
        loop(llm, [])
    assert info.value.category == reason.lower() and llm.usage.refusals == 1


def test_blocked_prompt_without_candidates_is_a_refusal() -> None:
    blocked = FakeResponse(None, prompt_feedback=FakeFeedback(EnumLike("PROHIBITED_CONTENT")))
    llm, _ = client([blocked])
    response = complete(llm)
    assert (response.stop_reason, response.refusal_category, response.content) == (
        "refusal",
        "prohibited_content",
        [],
    )
    assert response.usage.input_tokens == 1000  # prompt tokens are still reported


@pytest.mark.parametrize("candidates", [None, []])
def test_no_candidates_and_no_block_reason_is_malformed_output_not_an_attribute_error(
    candidates: Any,
) -> None:
    empty = FakeResponse(candidates, prompt_feedback=None)
    llm, models = client([empty, empty])
    with pytest.raises(MalformedModelOutput, match="no candidates"):
        complete(llm)
    assert len(models.calls) == 2  # retried once by the client


@pytest.mark.parametrize(
    "reason",
    [
        "MALFORMED_FUNCTION_CALL",
        "UNEXPECTED_TOOL_CALL",
        "TOO_MANY_TOOL_CALLS",
        "MISSING_THOUGHT_SIGNATURE",
        "MALFORMED_RESPONSE",
        "OTHER",
        "FINISH_REASON_UNSPECIFIED",
        "SOMETHING_NEW",
        None,
    ],
)
def test_other_finish_reasons_are_malformed_output_retried_once_with_usage_counted(
    reason: str | None,
) -> None:
    bad = FakeResponse([FakeCandidate(None, reason)], usage_metadata=FakeUsageMetadata(2000, None, 500))
    llm, _ = client([bad, text_reply("recovered")])
    assert complete(llm).text == "recovered"
    malformed = llm.history[0]
    assert malformed.stop_reason == "malformed" and malformed.model == MODEL
    assert (malformed.input_tokens, malformed.output_tokens) == (2000, 500)
    assert malformed.cost_usd == pytest.approx((2000 * 0.75 + 500 * 3.75) / 1e6)
    bad_twice, _ = client([bad, bad])
    with pytest.raises(MalformedModelOutput, match=str(reason)):
        complete(bad_twice)


def test_a_function_call_without_a_name_is_malformed_output() -> None:
    nameless = reply(call_part(None, {"value": 1}, "x"))
    llm, _ = client([nameless, nameless])
    with pytest.raises(MalformedModelOutput, match="without a name"):
        complete(llm)


# ---------------------------------------------------------------------------
# Usage and cost
# ---------------------------------------------------------------------------


def test_usage_counts_thinking_as_output_and_cached_tokens_at_the_cache_rate() -> None:
    usage = FakeUsageMetadata(
        prompt_token_count=10_000,  # includes the cached part
        candidates_token_count=300,
        thoughts_token_count=700,
        cached_content_token_count=4_000,
        tool_use_prompt_token_count=50,
    )
    llm, _ = client([reply(FakePart(text="x"), usage_metadata=usage, model_version="gemini-3.8-flash-001")])
    call = complete(llm).usage
    assert (call.input_tokens, call.output_tokens) == (6_050, 1_000)
    assert (call.cache_read_input_tokens, call.cache_creation_input_tokens) == (4_000, 0)
    assert call.cost_usd == pytest.approx((6_050 * 0.75 + 1_000 * 3.75 + 4_000 * 0.075) / 1e6)
    assert llm.usage.served_models == {"gemini-3.8-flash-001": 1} and llm.cost_usd == call.cost_usd


def test_absent_usage_fields_count_as_zero() -> None:
    partial = reply(FakePart(text="x"), usage_metadata=FakeUsageMetadata(12, None))
    bare = reply(FakePart(text="x"), usage_metadata=None, model_version=None)
    llm, _ = client([partial, bare])
    first, second = complete(llm).usage, complete(llm)
    assert (first.input_tokens, first.output_tokens) == (12, 0)
    assert (second.usage.cost_usd, second.model) == (0.0, MODEL)  # falls back to the requested model


def test_gemini_pricing_rows_and_the_versioned_id_fallback() -> None:
    flash = price_for("gemini-3.8-flash")
    assert (flash.input, flash.output, flash.cache_read) == (0.75, 3.75, 0.075)
    lite = price_for("gemini-3.5-flash-lite")
    assert (lite.input, lite.output, lite.cache_read) == (0.30, 2.50, 0.03)
    pro = price_for("gemini-3.1-pro-preview")
    assert (pro.input, pro.output, pro.cache_read) == (4.00, 18.00, 0.40)  # the >200k tier: never undercount
    assert price_for("gemini-3.8-flash-001") is flash
    assert price_for("gemini-3.1-pro-preview-customtools") is pro
    assert price_for("gemini-3.5-flash-lite-001") is lite  # longest match, not gemini-3.5-flash
    unknown = price_for("gemini-9-ultra")  # unlisted: the conservative rates
    assert unknown.input >= max(p.input for p in PRICING.values())
    assert price_for("claude-opus-5-5-20260901") is unknown  # the fallback is for gemini ids only


def test_the_cost_cap_stops_a_gemini_run() -> None:
    from zerodrop.agent.llm import BudgetExceeded

    big = FakeUsageMetadata(prompt_token_count=1_000_000, candidates_token_count=100_000)  # $1.125
    llm, models = client([reply(FakePart(text="x"), usage_metadata=big), text_reply()])
    complete(llm)
    with pytest.raises(BudgetExceeded):
        complete(llm)
    assert len(models.calls) == 1


# ---------------------------------------------------------------------------
# Provider selection, key handling
# ---------------------------------------------------------------------------


def test_missing_gemini_key_is_a_config_error_naming_the_variable() -> None:
    with pytest.raises(LLMConfigError, match="ZERODROP_GEMINI_KEY"):
        LLMClient(settings(zerodrop_gemini_key=None, zerodrop_anthropic_key="sk-test-offline"), model=MODEL)


def test_missing_anthropic_key_still_names_its_own_variable() -> None:
    with pytest.raises(LLMConfigError, match="ZERODROP_ANTHROPIC_KEY"):
        LLMClient(settings(zerodrop_anthropic_key=None, zerodrop_gemini_key=KEY))


def test_the_model_id_selects_the_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[str] = []

    class Recording:
        def __init__(self, api_key: str, **_: Any) -> None:
            built.append(f"{type(self).__name__}:{api_key}")

    monkeypatch.setattr("zerodrop.agent.gemini.GeminiBackend", type("Gemini", (Recording,), {}))
    monkeypatch.setattr("zerodrop.agent.llm.AnthropicBackend", type("Anthropic", (Recording,), {}))
    both = settings(zerodrop_gemini_key=KEY, zerodrop_anthropic_key="sk-test-offline")
    gemini = LLMClient(both, model=MODEL)
    claude = LLMClient(both)
    assert built == [f"Gemini:{KEY}", "Anthropic:sk-test-offline"]
    assert (gemini.model, claude.model) == (MODEL, "claude-opus-5-5")
    assert gemini.build_request(system="s", tools=[], messages=[])["model"] == MODEL
    assert "fallbacks" not in gemini.build_request(system="s", tools=[], messages=[])


def test_claude_requests_are_unchanged_when_no_model_is_given() -> None:
    from zerodrop.agent.fake import ScriptedBackend

    request = LLMClient(settings(), ScriptedBackend([])).build_request(system="s", tools=[], messages=[])
    assert request["model"] == "claude-opus-5-5" and request["fallbacks"] == "default"


def test_sdk_errors_pass_through_unless_they_contain_the_key() -> None:
    class ApiError(Exception):
        pass

    llm, _ = client([ApiError("429 RESOURCE_EXHAUSTED. quota")])
    with pytest.raises(ApiError, match="RESOURCE_EXHAUSTED"):
        complete(llm)
    leaky, _ = client([ApiError(f"GET https://example.invalid/v1beta/models?key={KEY} failed")])
    with pytest.raises(LLMError) as info:
        complete(leaky)
    error = info.value
    assert KEY not in str(error) and "withheld" in str(error)
    assert error.__cause__ is None and error.__suppress_context__  # the traceback cannot show it either


def test_the_key_is_not_in_the_backend_repr() -> None:
    backend = GeminiBackend(KEY, client=FakeGenai([]))
    assert KEY not in repr(backend) and KEY not in repr(vars(backend))


def test_blocks_compare_by_value_and_carry_their_part() -> None:
    part = FakePart(text="x")
    assert GeminiBlock("text", part, text="x") == GeminiBlock("text", part, text="x")


# ---------------------------------------------------------------------------
# Planner on the Gemini backend
# ---------------------------------------------------------------------------


def test_planner_submits_a_plan_through_the_gemini_backend() -> None:
    from test_agent_planner import Toolbox, discovery, oracle_plan, plan_input

    from zerodrop.agent.planner import ClaudePlanner
    from zerodrop.sandbox import fixtures

    dataset = fixtures.generate(5, "small")
    plan = oracle_plan(dataset)
    script = [
        reply(call_part("get_target_schema", None, "c1", signature=b"s1")),
        reply(call_part("submit_plan", plan_input(plan), "c2", signature=b"s2")),
    ]
    fake = FakeGenai(script)
    planner = ClaudePlanner(
        LLMClient(settings(), GeminiBackend(KEY, client=fake), model=MODEL), Toolbox(dataset)
    )
    assert planner.plan(discovery(dataset)) == plan
    assert planner.usage.calls == 2 and planner.usage.served_models == {MODEL: 2}
    declared = [d["name"] for d in fake.models.calls[0]["config"]["tools"][0]["function_declarations"]]
    assert declared[-1] == "submit_plan" and "dry_run" in declared
    answer = fake.models.calls[1]["contents"][2]["parts"][0]["function_response"]
    assert (answer["name"], answer["id"]) == ("get_target_schema", "c1")


# ---------------------------------------------------------------------------
# Real google-genai SDK over an offline transport (no network, placeholder key)
# ---------------------------------------------------------------------------


def sdk_backend(handler: Any) -> GeminiBackend:
    genai = pytest.importorskip("google.genai")
    import httpx

    http = httpx.Client(transport=httpx.MockTransport(handler))
    sdk = genai.Client(api_key=KEY, vertexai=False, http_options={"httpx_client": http})
    return GeminiBackend(KEY, client=sdk)


def wire_response(parts: list[dict[str, Any]], finish: str = "STOP") -> dict[str, Any]:
    return {
        "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}],
        "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 10, "thoughtsTokenCount": 30},
        "modelVersion": MODEL,
    }


def test_sdk_round_trip_sends_signatures_and_function_responses_on_the_wire() -> None:
    import httpx

    bodies: list[dict[str, Any]] = []
    urls: list[str] = []
    replies = [
        wire_response(
            [
                {
                    "functionCall": {"id": "fc-1", "name": "echo", "args": {"value": 4}},
                    "thoughtSignature": "c2lnLTE=",
                }
            ]
        ),
        wire_response([{"functionCall": {"id": "fc-2", "name": "submit_answer", "args": {"answer": 9}}}]),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == KEY
        urls.append(str(request.url))
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=replies[len(bodies) - 1])

    llm = LLMClient(settings(), sdk_backend(handler), model=MODEL)
    assert loop(llm, [echo_tool([])]) == 9
    assert all(KEY not in url and url.endswith(f"/models/{MODEL}:generateContent") for url in urls)
    first, second = bodies
    assert first["systemInstruction"]["parts"][0]["text"] == "sys"
    assert first["generationConfig"]["maxOutputTokens"] == 32_000
    # SDK 2.29.0 sends these two fields under their proto names, with typed objects as well
    assert first["generationConfig"]["thinkingConfig"] == {"thinking_level": "MEDIUM"}
    declarations = first["tools"][0]["functionDeclarations"]
    assert declarations[0] == {
        "name": "echo",
        "description": "Echo a value.",
        "parameters_json_schema": ECHO_SCHEMA,
    }
    assert "temperature" not in first["generationConfig"] and "topK" not in first["generationConfig"]
    assert first["toolConfig"] == {"functionCallingConfig": {"mode": "AUTO"}}
    assert [c["role"] for c in second["contents"]] == ["user", "model", "user"]
    (echoed,) = second["contents"][1]["parts"]
    assert echoed["functionCall"] == {"id": "fc-1", "name": "echo", "args": {"value": 4}}
    assert echoed["thoughtSignature"] in ("c2lnLTE=", "c2lnLTE")  # base64 of b"sig-1", as received
    (answer,) = second["contents"][2]["parts"]
    assert answer == {"functionResponse": {"id": "fc-1", "name": "echo", "response": {"output": "echo 4"}}}
    assert llm.usage.output_tokens == 80 and llm.usage.served_models == {MODEL: 2}


def test_sdk_malformed_function_call_and_blocked_prompt() -> None:
    import httpx

    replies = iter(
        [
            {
                "candidates": [{"finishReason": "MALFORMED_FUNCTION_CALL"}],
                "usageMetadata": {"promptTokenCount": 7},
            },
            {"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": {"promptTokenCount": 7}},
        ]
    )
    llm = LLMClient(settings(), sdk_backend(lambda _: httpx.Response(200, json=next(replies))), model=MODEL)
    response = complete(llm)  # the malformed call is retried; the retry is blocked
    assert (response.stop_reason, response.refusal_category) == ("refusal", "safety")
    assert [c.stop_reason for c in llm.history] == ["malformed", "refusal"]


def test_sdk_error_text_does_not_contain_the_key() -> None:
    import httpx

    body = {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "API key not valid."}}
    llm = LLMClient(settings(), sdk_backend(lambda _: httpx.Response(400, json=body)), model=MODEL)
    with pytest.raises(Exception, match="INVALID_ARGUMENT") as info:
        complete(llm)
    assert KEY not in str(info.value) and KEY not in repr(info.value)


def test_the_real_client_is_built_lazily_with_the_key_passed_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    genai = pytest.importorskip("google.genai")
    seen: dict[str, Any] = {}

    class Recorder:
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    monkeypatch.setattr(genai, "Client", Recorder)
    GeminiBackend(KEY)
    assert seen["api_key"] == KEY and seen["vertexai"] is False  # never left to ambient GOOGLE_* variables
    assert seen["http_options"] == {"timeout": 300_000, "retry_options": {"attempts": 3}}


def test_blank_gemini_key_is_a_missing_key_not_an_ambient_fallback() -> None:
    # docker-compose passes an empty ZERODROP_GEMINI_KEY by default; the SDK would then pick up GOOGLE_API_KEY.
    with pytest.raises(LLMConfigError, match="ZERODROP_GEMINI_KEY"):
        LLMClient(settings(zerodrop_gemini_key="  "), model=MODEL)


# ---------------------------------------------------------------------------
# Rate limits: a 429 with a retry hint is a wait, not a failure
# ---------------------------------------------------------------------------


class FakeRateLimit(Exception):
    """Shaped like google.genai.errors.ClientError for a quota 429."""

    def __init__(self, message: str) -> None:
        super().__init__(f"429 RESOURCE_EXHAUSTED. {message}")
        self.code = 429
        self.message = message


PER_MINUTE = (
    "Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, "
    "limit: 5, model: gemini-3.8-flash\nPlease retry in 9.544920111s."
)


def waiting_client(script: list[Any], waits: list[float], **kwargs: Any) -> tuple[LLMClient, FakeModels]:
    fake = FakeGenai(script)
    backend = GeminiBackend(KEY, client=fake, sleep=waits.append, **kwargs)
    return LLMClient(settings(), backend, model=MODEL), fake.models


def test_per_minute_429_waits_as_long_as_the_server_asks_then_retries() -> None:
    waits: list[float] = []
    llm, models = waiting_client(
        [FakeRateLimit(PER_MINUTE), FakeRateLimit(PER_MINUTE), text_reply("ok")], waits
    )
    response = llm.complete(system="s", tools=[], messages=[{"role": "user", "content": "hi"}])
    assert response.text == "ok" and len(models.calls) == 3
    assert len(waits) == 2 and all(9.5 <= w <= 11.0 for w in waits)
    assert llm.calls == 1  # the waits are not model calls: only the answered request counts


def test_429_without_a_hint_waits_a_default_and_gives_up_after_the_wait_budget() -> None:
    waits: list[float] = []
    llm, models = waiting_client(
        [FakeRateLimit("You exceeded your current quota.")] * 4, waits, max_rate_limit_waits=3
    )
    with pytest.raises(FakeRateLimit):
        llm.complete(system="s", tools=[], messages=[{"role": "user", "content": "hi"}])
    assert len(models.calls) == 4 and waits == [20.0, 20.0, 20.0]


def test_daily_quota_429_is_not_waited_on() -> None:
    waits: list[float] = []
    daily = "Quota exceeded for metric: generate_content_free_tier_requests, quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier. Please retry in 3600s."
    llm, models = waiting_client([FakeRateLimit(daily)], waits)
    with pytest.raises(FakeRateLimit):
        llm.complete(system="s", tools=[], messages=[{"role": "user", "content": "hi"}])
    assert waits == [] and len(models.calls) == 1


def test_other_client_errors_are_not_retried() -> None:
    waits: list[float] = []
    error = FakeRateLimit("bad request")
    error.code = 400
    llm, models = waiting_client([error], waits)
    with pytest.raises(FakeRateLimit):
        llm.complete(system="s", tools=[], messages=[{"role": "user", "content": "hi"}])
    assert waits == [] and len(models.calls) == 1
