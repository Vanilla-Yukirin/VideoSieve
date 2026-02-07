from __future__ import annotations

from pathlib import Path

from asr import ASRRequest, BaselineASRProvider


def test_baseline_provider_passthrough_hotwords_and_language_hint() -> None:
    provider = BaselineASRProvider()
    request = ASRRequest(
        audio_path=Path("workspaces/project-1/media/audio.wav"),
        hotwords=("VideoSieve", "ASR"),
        language_hint="zh",
    )

    result = provider.transcribe(request)

    assert result.metadata["provider_kind"] == "stub"
    assert result.metadata["language_hint"] == "zh"
    assert result.metadata["hotwords"] == ["VideoSieve", "ASR"]
    assert result.segments[0].lang == "zh"
    assert "Hotwords: VideoSieve, ASR" in result.segments[0].text


def test_baseline_provider_defaults_language_to_und() -> None:
    provider = BaselineASRProvider(default_texts=("hello",))
    request = ASRRequest(audio_path=Path("audio.wav"))

    result = provider.transcribe(request)

    assert len(result.segments) == 1
    assert result.segments[0].lang == "und"
    assert result.segments[0].start == 0.0
    assert result.segments[0].end > result.segments[0].start
