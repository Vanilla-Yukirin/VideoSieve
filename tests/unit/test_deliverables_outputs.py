from __future__ import annotations

import json
from pathlib import Path

import pytest

from deliverables import DeliverablesService
from infra import FileSystemWorkspaceStore
from overall_summary import (
    OverallSummaryResult,
    OverallSummaryService,
    SummaryProviderProvenance,
)


class _StaticSummaryProvider:
    provider_name = "test-summary"
    model_name = "test-model"

    def summarize(
        self,
        source_text: str,
        *,
        language_hint: str | None,
        partial: bool,
    ) -> OverallSummaryResult:
        del source_text, language_hint, partial
        return OverallSummaryResult(
            text="generated summary",
            provider=self.provider_name,
            model=self.model_name,
        )

    def describe_provenance(
        self, *, language_hint: str | None
    ) -> SummaryProviderProvenance:
        del language_hint
        return SummaryProviderProvenance(
            provider=self.provider_name,
            model=self.model_name,
            prompt_version="test-v1",
            prompt_sha256="c" * 64,
            endpoint_sha256="d" * 64,
            parameters={"temperature": 0.0},
        )


def test_deliverables_writes_expected_files_and_content(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = DeliverablesService(store)
    project_id = "project-deliverables-1"
    job_id = "job-1"

    timeline_path = store.timeline_file(project_id, job_id)
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    timeline_payload = {
        "schema_version": "1.0",
        "project_id": project_id,
        "job_id": job_id,
        "chunks": [
            {
                "chunk_id": "ch_0001",
                "start": 0.0,
                "end": 5.0,
                "text": "first chunk",
                "transcript_refs": ["seg_0001"],
                "frame_refs": ["frame_000001"],
                "frame_summary_refs": ["frame_000001:summary"],
            }
        ],
    }
    timeline_path.write_text(
        json.dumps(timeline_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result = service.run(project_id, job_id=job_id)

    clean_path = store.clean_transcript_file(project_id, job_id)
    notes_path = store.illustrated_notes_file(project_id, job_id)
    summary_path = store.summary_file(project_id, job_id)
    manifest_path = store.deliverables_manifest_file(project_id, job_id)

    assert result.clean_transcript_path == str(clean_path)
    assert result.illustrated_notes_path == str(notes_path)
    assert result.summary_path is None
    assert result.manifest_path == str(manifest_path)
    assert len(result.generation_id) == 32

    assert clean_path.exists()
    assert notes_path.exists()
    assert not summary_path.exists()
    assert manifest_path.exists()

    assert "first chunk" in clean_path.read_text(encoding="utf-8")
    notes_text = notes_path.read_text(encoding="utf-8")
    assert "[[frame:slide_000001]]" in notes_text
    assert "first chunk" in notes_text

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["ready"] is True
    assert manifest["generation_id"] == result.generation_id
    assert manifest["source_ids"] == ["transcript:ch_0001"]
    assert len(manifest["input_sha256"]) == 64
    assert len(manifest["config_sha256"]) == 64
    assert {item["path"] for item in manifest["artifacts"]} == {
        "outputs/clean_transcript.md",
        "outputs/illustrated_notes.md",
    }


def test_deliverables_manifest_with_relative_workspace_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    store = FileSystemWorkspaceStore(Path("workspaces"))
    timeline_path = store.timeline_file("project-relative", "job-relative")
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    timeline_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_id": "project-relative",
                "job_id": "job-relative",
                "chunks": [
                    {"chunk_id": "ch_0001", "start": 0.0, "end": 1.0, "text": "content"}
                ],
            }
        ),
        encoding="utf-8",
    )

    result = DeliverablesService(store).run("project-relative", job_id="job-relative")

    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert {item["path"] for item in manifest["artifacts"]} == {
        "outputs/clean_transcript.md",
        "outputs/illustrated_notes.md",
    }


