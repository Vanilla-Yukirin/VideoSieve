"""Baseline keyframe service that writes canonical JSONL output."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from infra.interfaces import WorkspaceStore

from .models import ALLOWED_KEYFRAME_REASONS, KeyframeRecord
from .sampler import stable_sampling_timestamps


class KeyframeBaselineService:
    """Stable-sampling baseline (no real decoding) for keyframe extraction."""

    def __init__(self, workspace_store: WorkspaceStore) -> None:
        self._workspace_store = workspace_store

    def run(
        self,
        project_id: str,
        *,
        duration_seconds: float,
        interval_seconds: float = 5.0,
        reason: str = "sample",
    ) -> list[KeyframeRecord]:
        """Generate baseline keyframe rows and write ``frames/keyframes.jsonl``."""
        if reason not in ALLOWED_KEYFRAME_REASONS:
            raise ValueError(f"invalid keyframe reason: {reason}")

        self._workspace_store.ensure_project_layout(project_id)
        timestamps = stable_sampling_timestamps(duration_seconds, interval_seconds=interval_seconds)

        records: list[KeyframeRecord] = []
        for index, ts in enumerate(timestamps, start=1):
            frame_id = f"frame_{index:06d}"
            image_name = f"slide_{index:06d}.jpg"
            image_path = self._workspace_store.path(project_id, "frames", "images", image_name)
            key_hash = hashlib.sha1(f"{project_id}|{frame_id}|{ts}".encode()).hexdigest()
            records.append(
                KeyframeRecord(
                    frame_id=frame_id,
                    ts=ts,
                    path=str(image_path),
                    hash=key_hash,
                    score=1.0,
                    reason=reason,
                )
            )

        self._write_jsonl(self._workspace_store.keyframes_file(project_id), records)
        return records

    @staticmethod
    def _write_jsonl(path: Path, records: list[KeyframeRecord]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record.to_json(), ensure_ascii=False) + "\n")
