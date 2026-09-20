"""Generate final markdown/json outputs from `fusion/timeline.json`."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from infra.interfaces import WorkspaceStore
from overall_summary import (
    EvidenceValidationError,
    OverallSummaryService,
    evidence_sha256,
    read_timeline_evidence,
    sha256_file,
    sha256_json,
)


@dataclass(frozen=True)
class DeliverablesResult:
    """Output artifact paths for one deliverables run."""

    project_id: str
    job_id: str
    clean_transcript_path: str
    illustrated_notes_path: str
    summary_path: str | None
    manifest_path: str
    generation_id: str


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
        manifest_path = self._workspace_store.deliverables_manifest_file(project_id, job_id)
        generation_id = uuid.uuid4().hex
        staged_clean_path = self._staging_path(clean_transcript_path)
        staged_notes_path = self._staging_path(illustrated_notes_path)
        staged_summary_path = self._staging_path(summary_path)
        staged_manifest_path = self._staging_path(manifest_path)
        canonical_paths = [
            manifest_path,
            clean_transcript_path,
            illustrated_notes_path,
            summary_path,
        ]
        staging_paths = [
            staged_clean_path,
            staged_notes_path,
            staged_summary_path,
            staged_manifest_path,
        ]
        self._unlink_all([*canonical_paths, *staging_paths])

        if not timeline_path.exists():
            raise FileNotFoundError(timeline_path)

        try:
            timeline = read_timeline_evidence(
                timeline_path,
                project_id=project_id,
                job_id=job_id,
                error_code="DELIVERABLES_INPUT_INVALID",
            )
            if not timeline.sections:
                raise EvidenceValidationError(
                    "DELIVERABLES_INPUT_EMPTY",
                    "timeline contains no transcript evidence",
                )

            clean_transcript = self._render_clean_transcript(timeline.chunks)
            illustrated_notes = self._render_illustrated_notes(timeline.chunks)
            staged_clean_path.write_text(clean_transcript, encoding="utf-8")
            staged_notes_path.write_text(illustrated_notes, encoding="utf-8")

            summary_provenance: dict[str, object] | None = None
            if summary_enabled:
                if self._overall_summary is None:
                    raise RuntimeError(
                        "overall summary is enabled but no model-backed summary "
                        "service is configured"
                    )
                self._overall_summary.run(
                    project_id,
                    job_id=job_id,
                    language_hint=language_hint,
                    output_path=staged_summary_path,
                )
                summary_payload = json.loads(staged_summary_path.read_text(encoding="utf-8"))
                raw_provenance = (
                    summary_payload.get("provenance")
                    if isinstance(summary_payload, dict)
                    else None
                )
                if not isinstance(raw_provenance, dict):
                    raise RuntimeError("overall summary artifact is missing provenance")
                summary_provenance = raw_provenance

            staged_artifacts: list[tuple[str, Path, Path]] = [
                ("clean_transcript", staged_clean_path, clean_transcript_path),
                ("illustrated_notes", staged_notes_path, illustrated_notes_path),
            ]
            if summary_enabled:
                staged_artifacts.append(("summary", staged_summary_path, summary_path))

            generated_at = datetime.now(UTC).isoformat()
            deliverables_config = {
                "summary_enabled": summary_enabled,
                "language_hint": language_hint,
                "format_version": "deliverables-v1",
            }
            transcript_source_ids = [section.source_id for section in timeline.sections]
            if summary_provenance is not None:
                raw_source_ids = summary_provenance.get("source_ids")
                raw_coverage = summary_provenance.get("coverage")
                input_sha256 = summary_provenance.get("input_sha256")
                if (
                    not isinstance(raw_source_ids, list)
                    or any(not isinstance(item, str) for item in raw_source_ids)
                    or not isinstance(raw_coverage, dict)
                    or not isinstance(input_sha256, str)
                ):
                    raise RuntimeError("overall summary provenance is incomplete")
                source_ids = raw_source_ids
                coverage = raw_coverage
            else:
                source_ids = transcript_source_ids
                coverage = {
                    "validated_source_count": len(source_ids),
                    "published_transcript_section_count": len(source_ids),
                    "coverage_ratio": 1.0,
                }
                input_sha256 = evidence_sha256(timeline.sections)
            manifest_payload = {
                "schema_version": "1.0",
                "ready": True,
                "generation_id": generation_id,
                "generated_at": generated_at,
                "project_id": project_id,
                "job_id": job_id,
                "summary_enabled": summary_enabled,
                "timeline_sha256": sha256_file(timeline_path),
                "input_sha256": input_sha256,
                "config_sha256": sha256_json(deliverables_config),
                "source_ids": source_ids,
                "coverage": coverage,
                "artifacts": [
                    self._artifact_manifest_entry(
                        artifact_type,
                        staged_path,
                        canonical_path,
                        project_id=project_id,
                        job_id=job_id,
                    )
                    for artifact_type, staged_path, canonical_path in staged_artifacts
                ],
                "summary_provenance": summary_provenance,
            }
            staged_manifest_path.write_text(
                json.dumps(manifest_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            for _, staged_path, canonical_path in staged_artifacts:
                self._publish_file(staged_path, canonical_path)
            self._publish_file(staged_manifest_path, manifest_path)

            return DeliverablesResult(
                project_id=project_id,
                job_id=job_id,
                clean_transcript_path=str(clean_transcript_path),
                illustrated_notes_path=str(illustrated_notes_path),
                summary_path=str(summary_path) if summary_enabled else None,
                manifest_path=str(manifest_path),
                generation_id=generation_id,
            )
        except Exception:
            self._unlink_all([*canonical_paths, *staging_paths])
            raise
        finally:
            self._unlink_all(staging_paths)

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
    def _staging_path(path: Path) -> Path:
        return path.with_name(f".{path.name}.generation.tmp")

    @staticmethod
    def _publish_file(staged_path: Path, canonical_path: Path) -> None:
        staged_path.replace(canonical_path)

    @staticmethod
    def _unlink_all(paths: list[Path]) -> None:
        for path in paths:
            path.unlink(missing_ok=True)

    def _artifact_manifest_entry(
        self,
        artifact_type: str,
        staged_path: Path,
        canonical_path: Path,
        *,
        project_id: str,
        job_id: str,
    ) -> dict[str, object]:
        return {
            "artifact_type": artifact_type,
            "path": canonical_path.relative_to(
                self._workspace_store.job_root(project_id, job_id)
            ).as_posix(),
            "size_bytes": staged_path.stat().st_size,
            "sha256": sha256_file(staged_path),
        }