def test_deliverables_missing_or_empty_timeline_behavior(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = DeliverablesService(store)
    missing_project_id = "project-deliverables-missing"
    missing_job_id = "job-missing"
    store.ensure_job_layout(missing_project_id, missing_job_id)
    missing_stale_paths = [
        store.clean_transcript_file(missing_project_id, missing_job_id),
        store.illustrated_notes_file(missing_project_id, missing_job_id),
        store.summary_file(missing_project_id, missing_job_id),
        store.deliverables_manifest_file(missing_project_id, missing_job_id),
    ]
    for path in missing_stale_paths:
        path.write_text("stale", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        service.run(missing_project_id, job_id=missing_job_id)
    assert all(not path.exists() for path in missing_stale_paths)

    project_id = "project-deliverables-empty"
    job_id = "job-empty"
    timeline_path = store.timeline_file(project_id, job_id)
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    timeline_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_id": project_id,
                "job_id": job_id,
                "chunks": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    stale_paths = [
        store.clean_transcript_file(project_id, job_id),
        store.illustrated_notes_file(project_id, job_id),
        store.summary_file(project_id, job_id),
        store.deliverables_manifest_file(project_id, job_id),
    ]
    for path in stale_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stale", encoding="utf-8")

    with pytest.raises(ValueError, match="DELIVERABLES_INPUT_EMPTY"):
        service.run(project_id, job_id=job_id)
    assert all(not path.exists() for path in stale_paths)


def test_deliverables_summary_generation_manifest_covers_frame_evidence(
    tmp_path: Path,
) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    project_id = "project-summary"
    job_id = "job-summary"
    timeline_path = store.timeline_file(project_id, job_id)
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    timeline_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_id": project_id,
                "job_id": job_id,
                "chunks": [
                    {
                        "chunk_id": "ch_0001",
                        "start": 0.0,
                        "end": 1.0,
                        "text": "transcript evidence",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    frame_path = store.frame_summary_file(project_id, job_id)
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "frame_id": "frame_1",
                "lang": "en",
                "provider": "test-frame",
                "description_text": "visual evidence",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    service = DeliverablesService(
        store,
        overall_summary=OverallSummaryService(store, _StaticSummaryProvider()),
    )

    result = service.run(project_id, job_id=job_id, summary_enabled=True)

    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert result.summary_path is not None
    summary = json.loads(Path(result.summary_path).read_text(encoding="utf-8"))
    assert manifest["source_ids"] == ["transcript:ch_0001", "frame:frame_1"]
    assert manifest["input_sha256"] == summary["provenance"]["input_sha256"]
    assert manifest["summary_provenance"] == summary["provenance"]
    assert {item["artifact_type"] for item in manifest["artifacts"]} == {
        "clean_transcript",
        "illustrated_notes",
        "summary",
    }


def test_deliverables_publish_failure_leaves_no_ready_or_partial_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = DeliverablesService(store)
    project_id = "project-publish-failure"
    job_id = "job-publish-failure"
    timeline_path = store.timeline_file(project_id, job_id)
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    timeline_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_id": project_id,
                "job_id": job_id,
                "chunks": [
                    {
                        "chunk_id": "ch_0001",
                        "start": 0.0,
                        "end": 1.0,
                        "text": "evidence",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    original_publish = service._publish_file
    publish_count = 0

    def fail_second_publish(staged_path: Path, canonical_path: Path) -> None:
        nonlocal publish_count
        publish_count += 1
        if publish_count == 2:
            raise OSError("simulated publish failure")
        original_publish(staged_path, canonical_path)

    monkeypatch.setattr(service, "_publish_file", fail_second_publish)

    with pytest.raises(OSError, match="simulated publish failure"):
        service.run(project_id, job_id=job_id)

    assert not store.clean_transcript_file(project_id, job_id).exists()
    assert not store.illustrated_notes_file(project_id, job_id).exists()
    assert not store.summary_file(project_id, job_id).exists()
    assert not store.deliverables_manifest_file(project_id, job_id).exists()
    outputs = store.job_path(project_id, job_id, "outputs")
    assert not list(outputs.glob("*.tmp"))


def test_deliverables_rejects_malformed_timeline_without_ready_manifest(
    tmp_path: Path,
) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    service = DeliverablesService(store)
    project_id = "project-malformed"
    job_id = "job-malformed"
    timeline_path = store.timeline_file(project_id, job_id)
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    timeline_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_id": project_id,
                "job_id": job_id,
                "chunks": ["silently dropped before this fix"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        service.run(project_id, job_id=job_id)

    assert getattr(exc_info.value, "code", None) == "DELIVERABLES_INPUT_INVALID"
    assert not store.deliverables_manifest_file(project_id, job_id).exists()
