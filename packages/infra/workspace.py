"""Filesystem workspace path builder and layout helper."""

from __future__ import annotations

from pathlib import Path

from .interfaces import WorkspaceStore

JOB_WORKSPACE_DIRS: tuple[str, ...] = (
    "meta",
    "media",
    "hotwords",
    "asr",
    "frames",
    "frames/images",
    "frames/metrics",
    "frame_summary",
    "fusion",
    "outputs",
    "logs",
)


class FileSystemWorkspaceStore(WorkspaceStore):
    """Workspace helper with canonical path builders."""

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir)

    def project_root(self, project_id: str) -> Path:
        return self._base_dir / project_id

    def ensure_project_layout(self, project_id: str) -> Path:
        root = self.project_root(project_id)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def job_root(self, project_id: str, job_id: str) -> Path:
        return self.project_root(project_id) / "jobs" / job_id

    def ensure_job_layout(self, project_id: str, job_id: str) -> Path:
        root = self.job_root(project_id, job_id)
        root.mkdir(parents=True, exist_ok=True)
        for rel_dir in JOB_WORKSPACE_DIRS:
            (root / rel_dir).mkdir(parents=True, exist_ok=True)
        return root

    def path(self, project_id: str, *parts: str) -> Path:
        root = self.project_root(project_id).resolve()
        candidate = (root / Path(*parts)).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError("workspace path escapes project root")
        return candidate

    def job_path(self, project_id: str, job_id: str, *parts: str) -> Path:
        root = self.job_root(project_id, job_id).resolve()
        candidate = (root / Path(*parts)).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError("workspace path escapes job root")
        return candidate

    def meta_file(self, project_id: str) -> Path:
        return self.path(project_id, "meta", "meta.json")

    def job_meta_file(self, project_id: str, job_id: str) -> Path:
        return self.job_path(project_id, job_id, "meta", "meta.json")

    def config_snapshot_file(self, project_id: str, job_id: str) -> Path:
        return self.job_path(project_id, job_id, "meta", "config.snapshot.json")

    def source_video_file(self, project_id: str, job_id: str) -> Path:
        return self.job_path(project_id, job_id, "media", "source.mp4")

    def audio_file(self, project_id: str, job_id: str) -> Path:
        return self.job_path(project_id, job_id, "media", "audio.wav")

    def hotwords_file(self, project_id: str, job_id: str) -> Path:
        return self.job_path(project_id, job_id, "hotwords", "hotwords.json")

    def transcript_file(self, project_id: str, job_id: str) -> Path:
        return self.job_path(project_id, job_id, "asr", "transcript.jsonl")

    def keyframes_file(self, project_id: str, job_id: str) -> Path:
        return self.job_path(project_id, job_id, "frames", "keyframes.jsonl")

    def frame_summary_file(self, project_id: str, job_id: str) -> Path:
        return self.job_path(project_id, job_id, "frame_summary", "frame_summary.jsonl")

    def timeline_file(self, project_id: str, job_id: str) -> Path:
        return self.job_path(project_id, job_id, "fusion", "timeline.json")

    def clean_transcript_file(self, project_id: str, job_id: str) -> Path:
        return self.job_path(project_id, job_id, "outputs", "clean_transcript.md")

    def illustrated_notes_file(self, project_id: str, job_id: str) -> Path:
        return self.job_path(project_id, job_id, "outputs", "illustrated_notes.md")

    def summary_file(self, project_id: str, job_id: str) -> Path:
        return self.job_path(project_id, job_id, "outputs", "summary.json")

    def worker_log_file(self, project_id: str, job_id: str) -> Path:
        return self.job_path(project_id, job_id, "logs", "worker.log")
