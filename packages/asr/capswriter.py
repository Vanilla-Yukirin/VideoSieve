"""CapsWriter adapter for the upstream WebSocket protocol."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from websockets.exceptions import InvalidStatus, WebSocketException
from websockets.sync.client import connect as _connect_ws
from websockets.typing import Subprotocol

from .interfaces import ASRProvider, ASRProviderError
from .models import ASRRequest, ASRResult, ASRSegment

_AUDIO_RATE = 16_000
_AUDIO_SAMPLE_BYTES = 4
_DEFAULT_CHUNK_SECONDS = 60
_DEFAULT_SEGMENT_SECONDS = 60.0
_DEFAULT_OVERLAP_SECONDS = 4.0
_SENTENCE_ENDINGS = frozenset("。！？.!?\n")


def _normalise_websocket_url(value: str) -> str:
    raw = value.strip()
    if "://" not in raw:
        raw = f"ws://{raw}"
    parsed = urlparse(raw)
    if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
        raise ASRProviderError(
            "ASR_CONFIG_INVALID",
            f"CapsWriter WebSocket endpoint is invalid: {value}",
            hint="Use ws://host:port or wss://host:port.",
        )
    return urlunparse(parsed._replace(path=parsed.path or "/"))


def _context_with_hotwords(context: str, hotwords: tuple[str, ...]) -> str:
    pieces = [context.strip()]
    terms = [term.strip() for term in hotwords if term.strip()]
    if terms:
        pieces.append("Hotwords: " + ", ".join(terms))
    return "\n".join(piece for piece in pieces if piece)[:2000]


def _iter_float32_chunks(
    media_path: Path,
    *,
    ffmpeg_executable: str,
    chunk_seconds: int = _DEFAULT_CHUNK_SECONDS,
) -> Iterator[bytes]:
    executable = shutil.which(ffmpeg_executable)
    if executable is None:
        raise ASRProviderError(
            "ASR_FFMPEG_UNAVAILABLE",
            f"ffmpeg executable was not found: {ffmpeg_executable}",
            hint="Install ffmpeg and make it available on PATH.",
        )
    if not media_path.is_file():
        raise ASRProviderError(
            "ASR_INPUT_MISSING",
            f"ASR media input does not exist: {media_path}",
            hint="Retry ingest and verify the workspace media files.",
        )

    with tempfile.TemporaryFile() as stderr_file:
        process = subprocess.Popen(
            [
                executable,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(media_path),
                "-f",
                "f32le",
                "-acodec",
                "pcm_f32le",
                "-ac",
                "1",
                "-ar",
                str(_AUDIO_RATE),
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=stderr_file,
        )
        chunk_size = _AUDIO_RATE * _AUDIO_SAMPLE_BYTES * chunk_seconds
        try:
            if process.stdout is None:
                raise ASRProviderError("ASR_FFMPEG_FAILED", "ffmpeg stdout pipe was not created")
            while block := process.stdout.read(chunk_size):
                yield block
            return_code = process.wait()
            if return_code != 0:
                stderr_file.seek(0)
                stderr = stderr_file.read().decode("utf-8", errors="replace").strip()
                raise ASRProviderError(
                    "ASR_FFMPEG_FAILED",
                    f"ffmpeg could not decode ASR input: {stderr or f'exit {return_code}'}",
                    hint="Verify that ffmpeg can decode the uploaded media.",
                )
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def _segments_from_tokens(
    payload: Mapping[str, Any],
    *,
    language: str,
) -> list[ASRSegment]:
    raw_tokens = payload.get("tokens")
    raw_timestamps = payload.get("timestamps")
    tokens = [str(item) for item in raw_tokens] if isinstance(raw_tokens, list) else []
    timestamps: list[float] = []
    if isinstance(raw_timestamps, list):
        for item in raw_timestamps:
            if isinstance(item, bool) or not isinstance(item, int | float):
                timestamps = []
                break
            timestamps.append(max(0.0, float(item)))
    duration_raw = payload.get("duration") or payload.get("duration_seconds") or 0.0
    duration = float(duration_raw) if isinstance(duration_raw, int | float) else 0.0

    if tokens and len(tokens) == len(timestamps):
        segments: list[ASRSegment] = []
        group_tokens: list[str] = []
        group_start = timestamps[0]
        for index, token in enumerate(tokens):
            group_tokens.append(token)
            boundary = any(char in _SENTENCE_ENDINGS for char in token) or len(group_tokens) >= 80
            if not boundary and index != len(tokens) - 1:
                continue
            next_index = index + 1
            group_end = timestamps[next_index] if next_index < len(timestamps) else duration
            if group_end <= group_start:
                group_end = max(group_start, timestamps[index])
            text = "".join(group_tokens).strip()
            if text:
                segments.append(
                    ASRSegment(
                        segment_id=f"seg_{len(segments) + 1:06d}",
                        start=group_start,
                        end=group_end,
                        text=text,
                        lang=language,
                    )
                )
            group_tokens = []
            if next_index < len(timestamps):
                group_start = timestamps[next_index]
        if segments:
            return segments

    text = str(payload.get("text_accu") or payload.get("text") or "").strip()
    if not text:
        raise ASRProviderError(
            "ASR_RESPONSE_EMPTY",
            "CapsWriter returned no transcript text",
            hint="Inspect the CapsWriter server logs and audio input.",
        )
    return [
        ASRSegment(
            segment_id="seg_000001",
            start=0.0,
            end=max(0.0, duration),
            text=text,
            lang=language,
        )
    ]


def _result_from_payload(
    payload: Mapping[str, Any],
    *,
    language: str,
    transport: str,
) -> ASRResult:
    segments = _segments_from_tokens(payload, language=language)
    return ASRResult(
        segments=segments,
        metadata={
            "adapter_name": "capswriter",
            "transport": transport,
            "provider_kind": "external_service",
            "confidence_available": False,
            "request_id": str(payload.get("id") or payload.get("task_id") or ""),
        },
    )


class CapsWriterWebSocketProvider(ASRProvider):
    """Adapter for the upstream CapsWriter root WebSocket protocol."""

    def __init__(
        self,
        *,
        endpoint: str,
        token: str | None = None,
        language: str = "auto",
        context: str = "",
        timeout_seconds: int = 900,
        ffmpeg_executable: str = "ffmpeg",
        segment_seconds: float = _DEFAULT_SEGMENT_SECONDS,
        overlap_seconds: float = _DEFAULT_OVERLAP_SECONDS,
    ) -> None:
        self._endpoint = _normalise_websocket_url(endpoint)
        self._token = token.strip() if token and token.strip() else None
        self._language = language.strip() or "auto"
        self._context = context
        self._timeout_seconds = max(1, timeout_seconds)
        self._ffmpeg_executable = ffmpeg_executable
        self._segment_seconds = max(1.0, segment_seconds)
        self._overlap_seconds = max(0.0, min(overlap_seconds, self._segment_seconds))

    @property
    def adapter_name(self) -> str:
        return "capswriter"

    def test_connection(self) -> None:
        """Verify the official WebSocket handshake without submitting audio."""

        headers = {"Authorization": f"Bearer {self._token}"} if self._token else None
        try:
            with _connect_ws(
                self._endpoint,
                subprotocols=[Subprotocol("binary")],
                additional_headers=headers,
                proxy=None,
                open_timeout=min(30, self._timeout_seconds),
                max_size=None,
                max_queue=None,
            ):
                return
        except TimeoutError as exc:
            raise ASRProviderError(
                "ASR_PROVIDER_TIMEOUT",
                "CapsWriter WebSocket handshake timed out",
                retryable=True,
            ) from exc
        except InvalidStatus as exc:
            status = exc.response.status_code
            if status in {401, 403}:
                raise ASRProviderError(
                    "ASR_PROVIDER_AUTH_FAILED",
                    f"CapsWriter WebSocket handshake returned HTTP {status}",
                    hint=(
                        "Configure the optional Bearer token when this CapsWriter "
                        "deployment enables authentication."
                    ),
                    retryable=False,
                ) from exc
            raise ASRProviderError(
                "ASR_PROVIDER_REQUEST_FAILED",
                f"CapsWriter WebSocket handshake returned HTTP {status}",
                retryable=status >= 500,
            ) from exc
        except (OSError, ValueError, WebSocketException) as exc:
            raise ASRProviderError(
                "ASR_PROVIDER_REQUEST_FAILED",
                f"CapsWriter WebSocket handshake failed: {exc}",
                retryable=True,
            ) from exc

    def transcribe(self, request: ASRRequest) -> ASRResult:
        task_id = str(uuid.uuid4())
        language = request.language_hint or self._language
        context = _context_with_hotwords(self._context, request.hotwords)
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else None
        deadline = time.monotonic() + self._timeout_seconds
        try:
            with _connect_ws(
                self._endpoint,
                subprotocols=[Subprotocol("binary")],
                additional_headers=headers,
                proxy=None,
                open_timeout=min(30, self._timeout_seconds),
                max_size=None,
                max_queue=None,
            ) as socket:
                for chunk in _iter_float32_chunks(
                    request.audio_path,
                    ffmpeg_executable=self._ffmpeg_executable,
                ):
                    socket.send(
                        json.dumps(
                            {
                                "task_id": task_id,
                                "source": "file",
                                "data": base64.b64encode(chunk).decode("ascii"),
                                "is_final": False,
                                "time_start": time.time(),
                                "seg_duration": self._segment_seconds,
                                "seg_overlap": self._overlap_seconds,
                                "context": context,
                                "language": language,
                            },
                            ensure_ascii=False,
                        )
                    )
                socket.send(
                    json.dumps(
                        {
                            "task_id": task_id,
                            "source": "file",
                            "data": "",
                            "is_final": True,
                            "time_start": time.time(),
                            "seg_duration": self._segment_seconds,
                            "seg_overlap": self._overlap_seconds,
                            "context": context,
                            "language": language,
                        },
                        ensure_ascii=False,
                    )
                )
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("CapsWriter recognition timed out")
                    raw = socket.recv(timeout=remaining)
                    decoded = json.loads(str(raw))
                    if not isinstance(decoded, dict) or decoded.get("task_id") != task_id:
                        continue
                    if decoded.get("is_final") is True:
                        return _result_from_payload(
                            decoded,
                            language=language,
                            transport="websocket",
                        )
        except ASRProviderError:
            raise
        except TimeoutError as exc:
            raise ASRProviderError(
                "ASR_PROVIDER_TIMEOUT",
                f"CapsWriter WebSocket request timed out after {self._timeout_seconds}s",
                retryable=True,
            ) from exc
        except (OSError, ValueError, WebSocketException, json.JSONDecodeError) as exc:
            raise ASRProviderError(
                "ASR_PROVIDER_REQUEST_FAILED",
                f"CapsWriter WebSocket request failed: {exc}",
                retryable=True,
            ) from exc
