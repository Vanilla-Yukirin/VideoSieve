"""Assemble ASR, keyframes, and frame summaries into timeline output."""

from __future__ import annotations

import json
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from contracts.models import SCHEMA_VERSION
from infra.interfaces import WorkspaceStore


@dataclass(frozen=True)
class FusionResult:
    """Fusion output location and in-memory timeline payload."""

    project_id: str
    job_id: str
    timeline_path: str
    timeline: dict[str, object]


class FusionService:
    """Timeline builder using keyframe chapter boundaries plus evidence refs."""

    def __init__(self, workspace_store: WorkspaceStore) -> None:
        self._workspace_store = workspace_store

    def run(self, project_id: str, *, job_id: str) -> FusionResult:
        self._workspace_store.ensure_project_layout(project_id)

        transcript_path = self._workspace_store.path(project_id, "asr", "transcript.jsonl")
        keyframes_path = self._workspace_store.path(project_id, "frames", "keyframes.jsonl")
        frame_summary_path = self._workspace_store.frame_summary_file(project_id)
        timeline_path = self._workspace_store.path(project_id, "fusion", "timeline.json")

        transcript_rows = self._read_jsonl(transcript_path, required=True)
        keyframe_rows = self._read_jsonl(keyframes_path, required=False)
        frame_summary_rows = self._read_jsonl(frame_summary_path, required=False)

        chunks = self._build_chunks(transcript_rows, keyframe_rows, frame_summary_rows)
        timeline: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "project_id": project_id,
            "job_id": job_id,
            "chunks": chunks,
        }

        timeline_path.parent.mkdir(parents=True, exist_ok=True)
        timeline_path.write_text(
            json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return FusionResult(
            project_id=project_id,
            job_id=job_id,
            timeline_path=str(timeline_path),
            timeline=timeline,
        )

    @staticmethod
    def _read_jsonl(path: Path, *, required: bool) -> list[dict[str, object]]:
        if not path.exists():
            if required:
                raise FileNotFoundError(path)
            return []

        rows: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        return rows

    def _build_chunks(
        self,
        transcript_rows: list[dict[str, object]],
        keyframe_rows: list[dict[str, object]],
        frame_summary_rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if not transcript_rows:
            return []

        transcript_rows.sort(key=lambda row: self._to_float(row["start"]))
        keyframe_rows.sort(key=lambda row: self._to_float(row["ts"]))

        frame_summary_index = self._build_frame_summary_ref_index(frame_summary_rows)

        if not keyframe_rows:
            chunks: list[dict[str, object]] = []
            for idx, segment in enumerate(transcript_rows, start=1):
                seg_id = str(segment["segment_id"])
                chunks.append(
                    {
                        "chunk_id": f"ch_{idx:04d}",
                        "start": self._to_float(segment["start"]),
                        "end": self._to_float(segment["end"]),
                        "text": str(segment["text"]).strip(),
                        "transcript_refs": [seg_id],
                        "frame_refs": [],
                        "frame_summary_refs": [],
                    }
                )
            return chunks

        boundaries = self._compute_midpoint_boundaries(keyframe_rows)
        grouped_segments: dict[int, list[dict[str, object]]] = {
            i: [] for i in range(len(keyframe_rows))
        }
        for segment in transcript_rows:
            midpoint = (self._to_float(segment["start"]) + self._to_float(segment["end"])) / 2.0
            chapter_idx = bisect_right(boundaries, midpoint)
            grouped_segments[chapter_idx].append(segment)

        chunks = []
        for chapter_idx, frame in enumerate(keyframe_rows):
            frame_id = str(frame["frame_id"])
            segments = grouped_segments[chapter_idx]
            if not segments:
                continue

            start = min(self._to_float(seg["start"]) for seg in segments)
            end = max(self._to_float(seg["end"]) for seg in segments)
            text = " ".join(
                str(seg["text"]).strip() for seg in segments if str(seg["text"]).strip()
            )
            transcript_refs = [str(seg["segment_id"]) for seg in segments]

            chunks.append(
                {
                    "chunk_id": f"ch_{chapter_idx + 1:04d}",
                    "start": start,
                    "end": end,
                    "text": text,
                    "transcript_refs": transcript_refs,
                    "frame_refs": [frame_id],
                    "frame_summary_refs": frame_summary_index.get(frame_id, []),
                }
            )

        if chunks:
            return chunks

        fallback_chunk = {
            "chunk_id": "ch_0001",
            "start": self._to_float(transcript_rows[0]["start"]),
            "end": self._to_float(transcript_rows[-1]["end"]),
            "text": " ".join(
                str(seg["text"]).strip() for seg in transcript_rows if str(seg["text"]).strip()
            ),
            "transcript_refs": [str(seg["segment_id"]) for seg in transcript_rows],
            "frame_refs": [],
            "frame_summary_refs": [],
        }
        return [fallback_chunk]

    @staticmethod
    def _compute_midpoint_boundaries(keyframe_rows: list[dict[str, object]]) -> list[float]:
        boundaries: list[float] = []
        for index in range(len(keyframe_rows) - 1):
            left = FusionService._to_float(keyframe_rows[index]["ts"])
            right = FusionService._to_float(keyframe_rows[index + 1]["ts"])
            boundaries.append((left + right) / 2.0)
        return boundaries

    @staticmethod
    def _to_float(value: object) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value)
        raise TypeError(f"Expected numeric value, got {type(value).__name__}")

    @staticmethod
    def _build_frame_summary_ref_index(
        frame_summary_rows: list[dict[str, object]],
    ) -> dict[str, list[str]]:
        refs_by_frame: dict[str, list[str]] = {}
        for row in frame_summary_rows:
            frame_id = str(row.get("frame_id", ""))
            if not frame_id:
                continue

            text = str(row.get("description_text", "")).strip()
            refs_by_frame[frame_id] = [f"{frame_id}:summary"] if text else []
        return refs_by_frame
