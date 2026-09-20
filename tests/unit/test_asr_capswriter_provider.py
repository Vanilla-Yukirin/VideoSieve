from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from asr import (
    ASRProviderError,
    ASRRequest,
    CapsWriterHTTPProvider,
    CapsWriterWebSocketProvider,
)


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def __enter__(self) -> _FakeWebSocket:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def recv(self, *, timeout: float) -> str:
        assert timeout > 0
        task_id = self.sent[-1]["task_id"]
        return json.dumps(
            {
                "task_id": task_id,
                "is_final": True,
                "duration": 2.5,
                "text": "你好。世界！",
                "text_accu": "你好。世界！",
                "tokens": ["你", "好", "。", "世", "界", "！"],
                "timestamps": [0.0, 0.3, 0.6, 1.0, 1.4, 2.0],
            },
            ensure_ascii=False,
        )


def test_websocket_provider_uses_upstream_protocol_without_required_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket = _FakeWebSocket()
    connect_kwargs: dict[str, Any] = {}

    def fake_connect(endpoint: str, **kwargs: Any) -> _FakeWebSocket:
        assert endpoint == "ws://capswriter.example:6016/"
        connect_kwargs.update(kwargs)
        return socket

    monkeypatch.setattr("asr.capswriter._connect_ws", fake_connect)
    monkeypatch.setattr(
        "asr.capswriter._iter_float32_chunks",
        lambda *_args, **_kwargs: iter([b"first", b"second"]),
    )
    provider = CapsWriterWebSocketProvider(
        endpoint="capswriter.example:6016",
        context="课程",
    )

    result = provider.transcribe(
        ASRRequest(audio_path=Path("input.mp4"), hotwords=("VideoSieve",))
    )

    assert connect_kwargs["subprotocols"] == ["binary"]
    assert connect_kwargs["additional_headers"] is None
    assert [message["is_final"] for message in socket.sent] == [False, False, True]
    assert socket.sent[0]["source"] == "file"
    assert socket.sent[0]["seg_duration"] == 60.0
    assert socket.sent[0]["seg_overlap"] == 4.0
    assert socket.sent[0]["context"] == "课程\nHotwords: VideoSieve"
    assert socket.sent[-1]["data"] == ""
    assert [segment.text for segment in result.segments] == ["你好。", "世界！"]
    assert result.metadata["transport"] == "websocket"
    assert result.metadata["confidence_available"] is False


def test_websocket_provider_sends_optional_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    socket = _FakeWebSocket()
    connect_kwargs: dict[str, Any] = {}

    def fake_connect(_endpoint: str, **kwargs: Any) -> _FakeWebSocket:
        connect_kwargs.update(kwargs)
        return socket

    monkeypatch.setattr("asr.capswriter._connect_ws", fake_connect)
    monkeypatch.setattr(
        "asr.capswriter._iter_float32_chunks",
        lambda *_args, **_kwargs: iter([b"audio"]),
    )

    CapsWriterWebSocketProvider(endpoint="ws://localhost:6016", token="secret").transcribe(
        ASRRequest(audio_path=Path("input.wav"))
    )

    assert connect_kwargs["additional_headers"] == {"Authorization": "Bearer secret"}


class _FakeHTTPResponse:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._body = json.dumps(payload, ensure_ascii=False).encode()

    def read(self) -> bytes:
        return self._body


class _FakeHTTPConnection:
    response = _FakeHTTPResponse(
        200,
        {
            "id": "req-1",
            "text": "第一句\n第二句",
            "duration_seconds": 3.0,
            "srt": (
                "1\n00:00:00,000 --> 00:00:01,200\n第一句\n\n"
                "2\n00:00:01,200 --> 00:00:03,000\n第二句\n"
            ),
        },
    )
    instances: list[_FakeHTTPConnection] = []

    def __init__(self, netloc: str, *, timeout: int) -> None:
        self.netloc = netloc
        self.timeout = timeout
        self.headers: dict[str, str] = {}
        self.sent = bytearray()
        self.request_path = ""
        self.__class__.instances.append(self)

    def putrequest(self, method: str, path: str) -> None:
        assert method == "POST"
        self.request_path = path

    def putheader(self, name: str, value: str) -> None:
        self.headers[name] = value

    def endheaders(self) -> None:
        return None

    def send(self, block: bytes) -> None:
        self.sent.extend(block)

    def getresponse(self) -> _FakeHTTPResponse:
        return self.response

    def close(self) -> None:
        return None


def test_http_extension_streams_raw_body_and_allows_missing_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _FakeHTTPConnection.instances.clear()
    monkeypatch.setattr("asr.capswriter.http.client.HTTPConnection", _FakeHTTPConnection)
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"wave-data")

    result = CapsWriterHTTPProvider(endpoint="http://capswriter:6018").transcribe(
        ASRRequest(audio_path=audio, language_hint="zh")
    )

    connection = _FakeHTTPConnection.instances[-1]
    assert connection.netloc == "capswriter:6018"
    assert connection.sent == b"wave-data"
    assert connection.headers["Content-Type"] == "audio/wav"
    assert "Authorization" not in connection.headers
    assert connection.request_path.startswith("/v1/transcriptions?")
    assert [segment.text for segment in result.segments] == ["第一句", "第二句"]
    assert result.metadata["transport"] == "http"


def test_http_extension_preserves_retryable_server_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FailingConnection(_FakeHTTPConnection):
        response = _FakeHTTPResponse(503, {"detail": "busy"})

    monkeypatch.setattr("asr.capswriter.http.client.HTTPConnection", FailingConnection)
    audio = tmp_path / "audio.bin"
    audio.write_bytes(b"audio")

    with pytest.raises(ASRProviderError) as exc_info:
        CapsWriterHTTPProvider(endpoint="http://capswriter:6018", token="optional").transcribe(
            ASRRequest(audio_path=audio)
        )

    assert exc_info.value.code == "ASR_PROVIDER_HTTP_ERROR"
    assert exc_info.value.retryable is True
