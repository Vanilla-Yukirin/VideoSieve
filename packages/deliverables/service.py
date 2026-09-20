"""Generate final markdown/json outputs from `fusion/timeline.json`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from infra.interfaces import WorkspaceStore
from overall_summary import OverallSummaryService


@dataclass(frozen=True)
class DeliverablesResult:
    """Output artifact paths for one deliverables run."""

    project_id: str
    job_id: str
    clean_transcript_path: str
    illustrated_notes_path: str
    summary_path: str | None


class DeliverablesService:
    """Create MVP deliverables from timeline chunks."""

    def __init__(
        self,
        workspace_store: WorkspaceStore,
        *,
        overall_summary: OverallSummaryService | None = None,
    ) -> None:
        self._workspace_store = workspace_store
        self._overall_summary = overall_summary

    def run(
        self,
        project_id: str,
        *,
        job_id: str,
        summary_enabled: bool = False,
        language_hint: str | None = None,
    ) -> DeliverablesResult:
        self._workspace_store.ensure_job_layout(project_id, job_id)

        timeline_path = self._workspace_store.timeline_file(project_id, job_id)
        clean_transcript_path = self._workspace_store.clean_transcript_file(project_id, job_id)
        illustrated_notes_path = self._workspace_store.illustrated_notes_file(project_id, job_id)
        summary_path = self._workspace_store.summary_file(project_id, job_id)

        if not timeline_path.exists():
            raise FileNotFoundError(timeline_path)

        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        chunks = timeline.get("chunks", [])
        if not isinstance(chunks, list):
            raise ValueError("timeline chunks must be a list")

        if not any(
            isinstance(chunk, dict) and str(chunk.get("text") or "").strip()
            for chunk in chunks
        ):
            raise ValueError("DELIVERABLES_INPUT_EMPTY: timeline contains no transcript text")

        clean_transcript = self._render_clean_transcript(chunks)
        illustrated_notes = self._render_illustrated_notes(chunks)
        clean_transcript_path.unlink(missing_ok=True)
        illustrated_notes_path.unlink(missing_ok=True)
        summary_path.unlink(missing_ok=True)

        if summary_enabled:
            if self._overall_summary is None:
                raise RuntimeError(
                    "overall summary is enabled but no model-backed summary service is configured"
                )
            self._overall_summary.run(
                project_id,
                job_id=job_id,
                language_hint=language_hint,
            )
        else:
            summary_path.unlink(missing_ok=True)

        self._write_text_atomic(clean_transcript_path, clean_transcript)
        self._write_text_atomic(illustrated_notes_path, illustrated_notes)

        return DeliverablesResult(
            project_id=project_id,
            job_id=job_id,
            clean_transcript_path=str(clean_transcript_path),
            illustrated_notes_path=str(illustrated_notes_path),
            summary_path=str(summary_path) if summary_enabled else None,
        )

    @staticmethod
    def _render_clean_transcript(chunks: list[object]) -> str:
        lines = ["# Clean Transcript", ""]
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            text = str(chunk.get("text", "")).strip()
            if text:
                lines.append(text)
                lines.append("")
        if len(lines) == 2:
            lines.append("(empty)")
            lines.append("")
        return "\n".join(lines)

    def _render_illustrated_notes(self, chunks: list[object]) -> str:
        lines = ["# Illustrated Notes", ""]
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue

            frame_refs = chunk.get("frame_refs", [])
            if isinstance(frame_refs, list):
                for frame_ref in frame_refs:
                    frame_name = self._to_slide_placeholder_name(str(frame_ref))
                    lines.append(f"[[frame:{frame_name}]]")

            text = str(chunk.get("text", "")).strip()
            if text:
                lines.append(text)
                lines.append("")

        if len(lines) == 2:
            lines.append("(empty)")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _to_slide_placeholder_name(frame_ref: str) -> str:
        if frame_ref.startswith("slide_"):
            return frame_ref
        if frame_ref.startswith("frame_"):
            return "slide_" + frame_ref[len("frame_") :]
        return frame_ref

    @staticmethod
    def _write_text_atomic(path: Path, content: str) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            temp_path.write_text(content, encoding="utf-8")
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)
