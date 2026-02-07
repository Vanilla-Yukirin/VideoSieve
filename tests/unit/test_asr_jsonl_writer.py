from __future__ import annotations

import json
from pathlib import Path

from asr import BaselineASRProvider, write_transcript_jsonl
from contracts.models import SCHEMA_VERSION


def test_write_transcript_jsonl_matches_contract_fields(tmp_path: Path) -> None:
    provider = BaselineASRProvider(default_texts=("alpha", "beta"))
    output_path = tmp_path / "asr" / "transcript.jsonl"

    result = write_transcript_jsonl(
        provider,
        audio_path=tmp_path / "media" / "audio.wav",
        output_path=output_path,
        hotwords=("VideoSieve",),
        language_hint="en",
    )

    assert output_path.exists()
    assert result.metadata["hotwords"] == ["VideoSieve"]
    assert result.metadata["language_hint"] == "en"

    rows = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 2

    required_fields = {
        "schema_version",
        "segment_id",
        "start",
        "end",
        "text",
        "lang",
        "conf",
    }
    for row in rows:
        assert set(row.keys()) == required_fields
        assert row["schema_version"] == SCHEMA_VERSION
        assert isinstance(row["start"], float)
        assert isinstance(row["end"], float)
        assert row["end"] > row["start"]
        assert isinstance(row["text"], str)
        assert isinstance(row["lang"], str)
        assert isinstance(row["conf"], float)
