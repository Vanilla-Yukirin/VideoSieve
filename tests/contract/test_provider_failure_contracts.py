from __future__ import annotations

import io
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from frame_summary import (
    FrameSummaryProviderError,
    FrameSummaryResult,
    FrameSummaryService,
    QwenFrameSummaryProvider,
)
from infra import FileSystemWorkspaceStore
from keyframes import KeyframeBaselineService


class _Response:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _image(tmp_path: Path) -> Path:
    path = tmp_path / "frame.jpg"
    path.write_bytes(b"not-a-real-image-but-provider-only-needs-bytes")
    return path


def test_frame_summary_missing_api_key_is_an_explicit_failure(tmp_path: Path) -> None:
    provider = QwenFrameSummaryProvider(api_key="")

    with pytest.raises(FrameSummaryProviderError, match="QWEN_API_KEY") as exc_info:
        provider.summarize_frame("frame-1", _image(tmp_path), language_hint="zh")
    assert exc_info.value.code == "FRAME_SUMMARY_CONFIG_MISSING"
    assert exc_info.value.retryable is False


@pytest.mark.parametrize(
    ("provider_error", "expected_code", "expected_retryable"),
    [
        (
            urllib.error.URLError("connection refused"),
            "FRAME_SUMMARY_PROVIDER_UNAVAILABLE",
            True,
        ),
        (
            TimeoutError("provider timed out"),
            "FRAME_SUMMARY_PROVIDER_UNAVAILABLE",
            True,
        ),
        (
            urllib.error.HTTPError(
                url="https://provider.invalid/v1/chat/completions",
                code=503,
                msg="unavailable",
                hdrs=Message(),
                fp=io.BytesIO(b"unavailable"),
            ),
            "FRAME_SUMMARY_PROVIDER_HTTP_ERROR",
            True,
        ),
    ],
)
def test_frame_summary_transport_failure_is_not_a_successful_placeholder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_error: BaseException,
    expected_code: str,
    expected_retryable: bool,
) -> None:
    def _raise(*args: object, **kwargs: object) -> _Response:
        del args, kwargs
        raise provider_error

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    provider = QwenFrameSummaryProvider(api_key="real-looking-test-key")

    with pytest.raises(FrameSummaryProviderError) as exc_info:
        provider.summarize_frame("frame-1", _image(tmp_path), language_hint="zh")
    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is expected_retryable


@pytest.mark.parametrize(
    ("body", "expected_code"),
    [
        ("not-json", "FRAME_SUMMARY_INVALID_RESPONSE"),
        ("{}", "FRAME_SUMMARY_EMPTY_RESPONSE"),
        ('{"choices": []}', "FRAME_SUMMARY_EMPTY_RESPONSE"),
        (
            '{"choices": [{"message": {"content": "   "}}]}',
            "FRAME_SUMMARY_EMPTY_RESPONSE",
        ),
    ],
)
def test_frame_summary_empty_or_malformed_response_is_an_explicit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    expected_code: str,
) -> None:
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _Response(body))
    provider = QwenFrameSummaryProvider(api_key="real-looking-test-key")

    with pytest.raises(FrameSummaryProviderError) as exc_info:
        provider.summarize_frame("frame-1", _image(tmp_path), language_hint="zh")
    assert exc_info.value.code == expected_code
    assert exc_info.value.retryable is True


def test_frame_summary_batch_failure_does_not_publish_partial_artifact(tmp_path: Path) -> None:
    class _FailSecondProvider:
        def __init__(self) -> None:
            self.calls = 0

        def summarize_frame(
            self,
            frame_id: str,
            image_path: Path,
            *,
            language_hint: str | None = None,
        ) -> FrameSummaryResult:
            del image_path, language_hint
            self.calls += 1
            if self.calls == 2:
                raise FrameSummaryProviderError(
                    "FRAME_SUMMARY_PROVIDER_UNAVAILABLE",
                    "deliberate second-frame failure",
                    retryable=True,
                )
            return FrameSummaryResult(
                frame_id=frame_id,
                lang="zh",
                provider="test_provider",
                description_text="real-looking test response",
            )

    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    KeyframeBaselineService(store).run(
        "project-1",
        "job-1",
        duration_seconds=6.0,
        interval_seconds=5.0,
        reason="sample",
    )
    artifact = store.frame_summary_file("project-1", "job-1")
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"previous":"stale artifact"}\n', encoding="utf-8")

    with pytest.raises(FrameSummaryProviderError):
        FrameSummaryService(store, _FailSecondProvider()).run(
            "project-1",
            "job-1",
            language_hint="zh",
            concurrency=1,
            rpm=0,
        )

    assert not artifact.exists()
    assert not artifact.with_suffix(f"{artifact.suffix}.tmp").exists()
