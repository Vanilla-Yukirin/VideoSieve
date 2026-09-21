from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from asr import (
    ASRProviderError,
    ASRRequest,
    CapsWriterWebSocketProvider,
)
from asr.capswriter import _iter_float32_chunks


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
    assert all(segment.conf is None for segment in result.segments)
    assert all("conf" not in segment.to_contract_dict() for segment in result.segments)


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


def test_websocket_connection_test_reports_optional_token_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject(*_args: object, **_kwargs: object) -> None:
        raise InvalidStatus(Response(401, "Unauthorized", Headers()))

    monkeypatch.setattr("asr.capswriter._connect_ws", reject)

    with pytest.raises(ASRProviderError) as exc_info:
        CapsWriterWebSocketProvider(endpoint="ws://localhost:6016").test_connection()

    assert exc_info.value.code == "ASR_PROVIDER_AUTH_FAILED"
    assert "optional Bearer token" in exc_info.value.hint
    assert exc_info.value.retryable is False


def test_websocket_provider_rejects_http_endpoint() -> None:
    with pytest.raises(ASRProviderError) as exc_info:
        CapsWriterWebSocketProvider(endpoint="http://localhost:6016")

    assert exc_info.value.code == "ASR_CONFIG_INVALID"


def test_ffmpeg_errors_are_buffered_without_a_stderr_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media_path = tmp_path / "broken.mp4"
    media_path.write_bytes(b"broken")

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = BytesIO(b"")

        def wait(self, timeout: float | None = None) -> int:
            assert timeout is None
            return 1

        def poll(self) -> int:
            return 1

    def fake_popen(*_args: object, **kwargs: Any) -> FakeProcess:
        stderr = kwargs["stderr"]
        assert stderr is not None
        assert stderr != -1  # subprocess.PIPE
        stderr.write(b"decode failed")
        stderr.flush()
        return FakeProcess()

    monkeypatch.setattr("asr.capswriter.shutil.which", lambda _name: "ffmpeg")
    monkeypatch.setattr("asr.capswriter.subprocess.Popen", fake_popen)

    with pytest.raises(ASRProviderError, match="decode failed"):
        list(_iter_float32_chunks(media_path, ffmpeg_executable="ffmpeg"))
