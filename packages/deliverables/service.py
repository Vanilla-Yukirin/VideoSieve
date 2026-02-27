"""Generate final markdown/json outputs from `fusion/timeline.json`."""

from __future__ import annotations

import json
from dataclasses import dataclass

from contracts.models import SCHEMA_VERSION
from infra.interfaces import WorkspaceStore


@dataclass(frozen=True)
class DeliverablesResult:
    """Output artifact paths for one deliverables run."""

    project_id: str
    job_id: str
    clean_transcript_path: str
    illustrated_notes_path: str
    summary_path: str


class DeliverablesService:
    """Create MVP deliverables from timeline chunks."""

    def __init__(self, workspace_store: WorkspaceStore) -> None:
        self._workspace_store = workspace_store

    def run(self, project_id: str, *, job_id: str) -> DeliverablesResult:
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

        clean_transcript_path.write_text(self._render_clean_transcript(chunks), encoding="utf-8")
        illustrated_notes_path.write_text(self._render_illustrated_notes(chunks), encoding="utf-8")

        summary_payload = {
            "schema_version": SCHEMA_VERSION,
            "title": f"Summary for {project_id}",
            "summary": self._render_summary_text(chunks),
        }
        summary_path.write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        return DeliverablesResult(
            project_id=project_id,
            job_id=job_id,
            clean_transcript_path=str(clean_transcript_path),
            illustrated_notes_path=str(illustrated_notes_path),
            summary_path=str(summary_path),
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
    def _render_summary_text(chunks: list[object]) -> str:
        texts: list[str] = []
        for chunk in chunks:
            if isinstance(chunk, dict):
                text = str(chunk.get("text", "")).strip()
                if text:
                    texts.append(text)
        if not texts:
            return "No content available."
        return " ".join(texts[:3])

    @staticmethod
    def _to_slide_placeholder_name(frame_ref: str) -> str:
        if frame_ref.startswith("slide_"):
            return frame_ref
        if frame_ref.startswith("frame_"):
            return "slide_" + frame_ref[len("frame_") :]
        return frame_ref
