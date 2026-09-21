from __future__ import annotations

import json
from typing import Any
from urllib.request import Request

import pytest

from model_api import request_model_text, resolve_model_endpoint


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


@pytest.mark.parametrize(
    ("protocol", "expected"),
    [
        ("openai_chat_completions", "https://api.example/v1/chat/completions"),
        ("openai_responses", "https://api.example/v1/responses"),
        ("anthropic_messages", "https://api.example/v1/messages"),
    ],
)
def test_resolve_model_endpoint_appends_protocol_route(
    protocol: str, expected: str
) -> None:
    assert resolve_model_endpoint("https://api.example/v1/", protocol) == expected


@pytest.mark.parametrize(
    ("protocol", "response", "expected_path"),
    [
        (
            "openai_chat_completions",
            {"choices": [{"message": {"content": "chat ok"}}]},
            "/v1/chat/completions",
        ),
        (
            "openai_responses",
            {
                "output": [
                    {"type": "reasoning"},
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "responses ok"}],
                    },
                ]
            },
            "/v1/responses",
        ),
        (
            "anthropic_messages",
            {"content": [{"type": "text", "text": "anthropic ok"}]},
            "/v1/messages",
        ),
    ],
)
def test_request_model_text_uses_protocol_specific_wire_format(
    monkeypatch: pytest.MonkeyPatch,
    protocol: str,
    response: dict[str, Any],
    expected_path: str,
) -> None:
    captured: list[Request] = []

    def _open(request: Request, timeout: float) -> _Response:
        del timeout
        captured.append(request)
        return _Response(response)

    monkeypatch.setattr("urllib.request.urlopen", _open)
    result = request_model_text(
        protocol=protocol,
        api_root="https://api.example/v1",
        model="model-id",
        api_key="secret",
        system_prompt="system",
        user_text="hello",
        image_data_url=(
            "data:image/png;base64,aGVsbG8=" if protocol != "anthropic_messages" else None
        ),
    )

    assert result.endswith("ok")
    assert captured[0].full_url.endswith(expected_path)
    body = json.loads(bytes(captured[0].data or b"").decode())
    if protocol == "openai_responses":
        assert body["input"][0]["content"][0]["type"] == "input_text"
    elif protocol == "anthropic_messages":
        assert body["system"] == "system"
        assert captured[0].headers["X-api-key"] == "secret"
    else:
        assert body["messages"][1]["content"][1]["type"] == "image_url"
