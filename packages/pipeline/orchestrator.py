"""Stage orchestration with cooperative control semantics."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from asr import ASRProvider, BaselineASRProvider, write_transcript_jsonl
from contracts import ControlCommandType, JobStatus, StageName
from core import apply_job_transition
from deliverables import DeliverablesService
from frame_summary import FrameSummaryService, QwenFrameSummaryProvider
from fusion import FusionService
from hotwords import run_hotwords_from_meta
from infra.interfaces import EventBus, JobRepository, WorkspaceStore
from infra.models import JobRecord
from ingest import INGEST_CANCELLED, IngestError, IngestRequest, run_ingest
from keyframes import (
    KeyframeAlgorithmService,
    KeyframeBaselineService,
    KeyframeRecord,
    build_images_zip,
    write_images_for_records,
)

from .checkpoint import CheckpointStore
from .control import ControlAckPayload, evaluate_control_command
from .events import publish_event
from .models import STAGE_SEQUENCE, STAGE_WEIGHTS, PipelineRunResult

# VLM setting keys — must match apps/api/service.py constants exactly
_SETTING_VLM_BASE_URL = "vlm_base_url"
_SETTING_VLM_MODEL = "vlm_model"
_SETTING_VLM_FRAME_PROMPT_ZH = "vlm_frame_prompt_zh"
_SETTING_VLM_FRAME_PROMPT_EN = "vlm_frame_prompt_en"
_SETTING_VLM_CONCURRENCY = "vlm_concurrency"
_SETTING_VLM_RPM = "vlm_rpm"


@dataclass(slots=True)
class _SafetySignal(Exception):
    kind: str


class PipelineOrchestrator:
    """Run one job through the canonical stage sequence."""

    def __init__(
        self,
        *,
        repository: JobRepository,
        workspace: WorkspaceStore,
        event_bus: EventBus,
        asr_provider: ASRProvider | None = None,
    ) -> None:
        self._repository = repository
        self._workspace = workspace
        self._event_bus = event_bus
        self._asr_provider = asr_provider or BaselineASRProvider()
        self._checkpoint_store = CheckpointStore(workspace)
        self._pending_pause: set[str] = set()
        self._pending_cancel: set[str] = set()
        self._pending_delete: set[str] = set()

    def run_job(
        self,
        *,
        project_id: str,
        job_id: str,
        source_path: str | None = None,
        ingest_config: dict[str, Any] | None = None,
        rerun_from_stage: StageName | None = None,
        title: str | None = None,
        description: str = "",
        tags: list[str] | None = None,
        language_hint: str | None = None,
        duration_seconds: float = 30.0,
    ) -> PipelineRunResult:
        """Run or rerun one job with checkpoint support."""

        self._workspace.ensure_project_layout(project_id)
        checkpoint = self._checkpoint_store.load(project_id, job_id)
        checkpoint.reused_until_stage = None

        current_status = _to_job_status(self._job_status(job_id))
        if current_status in {JobStatus.QUEUED, JobStatus.PAUSED}:
            self._set_job_status(project_id, job_id, JobStatus.RUNNING, stage=None)

        start_index = 0
        if rerun_from_stage is not None:
            start_index = STAGE_SEQUENCE.index(rerun_from_stage)
            if start_index > 0:
                checkpoint.reused_until_stage = STAGE_SEQUENCE[start_index - 1].value

        completed = list(checkpoint.completed_stages)

        try:
            for index, stage in enumerate(STAGE_SEQUENCE):
                self._safety_point(project_id, job_id)

                if index < start_index:
                    continue

                checkpoint.current_stage = stage.value
                self._checkpoint_store.save(checkpoint)
                self._publish_stage_changed(project_id, job_id, stage)
                self._set_job_status(project_id, job_id, JobStatus.RUNNING, stage=stage)

                try:
                    self._run_stage(
                        stage,
                        project_id=project_id,
                        job_id=job_id,
                        source_path=source_path,
                        ingest_config=ingest_config or {},
                        title=title,
                        description=description,
                        tags=tags or [],
                        language_hint=language_hint,
                        duration_seconds=duration_seconds,
                    )
                except _SafetySignal:
                    raise
                except Exception as exc:
                    checkpoint.stage_statuses[stage.value] = "failed"
                    self._checkpoint_store.save(checkpoint)
                    self._set_job_status(project_id, job_id, JobStatus.FAILED, stage=stage)
                    self._publish_log(
                        project_id,
                        job_id,
                        level="error",
                        message=(
                            f"阶段 {stage.value} | 结果: 失败 | 原因: {exc} | "
                            "建议: 检查该阶段输入与依赖后重试"
                        ),
                    )
                    publish_event(
                        self._event_bus,
                        project_id=project_id,
                        job_id=job_id,
                        event_type="error",
                        payload={
                            "stage": stage.value,
                            "code": "PIPELINE_STAGE_FAILED",
                            "message": str(exc),
                        },
                    )
                    raise

                checkpoint.stage_statuses[stage.value] = "succeeded"
                if stage.value not in completed:
                    completed.append(stage.value)
                checkpoint.completed_stages = completed
                self._checkpoint_store.save(checkpoint)
                self._publish_log(
                    project_id,
                    job_id,
                    level="info",
                    message=f"阶段 {stage.value} | 结果: 完成",
                )
                self._publish_progress(project_id, job_id, stage)

                self._safety_point(project_id, job_id)

            self._safety_point(project_id, job_id)
            checkpoint.current_stage = None
            self._checkpoint_store.save(checkpoint)
            self._set_job_status(
                project_id, job_id, JobStatus.SUCCEEDED, stage=StageName.DELIVERABLES
            )
            return PipelineRunResult(
                project_id=project_id,
                job_id=job_id,
                status=JobStatus.SUCCEEDED.value,
                completed_stages=completed,
                reused_until_stage=checkpoint.reused_until_stage,
            )
        except _SafetySignal as signal:
            if signal.kind == JobStatus.CANCELLED.value:
                checkpoint.current_stage = None
                self._checkpoint_store.save(checkpoint)
                self._set_job_status(project_id, job_id, JobStatus.CANCELLED, stage=None)
                if job_id in self._pending_delete:
                    self._cleanup_job_workspace(project_id, job_id)
                    self._pending_delete.discard(job_id)
                return PipelineRunResult(
                    project_id=project_id,
                    job_id=job_id,
                    status=JobStatus.CANCELLED.value,
                    completed_stages=completed,
                    reused_until_stage=checkpoint.reused_until_stage,
                )

            self._set_job_status(
                project_id,
                job_id,
                JobStatus.PAUSED,
                stage=StageName(checkpoint.current_stage) if checkpoint.current_stage else None,
            )
            return PipelineRunResult(
                project_id=project_id,
                job_id=job_id,
                status=JobStatus.PAUSED.value,
                completed_stages=completed,
                reused_until_stage=checkpoint.reused_until_stage,
            )

    def handle_control_command(
        self,
        *,
        project_id: str,
        job_id: str,
        command: ControlCommandType,
    ) -> dict[str, str | bool]:
        """Evaluate one control command and publish ``control_ack``."""

        current = _to_job_status(self._job_status(job_id))
        decision = evaluate_control_command(command, current)

        if decision.request_cancel:
            self._pending_cancel.add(job_id)
        if (
            command is ControlCommandType.PAUSE
            and decision.accepted
            and decision.target_status is not None
        ):
            self._pending_pause.add(job_id)
        if command is ControlCommandType.DELETE:
            self._pending_delete.add(job_id)
            if decision.request_cleanup:
                self._cleanup_job_workspace(project_id, job_id)
                self._pending_delete.discard(job_id)

        if command is ControlCommandType.RESUME and decision.accepted and decision.target_status:
            self._pending_pause.discard(job_id)
            self._set_job_status(project_id, job_id, decision.target_status, stage=None)

        payload = ControlAckPayload(
            command=command.value,
            accepted=decision.accepted,
            reason=decision.reason,
            code=decision.code,
        ).to_dict()
        ack_payload: dict[str, object] = dict(payload)
        publish_event(
            self._event_bus,
            project_id=project_id,
            job_id=job_id,
            event_type="control_ack",
            payload=ack_payload,
        )
        return payload

    def _safety_point(self, project_id: str, job_id: str) -> None:
        current = _to_job_status(self._job_status(job_id))

        if current is JobStatus.CANCEL_REQUESTED:
            self._set_job_status(project_id, job_id, JobStatus.CANCELLED, stage=None)
            self._pending_cancel.discard(job_id)
            raise _SafetySignal(JobStatus.CANCELLED.value)

        if current is JobStatus.CANCELLED:
            raise _SafetySignal(JobStatus.CANCELLED.value)

        if job_id in self._pending_cancel and current in {
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.PAUSED,
        }:
            self._set_job_status(project_id, job_id, JobStatus.CANCELLED, stage=None)
            self._pending_cancel.discard(job_id)
            raise _SafetySignal(JobStatus.CANCELLED.value)

        if job_id in self._pending_pause and current is JobStatus.RUNNING:
            self._pending_pause.discard(job_id)
            raise _SafetySignal(JobStatus.PAUSED.value)

    def _run_stage(
        self,
        stage: StageName,
        *,
        project_id: str,
        job_id: str,
        source_path: str | None,
        ingest_config: dict[str, Any],
        title: str | None,
        description: str,
        tags: list[str],
        language_hint: str | None,
        duration_seconds: float,
    ) -> None:
        if stage is StageName.INGEST:
            last_download_log_at = 0.0

            def _on_ingest_download_progress(progress: dict[str, object]) -> None:
                nonlocal last_download_log_at

                def _as_int(value: object) -> int:
                    if isinstance(value, bool):
                        return int(value)
                    if isinstance(value, int):
                        return value
                    if isinstance(value, float):
                        return int(value)
                    if isinstance(value, str):
                        raw = value.strip()
                        if not raw:
                            return 0
                        try:
                            return int(raw)
                        except ValueError:
                            return 0
                    return 0

                now = time.monotonic()
                if last_download_log_at > 0 and now - last_download_log_at < 5.0:
                    return

                percent = str(progress.get("percent") or "").strip()
                speed = str(progress.get("speed") or "").strip()
                eta = str(progress.get("eta") or "").strip()
                role = str(progress.get("role") or "").strip()
                attempt = _as_int(progress.get("attempt"))
                attempts = _as_int(progress.get("attempts"))
                parts: list[str] = []
                if role in {"quality", "analysis"}:
                    parts.append(f"资源: {role}")
                if attempt > 0 and attempts > 1:
                    parts.append(f"轮次: {attempt}/{attempts}")
                if percent:
                    parts.append(f"下载进度: {percent}")
                if speed:
                    parts.append(f"速度: {speed}")
                if eta:
                    parts.append(f"剩余: {eta}")
                if not parts:
                    return

                self._publish_log(
                    project_id,
                    job_id,
                    level="info",
                    message=f"阶段 {stage.value} | " + " | ".join(parts),
                )
                last_download_log_at = now

            request_payload: dict[str, Any] = {
                "project_id": project_id,
                "job_id": job_id,
                "title": title or "上传视频",
                "description": description,
                "tags": tags,
                "language_hint": language_hint,
            }
            request_payload.update(ingest_config)
            # source_path takes precedence for local uploads
            if source_path and "source_url" not in request_payload:
                request_payload["source_path"] = source_path
            elif "source_path" not in request_payload and source_path:
                request_payload["source_path"] = source_path
            try:
                run_ingest(
                    self._workspace,
                    IngestRequest.model_validate(request_payload),
                    cancel_checker=lambda: self._is_cancel_requested(job_id),
                    progress_callback=_on_ingest_download_progress,
                )
            except IngestError as exc:
                if exc.code == INGEST_CANCELLED:
                    raise _SafetySignal(JobStatus.CANCELLED.value) from exc
                raise
            return

        if stage is StageName.HOTWORDS:
            run_hotwords_from_meta(self._workspace, project_id=project_id, job_id=job_id)
            return

        if stage is StageName.ASR:
            audio_path = self._workspace.audio_file(project_id, job_id)
            if not audio_path.exists():
                audio_path = self._workspace.source_video_file(project_id, job_id)
            write_transcript_jsonl(
                self._asr_provider,
                audio_path=audio_path,
                output_path=self._workspace.transcript_file(project_id, job_id),
                language_hint=language_hint,
            )
            return

        if stage is StageName.KEYFRAMES:
            analysis_video = self._workspace.job_path(
                project_id, job_id, "media", "source.analysis.mp4"
            )
            quality_video = self._workspace.source_video_file(project_id, job_id)
            if not quality_video.exists():
                KeyframeBaselineService(self._workspace).run(
                    project_id,
                    job_id,
                    duration_seconds=duration_seconds,
                    interval_seconds=5.0,
                    reason="sample",
                )
                return

            analysis_path = analysis_video if analysis_video.exists() else quality_video
            records: list[KeyframeRecord]
            cv2_available = _is_cv2_available()
            try:
                KeyframeAlgorithmService(self._workspace).run_from_dual_sources(
                    project_id,
                    job_id,
                    analysis_video_path=analysis_path,
                    quality_video_path=quality_video,
                    same_source=analysis_path.resolve() == quality_video.resolve(),
                )
                records = _load_keyframe_records(self._workspace.keyframes_file(project_id, job_id))
            except Exception as exc:
                self._publish_log(
                    project_id,
                    job_id,
                    level="warning",
                    message=(
                        f"阶段 {stage.value} | 动作: 关键帧算法提取失败，已回退到基线策略 | "
                        f"原因: {exc} | 建议: 检查视频解码链路后重试"
                    ),
                )
                records = KeyframeBaselineService(self._workspace).run(
                    project_id,
                    job_id,
                    duration_seconds=duration_seconds,
                    interval_seconds=5.0,
                    reason="sample",
                )

            if not cv2_available:
                self._publish_log(
                    project_id,
                    job_id,
                    level="warning",
                    message=(
                        f"阶段 {stage.value} | 动作: 跳过关键帧图片提取 | "
                        "原因: 未检测到 opencv-python | "
                        "建议: 安装 opencv-python 后重试"
                    ),
                )
                return

            if records:
                existing_images = sum(1 for record in records if Path(record.path).exists())
                if existing_images == 0:
                    try:
                        write_images_for_records(
                            quality_video,
                            timestamps_to_paths=[
                                (record.ts, Path(record.path)) for record in records
                            ],
                        )
                    except Exception as exc:
                        self._publish_log(
                            project_id,
                            job_id,
                            level="warning",
                            message=(
                                f"阶段 {stage.value} | 动作: 关键帧图片提取重试失败 | "
                                f"原因: {exc} | "
                                "建议: 检查 ffmpeg/cv2 与视频编码兼容性"
                            ),
                        )
                    existing_images = sum(1 for record in records if Path(record.path).exists())
                if existing_images == 0:
                    message = (
                        f"阶段 {stage.value} | 结果: 失败 | 原因: 关键帧图片提取结果为空 | "
                        "建议: 检查视频解码与 ffmpeg/cv2 运行环境"
                    )
                    raise RuntimeError(message)
                build_images_zip(self._workspace, project_id, job_id)
            return

        if stage is StageName.FRAME_SUMMARY:
            FrameSummaryService(
                self._workspace,
                provider=QwenFrameSummaryProvider(
                    endpoint=self._read_vlm_str(
                        _SETTING_VLM_BASE_URL,
                        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                    ),
                    model=self._read_vlm_str(_SETTING_VLM_MODEL, "qwen3.5-plus"),
                    prompt_zh=self._read_vlm_str(
                        _SETTING_VLM_FRAME_PROMPT_ZH,
                        QwenFrameSummaryProvider.DEFAULT_PROMPT_ZH,
                    ),
                    prompt_en=self._read_vlm_str(
                        _SETTING_VLM_FRAME_PROMPT_EN,
                        QwenFrameSummaryProvider.DEFAULT_PROMPT_EN,
                    ),
                ),
            ).run(
                project_id,
                job_id,
                language_hint=language_hint,
                concurrency=self._read_vlm_int(_SETTING_VLM_CONCURRENCY, 5),
                rpm=self._read_vlm_int(_SETTING_VLM_RPM, 30),
            )
            return

        if stage is StageName.FUSION:
            FusionService(self._workspace).run(project_id, job_id=job_id)
            return

        if stage is StageName.DELIVERABLES:
            DeliverablesService(self._workspace).run(project_id, job_id=job_id)
            return

        raise ValueError(f"unsupported stage: {stage.value}")

    def _read_vlm_str(self, key: str, default: str) -> str:
        """Read a VLM string setting from the repository, falling back to default."""
        raw = self._repository.get_setting(key)
        if raw is None:
            return default
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, str) and parsed.strip() else default
        except Exception:
            return default

    def _read_vlm_int(self, key: str, default: int) -> int:
        """Read a VLM integer setting from the repository, falling back to default."""
        raw = self._repository.get_setting(key)
        if raw is None:
            return default
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, int) and not isinstance(parsed, bool) else default
        except Exception:
            return default

    def _publish_stage_changed(self, project_id: str, job_id: str, stage: StageName) -> None:
        self._publish_log(
            project_id,
            job_id,
            level="info",
            message=f"阶段 {stage.value} | 动作: 开始执行",
        )
        publish_event(
            self._event_bus,
            project_id=project_id,
            job_id=job_id,
            event_type="stage_changed",
            payload={"to": stage.value},
        )

    def _publish_progress(self, project_id: str, job_id: str, stage: StageName) -> None:
        stage_index = STAGE_SEQUENCE.index(stage)
        pct = sum(STAGE_WEIGHTS[item] for item in STAGE_SEQUENCE[: stage_index + 1])
        publish_event(
            self._event_bus,
            project_id=project_id,
            job_id=job_id,
            event_type="progress",
            payload={"stage": stage.value, "pct": min(100.0, pct)},
        )

    def _publish_log(self, project_id: str, job_id: str, *, level: str, message: str) -> None:
        line = f"[{level}] {message}"
        self._append_worker_log_line(project_id, job_id, line)
        publish_event(
            self._event_bus,
            project_id=project_id,
            job_id=job_id,
            event_type="log",
            payload={"level": level, "message": message},
        )

    def _append_worker_log_line(self, project_id: str, job_id: str, line: str) -> None:
        log_file = self._workspace.worker_log_file(project_id, job_id)
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")
        except OSError as exc:
            publish_event(
                self._event_bus,
                project_id=project_id,
                job_id=job_id,
                event_type="log",
                payload={"level": "warning", "message": f"日志写入失败: {exc}"},
            )

    def _cleanup_job_workspace(self, project_id: str, job_id: str) -> None:
        root = self._workspace.job_root(project_id, job_id)
        if root.exists():
            shutil.rmtree(root)

    def _job_status(self, job_id: str) -> str:
        job: JobRecord | None = self._repository.get_job(job_id)
        if job is None:
            raise ValueError(f"job not found: {job_id}")
        return str(job.status)

    def _is_cancel_requested(self, job_id: str) -> bool:
        status = _to_job_status(self._job_status(job_id))
        return status in {JobStatus.CANCEL_REQUESTED, JobStatus.CANCELLED}

    def _set_job_status(
        self,
        project_id: str,
        job_id: str,
        target: JobStatus,
        *,
        stage: StageName | None,
    ) -> None:
        current = _to_job_status(self._job_status(job_id))
        if current is not target:
            apply_job_transition(current, target)
        self._repository.update_job_status(
            job_id,
            status=target.value,
            stage=stage.value if stage is not None else None,
        )
        self._repository.update_project_status(project_id, target.value)


def _to_job_status(value: str) -> JobStatus:
    return JobStatus(value)


def _is_cv2_available() -> bool:
    return find_spec("cv2") is not None


def _load_keyframe_records(path: Path) -> list[KeyframeRecord]:
    if not path.exists():
        return []
    records: list[KeyframeRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        records.append(
            KeyframeRecord(
                frame_id=str(payload["frame_id"]),
                ts=float(payload["ts"]),
                path=str(payload["path"]),
                hash=str(payload["hash"]),
                score=float(payload["score"]),
                reason=str(payload["reason"]),
            )
        )
    return records
