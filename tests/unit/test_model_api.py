from __future__ import annotations

import json
from typing import Any

import httpx2
import pytest

from model_api import ModelApiError, ModelRequestOptions, request_model, resolve_model_endpoint
from model_api.telemetry import ModelCallJournal, read_usage_summary


@pytest.mark.parametrize(
    ("protocol", "route"),
    [
        ("openai_chat_completions", "chat/completions"),
        ("openai_responses", "responses"),
        ("anthropic_messages", "messages"),
    ],
)
def test_endpoint_legacy_full_route_and_api_root(protocol: str, route: str) -> None:
    endpoint = f"https://api.example/v1/{route}"
    assert resolve_model_endpoint("https://api.example/v1/", protocol) == endpoint
    assert resolve_model_endpoint(endpoint, protocol) == endpoint


def _payload(
    protocol: str, reason: str, text: str = "complete", usage: Any = None
) -> dict[str, Any]:
    if protocol == "openai_chat_completions":
        result = {"choices": [{"finish_reason": reason, "message": {"content": text}}]}
    elif protocol == "openai_responses":
        result = {
            "status": "incomplete" if reason == "max_output_tokens" else reason,
            "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        }
        if reason == "max_output_tokens":
            result["incomplete_details"] = {"reason": reason}
    else:
        result = {"stop_reason": reason, "content": [{"type": "text", "text": text}]}
    if usage is not None:
        result["usage"] = usage
    return result


def _sdk_transport(
    monkeypatch: pytest.MonkeyPatch, responses: list[Any], captured: list[Any]
) -> None:
    from model_api import client

    original_openai = client.openai.OpenAI
    original_anthropic = client.anthropic.Anthropic

    def handle(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        response = responses.pop(0)
        if isinstance(response, tuple):
            status, body = response
            return httpx2.Response(status, text=body, headers={"Content-Type": "application/json"})
        return httpx2.Response(200, json=response, headers={"x-request-id": "test-request"})

    def openai_factory(**kwargs: Any) -> Any:
        return original_openai(
            **kwargs, http_client=httpx2.Client(transport=httpx2.MockTransport(handle))
        )

    def anthropic_factory(**kwargs: Any) -> Any:
        return original_anthropic(
            **kwargs, http_client=httpx2.Client(transport=httpx2.MockTransport(handle))
        )

    monkeypatch.setattr(client.openai, "OpenAI", openai_factory)
    monkeypatch.setattr(client.anthropic, "Anthropic", anthropic_factory)


def _request(protocol: str = "openai_chat_completions", **kwargs: Any) -> Any:
    return request_model(
        protocol=protocol,
        api_root="https://api.example/v1",
        model="test-model",
        api_key="synthetic-secret",
        system_prompt="system",
        user_text="evidence",
        **kwargs,
    )


@pytest.mark.parametrize(
    ("protocol", "reason", "cap_field"),
    [
        ("openai_chat_completions", "stop", "max_completion_tokens"),
        ("openai_responses", "completed", "max_output_tokens"),
        ("anthropic_messages", "end_turn", "max_tokens"),
    ],
)
def test_sdk_wire_budget_thinking_and_usage(
    monkeypatch: pytest.MonkeyPatch, protocol: str, reason: str, cap_field: str
) -> None:
    captured: list[Any] = []
    usage = {"input_tokens": 123, "output_tokens": 44, "cache_read_input_tokens": 7}
    _sdk_transport(monkeypatch, [_payload(protocol, reason, usage=usage)], captured)
    result = _request(
        protocol,
        options={"max_output_tokens": 32000, "max_retries": 0},
        image_data_url="data:image/png;base64,aGVsbG8=",
    )
    assert result.text == "complete"
    assert result.attempts[0].usage == usage
    assert result.attempts[0].request_id == "test-request"
    assert result.attempts[0].finish_reason == reason
    body = json.loads(captured[0].content)
    assert body[cap_field] == 32000
    assert "context_window_tokens" not in body
    assert "temperature" not in body
    if protocol == "anthropic_messages":
        assert body["thinking"] == {"type": "enabled", "budget_tokens": 8192}
        assert captured[0].headers["x-api-key"] == "synthetic-secret"
    elif protocol == "openai_responses":
        assert body["reasoning"]["effort"] == "medium"
    else:
        assert body["reasoning_effort"] == "medium"


@pytest.mark.parametrize("protocol", ["openai_chat_completions", "openai_responses"])
@pytest.mark.parametrize("adapter", ["openai", "openai_legacy"])
def test_openai_disabled_thinking_is_explicit_or_declared_legacy(
    monkeypatch: pytest.MonkeyPatch, protocol: str, adapter: str
) -> None:
    captured: list[Any] = []
    reason = "stop" if protocol == "openai_chat_completions" else "completed"
    _sdk_transport(monkeypatch, [_payload(protocol, reason)], captured)
    _request(
        protocol,
        options={"thinking_enabled": False, "thinking_adapter": adapter, "max_retries": 0},
    )
    body = json.loads(captured[0].content)
    if adapter == "openai_legacy":
        assert "reasoning" not in body and "reasoning_effort" not in body
    elif protocol == "openai_responses":
        assert body["reasoning"] == {"effort": "none"}
    else:
        assert body["reasoning_effort"] == "none"
    cap = (
        "max_output_tokens"
        if protocol == "openai_responses"
        else "max_tokens"
        if adapter == "openai_legacy"
        else "max_completion_tokens"
    )
    assert body[cap] == 32768


def test_unsupported_disabled_thinking_does_not_silently_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[Any] = []
    _sdk_transport(monkeypatch, [(400, '{"error":{"message":"none is unsupported"}}')], captured)
    with pytest.raises(ModelApiError) as error:
        _request(options={"thinking_enabled": False, "thinking_adapter": "openai"})
    assert error.value.code == "MODEL_PROVIDER_HTTP_ERROR"
    assert not error.value.retryable
    assert len(captured) == 1
    assert json.loads(captured[0].content)["reasoning_effort"] == "none"


def test_legacy_adapter_rejects_enabled_thinking() -> None:
    with pytest.raises(ValueError, match="legacy models"):
        ModelRequestOptions(thinking_adapter="openai_legacy", thinking_enabled=True)


@pytest.mark.parametrize(
    ("protocol", "reason"),
    [
        ("openai_chat_completions", "length"),
        ("openai_responses", "max_output_tokens"),
        ("anthropic_messages", "max_tokens"),
    ],
)
def test_truncation_never_succeeds_even_with_valid_json_text(
    monkeypatch: pytest.MonkeyPatch, protocol: str, reason: str
) -> None:
    _sdk_transport(
        monkeypatch, [_payload(protocol, reason, text='{"summary":"only first part"}')], []
    )
    with pytest.raises(ModelApiError) as error:
        _request(protocol, options={"max_retries": 0})
    assert error.value.code == "MODEL_OUTPUT_TRUNCATED"
    assert len(error.value.attempts) == 1


def test_retry_retains_failed_usage_and_success_without_joining_partial_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    responses = [
        _payload(
            "openai_chat_completions",
            "length",
            "PARTIAL",
            {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        ),
        _payload(
            "openai_chat_completions",
            "stop",
            "FINAL",
            {"prompt_tokens": 14, "completion_tokens": 7, "total_tokens": 21},
        ),
    ]
    captured: list[Any] = []
    _sdk_transport(monkeypatch, responses, captured)
    journal = ModelCallJournal(tmp_path)
    result = _request(
        options={"max_retries": 1}, on_attempt=lambda row: journal.record("deliverables", row)
    )
    assert result.text == "FINAL"
    assert len(result.attempts) == 2
    assert (
        json.loads(captured[0].content)["messages"][1]
        == json.loads(captured[1].content)["messages"][1]
    )
    assert result.attempts[0].error_code == "MODEL_OUTPUT_TRUNCATED"
    summary = read_usage_summary(tmp_path)
    assert summary["calls"] == 2 and summary["failed_calls"] == 1
    assert summary["stages"]["deliverables"]["input_tokens"] == 26
    assert summary["stages"]["deliverables"]["total_tokens"] == 41
    assert "synthetic-secret" not in (tmp_path / "meta/model_calls.jsonl").read_text()


@pytest.mark.parametrize("reason", [None, "tool_calls", "content_filter", "unknown"])
def test_missing_or_non_text_completion_is_not_success(
    monkeypatch: pytest.MonkeyPatch, reason: Any
) -> None:
    _sdk_transport(monkeypatch, [_payload("openai_chat_completions", reason)], [])
    with pytest.raises(ModelApiError) as error:
        _request(options={"max_retries": 0})
    assert error.value.code == "MODEL_COMPLETION_INVALID"


@pytest.mark.parametrize(
    ("adapter", "expected"),
    [
        ("deepseek", {"thinking": {"type": "enabled"}, "reasoning_effort": "medium"}),
        ("dashscope", {"enable_thinking": True}),
    ],
)
def test_third_party_thinking_parameters(
    monkeypatch: pytest.MonkeyPatch, adapter: str, expected: Any
) -> None:
    captured: list[Any] = []
    _sdk_transport(monkeypatch, [_payload("openai_chat_completions", "stop")], captured)
    _request(options={"thinking_adapter": adapter, "max_retries": 0})
    body = json.loads(captured[0].content)
    assert body["max_tokens"] == 32768
    for key, value in expected.items():
        assert body[key] == value


def test_anthropic_bearer_and_adaptive(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[Any] = []
    _sdk_transport(monkeypatch, [_payload("anthropic_messages", "end_turn")], captured)
    _request(
        "anthropic_messages", auth_mode="bearer", options={"thinking_adapter": "anthropic_adaptive"}
    )
    assert captured[0].headers["authorization"] == "Bearer synthetic-secret"
    assert not captured[0].headers.get("x-api-key")
    assert json.loads(captured[0].content)["thinking"] == {"type": "adaptive"}
    assert json.loads(captured[0].content)["output_config"] == {"effort": "medium"}


@pytest.mark.parametrize("output", [None, {}, "invalid"])
def test_responses_malformed_optional_output_is_not_an_unhandled_error(
    monkeypatch: pytest.MonkeyPatch, output: Any
) -> None:
    _sdk_transport(
        monkeypatch,
        [{"status": "completed", "output_text": "complete", "output": output}],
        [],
    )
    assert _request("openai_responses", options={"max_retries": 0}).text == "complete"


@pytest.mark.parametrize("protocol", ["openai_chat_completions", "openai_responses"])
@pytest.mark.parametrize("text", ["complete", ""])
def test_refusal_metadata_rejects_even_nonempty_completed_text(
    monkeypatch: pytest.MonkeyPatch, protocol: str, text: str
) -> None:
    payload = _payload(
        protocol, "stop" if protocol == "openai_chat_completions" else "completed", text=text
    )
    if protocol == "openai_chat_completions":
        payload["choices"][0]["message"]["refusal"] = "refused"
    else:
        payload["output"][0]["content"].append({"type": "refusal", "refusal": "refused"})
    captured: list[Any] = []
    _sdk_transport(monkeypatch, [payload], captured)
    with pytest.raises(ModelApiError) as error:
        _request(protocol)
    assert error.value.code == "MODEL_COMPLETION_INVALID"
    assert not error.value.retryable
    assert len(captured) == 1


@pytest.mark.parametrize(
    ("status", "retryable"), [(401, False), (400, False), (503, True), (429, True)]
)
def test_sdk_errors_are_sanitized_and_not_retried_when_disabled(
    monkeypatch: pytest.MonkeyPatch, status: int, retryable: bool
) -> None:
    captured: list[Any] = []
    _sdk_transport(
        monkeypatch, [(status, '{"error":{"message":"secret response text"}}')], captured
    )
    with pytest.raises(ModelApiError) as error:
        _request(options={"max_retries": 0})
    assert error.value.code == "MODEL_PROVIDER_HTTP_ERROR"
    assert error.value.retryable is retryable
    assert "secret response" not in str(error.value)
    assert len(captured) == 1


def test_unknown_usage_stays_unknown(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    _sdk_transport(monkeypatch, [_payload("openai_chat_completions", "stop")], [])
    journal = ModelCallJournal(tmp_path)
    _request(on_attempt=lambda row: journal.record("frame_summary", row))
    usage = read_usage_summary(tmp_path)["stages"]["frame_summary"]
    assert usage["input_tokens"] is None
    assert usage["usage_missing_calls"] == 1


def test_option_defaults_and_strict_validation() -> None:
    assert ModelRequestOptions().context_window_tokens == 131072
    assert ModelRequestOptions().max_output_tokens == 32768
    for invalid in [
        {"max_retries": -1},
        {"max_output_tokens": True},
        {"context_window_tokens": 32768},
    ]:
        with pytest.raises(ValueError):
            ModelRequestOptions.model_validate(invalid)


def test_exhausted_truncation_retains_every_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[Any] = []
    _sdk_transport(
        monkeypatch,
        [
            _payload("openai_chat_completions", "length"),
            _payload("openai_chat_completions", "length"),
        ],
        captured,
    )
    with pytest.raises(ModelApiError) as error:
        _request(options={"max_retries": 1})
    assert error.value.code == "MODEL_OUTPUT_TRUNCATED"
    assert len(error.value.attempts) == len(captured) == 2


def test_invalid_json_from_sdk_transport_fails_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    _sdk_transport(monkeypatch, [(200, "not-json")], [])
    with pytest.raises(ModelApiError) as error:
        _request(options={"max_retries": 0})
    assert error.value.code == "MODEL_INVALID_RESPONSE"


def test_reasoning_only_truncation_is_detected_before_empty_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sdk_transport(monkeypatch, [_payload("openai_chat_completions", "length", text="")], [])
    with pytest.raises(ModelApiError) as error:
        _request(options={"max_retries": 0})
    assert error.value.code == "MODEL_OUTPUT_TRUNCATED"


def test_journal_recovers_after_partial_crash_tail(tmp_path: Any) -> None:
    from model_api import ModelCallAttempt

    path = tmp_path / "meta/model_calls.jsonl"
    path.parent.mkdir()
    path.write_text('{"partial":', encoding="utf-8")
    journal = ModelCallJournal(tmp_path)
    journal.record(
        "deliverables",
        ModelCallAttempt(
            call_id="good",
            attempt=1,
            protocol="openai_chat_completions",
            model="model",
            elapsed_ms=10,
            finish_reason="stop",
            usage={"prompt_tokens": 5},
            request_id=None,
        ),
    )
    assert read_usage_summary(tmp_path)["calls"] == 1
    assert read_usage_summary(tmp_path)["stages"]["deliverables"]["input_tokens"] == 5


def test_control_check_prevents_additional_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[Any] = []
    _sdk_transport(monkeypatch, [_payload("openai_chat_completions", "length")], captured)
    checks = 0

    def check() -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            raise RuntimeError("cancel requested")

    with pytest.raises(RuntimeError, match="cancel requested"):
        _request(check_control=check)
    assert len(captured) == 1


def test_request_gate_rechecks_control_before_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[Any] = []
    _sdk_transport(monkeypatch, [], captured)
    cancelled = False

    def gate() -> None:
        nonlocal cancelled
        cancelled = True

    def check() -> None:
        if cancelled:
            raise RuntimeError("cancel requested during rate limit wait")

    with pytest.raises(RuntimeError, match="during rate limit wait"):
        _request(before_request=gate, check_control=check)
    assert captured == []
