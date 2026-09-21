"""Job-scoped API control plane service."""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO, cast

from pydantic import SecretStr

from contracts import ControlCommandType, JobStatus
from core import DELETE_PENDING_CLEANUP
from infra import (
    EventBus,
    EventSubscription,
    InfraEvent,
    JobRecord,
    JobRepository,
    UserCookieRecord,
    WorkspaceStore,
)
from infra.secrets import SecretCipherError, decrypt_secret, encrypt_secret
from ingest import IngestRequest, probe_url_formats
from ingest.errors import INGEST_AUTH_REQUIRED, IngestError
from overall_summary import OpenAICompatibleSummaryProvider
from pipeline.control import ControlAckPayload, evaluate_control_command

from .models import (
    ArtifactItem,
    CookieCreateRequest,
    CookieListItem,
    CookiePatchRequest,
    CookieValidateRequest,
    CookieValidateResponse,
    IngestAssetSelection,
    IngestFormatItem,
    IngestParams,
    IngestProbeRequest,
    IngestProbeResponse,
    JobCreateRequest,
    JobSnapshot,
    ProjectCreateRequest,
    SystemSettingsPatchRequest,
    SystemSettingsResponse,
    utc_now_iso,
)

MAX_LOG_BUFFER = 100
PROJECT_DELETE_WAIT_SECONDS = 10.0
PROJECT_DELETE_POLL_SECONDS = 0.2
LOCAL_COOKIE_OWNER_ID = "default_user"
LOCAL_ACTOR_ID = "local"
SETTING_ASR_PROVIDER = "asr_provider"
SETTING_ASR_ENDPOINT = "asr_endpoint"
SETTING_ASR_LANGUAGE = "asr_language"
SETTING_ASR_CONTEXT = "asr_context"
SETTING_ASR_TIMEOUT_SECONDS = "asr_timeout_seconds"
SETTING_VLM_BASE_URL = "vlm_base_url"
SETTING_VLM_MODEL = "vlm_model"
SETTING_VLM_FRAME_PROMPT_ZH = "vlm_frame_prompt_zh"
SETTING_VLM_FRAME_PROMPT_EN = "vlm_frame_prompt_en"
SETTING_VLM_CONCURRENCY = "vlm_concurrency"
SETTING_VLM_RPM = "vlm_rpm"
SETTING_SUMMARY_BASE_URL = "summary_base_url"
SETTING_SUMMARY_MODEL = "summary_model"
SETTING_SUMMARY_PROMPT_ZH = "summary_prompt_zh"
SETTING_SUMMARY_PROMPT_EN = "summary_prompt_en"
SETTING_SUMMARY_MAX_INPUT_CHARS = "summary_max_input_chars"
PROVIDER_SECRET_ASR_TOKEN = "capswriter_token"
PROVIDER_SECRET_VLM_API_KEY = "vlm_api_key"
PROVIDER_SECRET_SUMMARY_API_KEY = "summary_api_key"

# Must match QwenFrameSummaryProvider.DEFAULT_PROMPT_ZH / DEFAULT_PROMPT_EN exactly
_DEFAULT_VLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
_DEFAULT_VLM_MODEL = "qwen3.5-plus"
_DEFAULT_VLM_PROMPT_ZH = (
    "请直接用自然语言回答，不要JSON。"
    "请对当前画面做一段完整描述，优先覆盖主要内容、上方区域信息、下方区域信息、可见文字和图示关系。"
)
_DEFAULT_VLM_PROMPT_EN = (
    "Respond in plain natural language, not JSON. "
    "Give a complete frame description, including main content, upper area details, "
    "lower area details, visible text, and diagram relationships."
)
_DEFAULT_VLM_CONCURRENCY = 5
_DEFAULT_VLM_RPM = 30
_DEFAULT_ASR_PROVIDER = "unconfigured"
_DEFAULT_ASR_ENDPOINT = ""
_DEFAULT_ASR_LANGUAGE = "auto"
_DEFAULT_ASR_CONTEXT = ""
_DEFAULT_ASR_TIMEOUT_SECONDS = 900
_DEFAULT_SUMMARY_BASE_URL = (
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
)
_DEFAULT_SUMMARY_MODEL = "qwen-plus"
_DEFAULT_SUMMARY_PROMPT_ZH = OpenAICompatibleSummaryProvider.DEFAULT_PROMPT_ZH
_DEFAULT_SUMMARY_PROMPT_EN = OpenAICompatibleSummaryProvider.DEFAULT_PROMPT_EN
_DEFAULT_SUMMARY_MAX_INPUT_CHARS = 24_000


class ApiError(RuntimeError):
    """Structured API error with stable code and status."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class ApiConfigError(RuntimeError):
    """Raised when required API runtime configuration is missing."""


class ApiControlPlane:
    """REST-facing service for project/job control and snapshots."""

    def __init__(
        self,
        *,
        repository: JobRepository,
        workspace: WorkspaceStore,
        event_bus: EventBus,
        control_dispatcher: (
            Callable[[str, str, ControlCommandType], dict[str, str | bool]] | None
        ) = None,
    ) -> None:
        self._repository = repository
        self._workspace = workspace
        self._event_bus = event_bus
        self._uses_default_control_dispatcher = control_dispatcher is None
        self._control_dispatcher = control_dispatcher or self._default_control_dispatcher
        self._subscriptions: dict[str, EventSubscription] = {}
        self._latest_progress: dict[str, float] = {}
        self._latest_stage: dict[str, str | None] = {}
        self._latest_logs: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=MAX_LOG_BUFFER))
        self._project_locks_guard = threading.Lock()
        self._project_locks: dict[str, threading.RLock] = {}
        self._project_delete_lock = threading.Lock()
        self._deleting_projects: set[str] = set()
        self._pending_job_delete_cache_lock = threading.Lock()
        self._pending_job_deletes_cache: set[str] = set()
        self._hydrate_pending_job_delete_cache()
        self._validate_app_secret_or_raise()
        self._initialize_settings_from_env_once()
        self._reconcile_pending_job_deletes()

    def create_project(self, payload: ProjectCreateRequest) -> str:
        """Create one project and its workspace."""

        project_id = f"p_{uuid.uuid4().hex[:12]}"
        self._repository.upsert_project(
            project_id, title=payload.title, status=JobStatus.QUEUED.value
        )
        self._workspace.ensure_project_layout(project_id)
        return project_id

    def stage_local_upload(
        self,
        project_id: str,
        *,
        filename: str | None,
        source: BinaryIO,
    ) -> Path:
        """Persist an upload inside the project workspace before queueing a job."""

        if self._repository.get_project(project_id) is None:
            raise KeyError(f"project not found: {project_id}")
        project_root = self._workspace.ensure_project_layout(project_id)
        upload_root = project_root / "uploads"
        upload_root.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename or "upload.mp4").name
        suffix = Path(safe_name).suffix.lower()
        if not suffix or len(suffix) > 16 or not suffix[1:].isalnum():
            suffix = ".bin"
        upload_path: Path = upload_root / f"upload_{uuid.uuid4().hex}{suffix}"
        temporary_path = upload_path.with_suffix(f"{upload_path.suffix}.tmp")
        try:
            with temporary_path.open("wb") as handle:
                shutil.copyfileobj(source, handle)
            if temporary_path.stat().st_size <= 0:
                raise ApiError(
                    code="upload_empty",
                    message="uploaded video is empty",
                    status_code=400,
                )
            os.replace(temporary_path, upload_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return upload_path

    def discard_local_upload(self, project_id: str, upload_path: Path) -> None:
        """Remove one unqueued staged upload without escaping the project workspace."""

        upload_root = (self._workspace.project_root(project_id) / "uploads").resolve()
        resolved = upload_path.resolve()
        try:
            resolved.relative_to(upload_root)
        except ValueError:
            return
        resolved.unlink(missing_ok=True)

    def get_project(self, project_id: str) -> dict[str, str | None] | None:
        """Get one project by id."""

        project = self._repository.get_project(project_id)
        if project is None:
            return None
        return {
            "project_id": project.project_id,
            "title": project.title,
            "status": project.status,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
        }

    def list_projects(self) -> list[dict[str, str | None]]:
        """List persisted projects in repository-defined order."""

        return [
            {
                "project_id": project.project_id,
                "title": project.title,
                "status": project.status,
                "created_at": project.created_at,
                "updated_at": project.updated_at,
            }
            for project in self._repository.list_projects()
        ]

    def delete_project(
        self, project_id: str, *, force_cancel_active: bool = False
    ) -> dict[str, object]:
        """Delete one project and its job workspaces."""

        project_lock = self._get_project_lock(project_id)
        with project_lock:
            with self._project_delete_lock:
                if project_id in self._deleting_projects:
                    raise ApiError(
                        code="project_delete_in_progress",
                        message="project deletion already in progress",
                        status_code=409,
                    )
                self._deleting_projects.add(project_id)

            try:
                project = self._repository.get_project(project_id)
                if project is None:
                    raise KeyError(f"project not found: {project_id}")

                jobs = self._repository.list_jobs_for_project(project_id)
                active_job_ids = self._pending_project_job_ids(project_id, jobs)

                if active_job_ids and not force_cancel_active:
                    raise ApiError(
                        code="project_has_active_jobs",
                        message="project has active jobs",
                        status_code=409,
                        details={"active_job_ids": active_job_ids},
                    )

                cancelled_job_ids: list[str] = []
                if active_job_ids and force_cancel_active:
                    cancellable_statuses = {
                        JobStatus.QUEUED.value,
                        JobStatus.RUNNING.value,
                        JobStatus.PAUSED.value,
                        JobStatus.INTERRUPTED.value,
                    }
                    for job in jobs:
                        if job.job_id not in active_job_ids:
                            continue
                        if job.status not in cancellable_statuses:
                            continue
                        self.dispatch_control_command(
                            job_id=job.job_id,
                            command=ControlCommandType.CANCEL,
                        )
                        cancelled_job_ids.append(job.job_id)

                    pending = self._wait_for_project_jobs_to_finish(project_id)
                    if pending:
                        raise ApiError(
                            code="project_delete_pending_cancel",
                            message="project deletion is waiting for job cancellation",
                            status_code=409,
                            details={
                                "pending_job_ids": pending,
                                "retry_after_seconds": 2,
                            },
                        )

                for job in jobs:
                    self._clear_job_tracking(job.job_id)
                    self._clear_job_delete_pending(job.job_id)

                project_root = self._workspace.project_root(project_id)
                if project_root.exists():
                    try:
                        shutil.rmtree(project_root)
                    except OSError as exc:
                        raise ApiError(
                            code="project_delete_pending_cleanup",
                            message="project workspace is still busy",
                            status_code=409,
                            details={
                                "project_id": project_id,
                                "workspace_path": str(project_root),
                                "error": str(exc),
                                "pending_job_ids": self._pending_project_job_ids(project_id),
                                "retry_after_seconds": 2,
                            },
                        ) from exc

                self._repository.delete_project(project_id)

                return {
                    "deleted": True,
                    "cancelled_job_ids": cancelled_job_ids,
                }
            finally:
                with self._project_delete_lock:
                    self._deleting_projects.discard(project_id)

    def get_system_settings(self) -> SystemSettingsResponse:
        settings = self._current_settings()
        return SystemSettingsResponse(
            asr_provider=str(settings[SETTING_ASR_PROVIDER]),
            asr_endpoint=str(settings[SETTING_ASR_ENDPOINT]),
            asr_language=str(settings[SETTING_ASR_LANGUAGE]),
            asr_context=str(settings[SETTING_ASR_CONTEXT]),
            asr_timeout_seconds=int(str(settings[SETTING_ASR_TIMEOUT_SECONDS])),
            asr_token_configured=self._provider_secret_configured(PROVIDER_SECRET_ASR_TOKEN),
            vlm_base_url=str(settings[SETTING_VLM_BASE_URL]),
            vlm_model=str(settings[SETTING_VLM_MODEL]),
            vlm_frame_prompt_zh=str(settings[SETTING_VLM_FRAME_PROMPT_ZH]),
            vlm_frame_prompt_en=str(settings[SETTING_VLM_FRAME_PROMPT_EN]),
            vlm_concurrency=int(str(settings[SETTING_VLM_CONCURRENCY])),
            vlm_rpm=int(str(settings[SETTING_VLM_RPM])),
            vlm_api_key_configured=self._provider_secret_configured(
                PROVIDER_SECRET_VLM_API_KEY
            ),
            vlm_frame_prompt_zh_default=_DEFAULT_VLM_PROMPT_ZH,
            vlm_frame_prompt_en_default=_DEFAULT_VLM_PROMPT_EN,
            summary_base_url=str(settings[SETTING_SUMMARY_BASE_URL]),
            summary_model=str(settings[SETTING_SUMMARY_MODEL]),
            summary_prompt_zh=str(settings[SETTING_SUMMARY_PROMPT_ZH]),
            summary_prompt_en=str(settings[SETTING_SUMMARY_PROMPT_EN]),
            summary_max_input_chars=int(str(settings[SETTING_SUMMARY_MAX_INPUT_CHARS])),
            summary_api_key_configured=self._provider_secret_configured(
                PROVIDER_SECRET_SUMMARY_API_KEY
            ),
            summary_prompt_zh_default=_DEFAULT_SUMMARY_PROMPT_ZH,
            summary_prompt_en_default=_DEFAULT_SUMMARY_PROMPT_EN,
        )

    def patch_system_settings(
        self, payload: SystemSettingsPatchRequest
    ) -> SystemSettingsResponse:
        current = self._current_settings()
        next_asr_token = self._validate_provider_secret_patch(
            payload.asr_token, payload.clear_asr_token, field_name="asr_token"
        )
        next_vlm_api_key = self._validate_provider_secret_patch(
            payload.vlm_api_key, payload.clear_vlm_api_key, field_name="vlm_api_key"
        )
        next_summary_api_key = self._validate_provider_secret_patch(
            payload.summary_api_key,
            payload.clear_summary_api_key,
            field_name="summary_api_key",
        )
        next_asr_provider = (
            payload.asr_provider.strip().lower()
            if payload.asr_provider is not None
            else str(current[SETTING_ASR_PROVIDER])
        ) or _DEFAULT_ASR_PROVIDER
        if next_asr_provider not in {"unconfigured", "capswriter"}:
            raise ApiError(
                code="asr_provider_invalid",
                message=f"unsupported ASR provider: {next_asr_provider}",
                status_code=422,
            )
        next_asr_endpoint = (
            payload.asr_endpoint.strip()
            if payload.asr_endpoint is not None
            else str(current[SETTING_ASR_ENDPOINT])
        )
        if next_asr_provider == "capswriter" and not next_asr_endpoint:
            raise ApiError(
                code="asr_endpoint_required",
                message="CapsWriter endpoint is required",
                status_code=422,
            )
        next_asr_language = (
            payload.asr_language.strip()
            if payload.asr_language is not None
            else str(current[SETTING_ASR_LANGUAGE])
        ) or _DEFAULT_ASR_LANGUAGE
        next_asr_context = (
            payload.asr_context
            if payload.asr_context is not None
            else str(current[SETTING_ASR_CONTEXT])
        )[:2000]
        next_asr_timeout_seconds = max(
            1,
            payload.asr_timeout_seconds
            if payload.asr_timeout_seconds is not None
            else int(str(current[SETTING_ASR_TIMEOUT_SECONDS])),
        )
        next_vlm_base_url = (
            payload.vlm_base_url.strip()
            if payload.vlm_base_url is not None
            else str(current[SETTING_VLM_BASE_URL])
        ) or _DEFAULT_VLM_BASE_URL
        next_vlm_model = (
            payload.vlm_model.strip()
            if payload.vlm_model is not None
            else str(current[SETTING_VLM_MODEL])
        ) or _DEFAULT_VLM_MODEL
        next_prompt_zh = (
            payload.vlm_frame_prompt_zh
            if payload.vlm_frame_prompt_zh is not None
            else str(current[SETTING_VLM_FRAME_PROMPT_ZH])
        ) or _DEFAULT_VLM_PROMPT_ZH
        next_prompt_en = (
            payload.vlm_frame_prompt_en
            if payload.vlm_frame_prompt_en is not None
            else str(current[SETTING_VLM_FRAME_PROMPT_EN])
        ) or _DEFAULT_VLM_PROMPT_EN
        next_concurrency = max(
            1,
            payload.vlm_concurrency
            if payload.vlm_concurrency is not None
            else int(str(current[SETTING_VLM_CONCURRENCY]))
        )
        next_rpm = max(
            0,
            payload.vlm_rpm
            if payload.vlm_rpm is not None
            else int(str(current[SETTING_VLM_RPM]))
        )
        next_summary_base_url = (
            payload.summary_base_url.strip()
            if payload.summary_base_url is not None
            else str(current[SETTING_SUMMARY_BASE_URL])
        ) or _DEFAULT_SUMMARY_BASE_URL
        next_summary_model = (
            payload.summary_model.strip()
            if payload.summary_model is not None
            else str(current[SETTING_SUMMARY_MODEL])
        ) or _DEFAULT_SUMMARY_MODEL
        next_summary_prompt_zh = (
            payload.summary_prompt_zh
            if payload.summary_prompt_zh is not None
            else str(current[SETTING_SUMMARY_PROMPT_ZH])
        ) or _DEFAULT_SUMMARY_PROMPT_ZH
        next_summary_prompt_en = (
            payload.summary_prompt_en
            if payload.summary_prompt_en is not None
            else str(current[SETTING_SUMMARY_PROMPT_EN])
        ) or _DEFAULT_SUMMARY_PROMPT_EN
        next_summary_max_input_chars = max(
            1_000,
            payload.summary_max_input_chars
            if payload.summary_max_input_chars is not None
            else int(str(current[SETTING_SUMMARY_MAX_INPUT_CHARS]))
        )

        self._repository.set_setting(SETTING_ASR_PROVIDER, json.dumps(next_asr_provider))
        self._repository.set_setting(SETTING_ASR_ENDPOINT, json.dumps(next_asr_endpoint))
        self._repository.set_setting(SETTING_ASR_LANGUAGE, json.dumps(next_asr_language))
        self._repository.set_setting(SETTING_ASR_CONTEXT, json.dumps(next_asr_context))
        self._repository.set_setting(
            SETTING_ASR_TIMEOUT_SECONDS,
            json.dumps(next_asr_timeout_seconds),
        )
        self._repository.set_setting(SETTING_VLM_BASE_URL, json.dumps(next_vlm_base_url))
        self._repository.set_setting(SETTING_VLM_MODEL, json.dumps(next_vlm_model))
        self._repository.set_setting(SETTING_VLM_FRAME_PROMPT_ZH, json.dumps(next_prompt_zh))
        self._repository.set_setting(SETTING_VLM_FRAME_PROMPT_EN, json.dumps(next_prompt_en))
        self._repository.set_setting(SETTING_VLM_CONCURRENCY, json.dumps(next_concurrency))
        self._repository.set_setting(SETTING_VLM_RPM, json.dumps(next_rpm))
        self._repository.set_setting(
            SETTING_SUMMARY_BASE_URL, json.dumps(next_summary_base_url)
        )
        self._repository.set_setting(SETTING_SUMMARY_MODEL, json.dumps(next_summary_model))
        self._repository.set_setting(
            SETTING_SUMMARY_PROMPT_ZH, json.dumps(next_summary_prompt_zh)
        )
        self._repository.set_setting(
            SETTING_SUMMARY_PROMPT_EN, json.dumps(next_summary_prompt_en)
        )
        self._repository.set_setting(
            SETTING_SUMMARY_MAX_INPUT_CHARS,
            json.dumps(next_summary_max_input_chars),
        )
        self._persist_provider_secret_patch(
            kind=PROVIDER_SECRET_ASR_TOKEN,
            value=next_asr_token,
            clear=payload.clear_asr_token is True,
        )
        self._persist_provider_secret_patch(
            kind=PROVIDER_SECRET_VLM_API_KEY,
            value=next_vlm_api_key,
            clear=payload.clear_vlm_api_key is True,
        )
        self._persist_provider_secret_patch(
            kind=PROVIDER_SECRET_SUMMARY_API_KEY,
            value=next_summary_api_key,
            clear=payload.clear_summary_api_key is True,
        )
        self._append_operation_log(event="settings.patch", outcome="accepted")
        return SystemSettingsResponse(
            asr_provider=next_asr_provider,
            asr_endpoint=next_asr_endpoint,
            asr_language=next_asr_language,
            asr_context=next_asr_context,
            asr_timeout_seconds=next_asr_timeout_seconds,
            asr_token_configured=self._provider_secret_configured(PROVIDER_SECRET_ASR_TOKEN),
            vlm_base_url=next_vlm_base_url,
            vlm_model=next_vlm_model,
            vlm_frame_prompt_zh=next_prompt_zh,
            vlm_frame_prompt_en=next_prompt_en,
            vlm_concurrency=next_concurrency,
            vlm_rpm=next_rpm,
            vlm_api_key_configured=self._provider_secret_configured(
                PROVIDER_SECRET_VLM_API_KEY
            ),
            vlm_frame_prompt_zh_default=_DEFAULT_VLM_PROMPT_ZH,
            vlm_frame_prompt_en_default=_DEFAULT_VLM_PROMPT_EN,
            summary_base_url=next_summary_base_url,
            summary_model=next_summary_model,
            summary_prompt_zh=next_summary_prompt_zh,
            summary_prompt_en=next_summary_prompt_en,
            summary_max_input_chars=next_summary_max_input_chars,
            summary_api_key_configured=self._provider_secret_configured(
                PROVIDER_SECRET_SUMMARY_API_KEY
            ),
            summary_prompt_zh_default=_DEFAULT_SUMMARY_PROMPT_ZH,
            summary_prompt_en_default=_DEFAULT_SUMMARY_PROMPT_EN,
        )

    def create_cookie(self, payload: CookieCreateRequest) -> CookieListItem:
        """Create one encrypted cookie entry for the local installation."""

        user_id = LOCAL_COOKIE_OWNER_ID
        if payload.is_default:
            self._repository.clear_default_cookie_for_user(user_id)

        cookie_id = f"c_{uuid.uuid4().hex[:12]}"
        self._repository.create_user_cookie(
            cookie_id=cookie_id,
            user_id=user_id,
            name=payload.name,
            cookie_encrypted=self._encrypt_cookie(payload.cookie_netscape_text),
            is_default=payload.is_default,
            status="unknown",
        )
        created = self._repository.get_user_cookie(cookie_id, user_id)
        if created is None:
            raise RuntimeError("failed to persist cookie")
        return self._to_cookie_list_item(created)

    def list_cookies(self) -> list[CookieListItem]:
        """List cookie metadata for the local installation."""

        return [
            self._to_cookie_list_item(row)
            for row in self._repository.list_user_cookies(LOCAL_COOKIE_OWNER_ID)
        ]

    def patch_cookie(self, cookie_id: str, payload: CookiePatchRequest) -> CookieListItem:
        """Patch mutable cookie metadata/content without exposing plaintext."""

        _ = self._require_cookie(cookie_id)
        if payload.is_default:
            self._repository.clear_default_cookie_for_user(LOCAL_COOKIE_OWNER_ID)

        self._repository.update_user_cookie(
            cookie_id=cookie_id,
            user_id=LOCAL_COOKIE_OWNER_ID,
            name=payload.name,
            cookie_encrypted=(
                self._encrypt_cookie(payload.cookie_netscape_text)
                if payload.cookie_netscape_text is not None
                else None
            ),
            is_default=payload.is_default,
            status="unknown" if payload.cookie_netscape_text is not None else None,
            last_validated_at=(None if payload.cookie_netscape_text is not None else None),
            last_error_code=(None if payload.cookie_netscape_text is not None else None),
            set_last_validated_at=payload.cookie_netscape_text is not None,
            set_last_error_code=payload.cookie_netscape_text is not None,
        )
        updated = self._require_cookie(cookie_id)
        return self._to_cookie_list_item(updated)

    def delete_cookie(self, cookie_id: str) -> None:
        """Delete one cookie entry in the local installation."""

        _ = self._require_cookie(cookie_id)
        self._repository.delete_user_cookie(cookie_id, LOCAL_COOKIE_OWNER_ID)

    def validate_cookie(
        self, cookie_id: str, payload: CookieValidateRequest
    ) -> CookieValidateResponse:
        """Validate cookie by probing ingest URL using decrypted Netscape text."""

        current = self._require_cookie(cookie_id)
        ts = utc_now_iso()
        status = "valid"
        error_code: str | None = None

        try:
            cookie_text = self._decrypt_cookie(current.cookie_encrypted)
        except ApiConfigError:
            status = "invalid"
            error_code = "cookie_decrypt_failed"
            self._repository.update_user_cookie(
                cookie_id=cookie_id,
                user_id=LOCAL_COOKIE_OWNER_ID,
                status=status,
                last_validated_at=ts,
                last_error_code=error_code,
                set_last_validated_at=True,
                set_last_error_code=True,
            )
            return CookieValidateResponse(
                id=cookie_id,
                status=status,
                last_validated_at=ts,
                last_error_code=error_code,
            )

        try:
            probe_url_formats(
                IngestRequest(
                    project_id="p_cookie_validate",
                    job_id="j_cookie_validate",
                    source_url=payload.source_url,
                    cookie_content=cookie_text,
                )
            )
        except IngestError as exc:
            status = "expired" if exc.code == INGEST_AUTH_REQUIRED else "invalid"
            error_code = exc.code

        self._repository.update_user_cookie(
            cookie_id=cookie_id,
            user_id=LOCAL_COOKIE_OWNER_ID,
            status=status,
            last_validated_at=ts,
            last_error_code=error_code,
            set_last_validated_at=True,
            set_last_error_code=True,
        )
        return CookieValidateResponse(
            id=cookie_id,
            status=status,
            last_validated_at=ts,
            last_error_code=error_code,
        )

    def _require_cookie(self, cookie_id: str) -> UserCookieRecord:
        row = self._repository.get_user_cookie(cookie_id, LOCAL_COOKIE_OWNER_ID)
        if row is None:
            raise KeyError(f"cookie not found: {cookie_id}")
        return row

    def _to_cookie_list_item(self, row: UserCookieRecord) -> CookieListItem:
        return CookieListItem(
            id=row.id,
            name=row.name,
            is_default=row.is_default,
            status=row.status,
            last_validated_at=row.last_validated_at,
            last_error_code=row.last_error_code,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _encrypt_cookie(self, cookie_text: str) -> str:
        try:
            return cast(str, encrypt_secret(cookie_text))
        except SecretCipherError as exc:
            raise ApiConfigError(str(exc)) from exc

    def _decrypt_cookie(self, cookie_encrypted: str) -> str:
        try:
            return cast(str, decrypt_secret(cookie_encrypted))
        except SecretCipherError as exc:
            raise ApiConfigError(str(exc)) from exc

    def _provider_secret_configured(self, kind: str) -> bool:
        return self._repository.get_active_provider_secret(kind) is not None

    def _active_provider_secret_ref(self, kind: str) -> str | None:
        record = self._repository.get_active_provider_secret(kind)
        return record.id if record is not None else None

    def _validate_provider_secret_patch(
        self,
        value: SecretStr | None,
        clear: bool | None,
        *,
        field_name: str,
    ) -> str | None:
        if value is not None and clear is True:
            raise ApiError(
                code="provider_secret_patch_conflict",
                message=f"{field_name} cannot be replaced and cleared in the same request",
                status_code=422,
            )
        if value is None:
            return None
        plaintext = value.get_secret_value().strip()
        if not plaintext:
            raise ApiError(
                code="provider_secret_empty",
                message=f"{field_name} cannot be empty",
                status_code=422,
            )
        return plaintext

    def _persist_provider_secret_patch(
        self, *, kind: str, value: str | None, clear: bool
    ) -> None:
        if value is not None:
            self._repository.create_provider_secret(
                secret_id=f"s_{uuid.uuid4().hex}",
                kind=kind,
                secret_encrypted=encrypt_secret(value),
            )
        elif clear:
            self._repository.clear_active_provider_secret(kind)

    def _validate_app_secret_or_raise(self) -> None:
        secret = os.getenv("APP_SECRET_KEY", "").strip()
        if not secret:
            raise ApiConfigError("APP_SECRET_KEY is required for API startup")
        if secret == "change-me-in-local-or-production":
            raise ApiConfigError("APP_SECRET_KEY must be changed from the example value")

    def _read_setting_str(self, key: str, *, default: str) -> str:
        raw = self._repository.get_setting(key)
        if raw is None:
            self._repository.set_setting(key, json.dumps(default))
            return default
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return default
        if isinstance(parsed, str):
            return parsed
        return default

    def _read_setting_int(self, key: str, *, default: int) -> int:
        raw = self._repository.get_setting(key)
        if raw is None:
            self._repository.set_setting(key, json.dumps(default))
            return default
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return default
        if isinstance(parsed, int) and not isinstance(parsed, bool):
            return parsed
        return default

    def _initialize_settings_from_env_once(self) -> None:
        _ = self._read_setting_str(
            SETTING_ASR_PROVIDER,
            default=os.getenv("VIDEOSIEVE_ASR_PROVIDER") or _DEFAULT_ASR_PROVIDER,
        )
        _ = self._read_setting_str(
            SETTING_ASR_ENDPOINT,
            default=os.getenv("VIDEOSIEVE_ASR_ENDPOINT") or _DEFAULT_ASR_ENDPOINT,
        )
        _ = self._read_setting_str(
            SETTING_ASR_LANGUAGE,
            default=os.getenv("VIDEOSIEVE_ASR_LANGUAGE") or _DEFAULT_ASR_LANGUAGE,
        )
        _ = self._read_setting_str(
            SETTING_ASR_CONTEXT,
            default=os.getenv("VIDEOSIEVE_ASR_CONTEXT") or _DEFAULT_ASR_CONTEXT,
        )
        asr_timeout_raw = os.getenv("VIDEOSIEVE_ASR_TIMEOUT_SECONDS", "")
        try:
            asr_timeout_default = max(1, int(asr_timeout_raw))
        except ValueError:
            asr_timeout_default = _DEFAULT_ASR_TIMEOUT_SECONDS
        _ = self._read_setting_int(
            SETTING_ASR_TIMEOUT_SECONDS,
            default=asr_timeout_default,
        )
        _ = self._read_setting_str(
            SETTING_VLM_BASE_URL,
            default=os.getenv("QWEN_BASE_URL") or _DEFAULT_VLM_BASE_URL,
        )
        _ = self._read_setting_str(
            SETTING_VLM_MODEL,
            default=os.getenv("VLM_MODEL") or _DEFAULT_VLM_MODEL,
        )
        _ = self._read_setting_str(SETTING_VLM_FRAME_PROMPT_ZH, default=_DEFAULT_VLM_PROMPT_ZH)
        _ = self._read_setting_str(SETTING_VLM_FRAME_PROMPT_EN, default=_DEFAULT_VLM_PROMPT_EN)
        _ = self._read_setting_int(SETTING_VLM_CONCURRENCY, default=_DEFAULT_VLM_CONCURRENCY)
        _ = self._read_setting_int(SETTING_VLM_RPM, default=_DEFAULT_VLM_RPM)
        _ = self._read_setting_str(
            SETTING_SUMMARY_BASE_URL,
            default=os.getenv("SUMMARY_BASE_URL") or _DEFAULT_SUMMARY_BASE_URL,
        )
        _ = self._read_setting_str(
            SETTING_SUMMARY_MODEL,
            default=os.getenv("SUMMARY_MODEL") or _DEFAULT_SUMMARY_MODEL,
        )
        _ = self._read_setting_str(
            SETTING_SUMMARY_PROMPT_ZH, default=_DEFAULT_SUMMARY_PROMPT_ZH
        )
        _ = self._read_setting_str(
            SETTING_SUMMARY_PROMPT_EN, default=_DEFAULT_SUMMARY_PROMPT_EN
        )
        _ = self._read_setting_int(
            SETTING_SUMMARY_MAX_INPUT_CHARS,
            default=_DEFAULT_SUMMARY_MAX_INPUT_CHARS,
        )

    def _current_settings(self) -> dict[str, object]:
        return {
            SETTING_VLM_BASE_URL: self._read_setting_str(
                SETTING_VLM_BASE_URL,
                default=os.getenv("QWEN_BASE_URL") or _DEFAULT_VLM_BASE_URL,
            ),
            SETTING_VLM_MODEL: self._read_setting_str(
                SETTING_VLM_MODEL,
                default=os.getenv("VLM_MODEL") or _DEFAULT_VLM_MODEL,
            ),
            SETTING_VLM_FRAME_PROMPT_ZH: self._read_setting_str(
                SETTING_VLM_FRAME_PROMPT_ZH, default=_DEFAULT_VLM_PROMPT_ZH
            ),
            SETTING_VLM_FRAME_PROMPT_EN: self._read_setting_str(
                SETTING_VLM_FRAME_PROMPT_EN, default=_DEFAULT_VLM_PROMPT_EN
            ),
            SETTING_VLM_CONCURRENCY: self._read_setting_int(
                SETTING_VLM_CONCURRENCY, default=_DEFAULT_VLM_CONCURRENCY
            ),
            SETTING_VLM_RPM: self._read_setting_int(
                SETTING_VLM_RPM, default=_DEFAULT_VLM_RPM
            ),
            SETTING_ASR_PROVIDER: self._read_setting_str(
                SETTING_ASR_PROVIDER,
                default=os.getenv("VIDEOSIEVE_ASR_PROVIDER") or _DEFAULT_ASR_PROVIDER,
            ),
            SETTING_ASR_ENDPOINT: self._read_setting_str(
                SETTING_ASR_ENDPOINT,
                default=os.getenv("VIDEOSIEVE_ASR_ENDPOINT") or _DEFAULT_ASR_ENDPOINT,
            ),
            SETTING_ASR_LANGUAGE: self._read_setting_str(
                SETTING_ASR_LANGUAGE,
                default=os.getenv("VIDEOSIEVE_ASR_LANGUAGE") or _DEFAULT_ASR_LANGUAGE,
            ),
            SETTING_ASR_CONTEXT: self._read_setting_str(
                SETTING_ASR_CONTEXT,
                default=os.getenv("VIDEOSIEVE_ASR_CONTEXT") or _DEFAULT_ASR_CONTEXT,
            ),
            SETTING_ASR_TIMEOUT_SECONDS: self._read_setting_int(
                SETTING_ASR_TIMEOUT_SECONDS,
                default=_DEFAULT_ASR_TIMEOUT_SECONDS,
            ),
            SETTING_SUMMARY_BASE_URL: self._read_setting_str(
                SETTING_SUMMARY_BASE_URL,
                default=os.getenv("SUMMARY_BASE_URL") or _DEFAULT_SUMMARY_BASE_URL,
            ),
            SETTING_SUMMARY_MODEL: self._read_setting_str(
                SETTING_SUMMARY_MODEL,
                default=os.getenv("SUMMARY_MODEL") or _DEFAULT_SUMMARY_MODEL,
            ),
            SETTING_SUMMARY_PROMPT_ZH: self._read_setting_str(
                SETTING_SUMMARY_PROMPT_ZH, default=_DEFAULT_SUMMARY_PROMPT_ZH
            ),
            SETTING_SUMMARY_PROMPT_EN: self._read_setting_str(
                SETTING_SUMMARY_PROMPT_EN, default=_DEFAULT_SUMMARY_PROMPT_EN
            ),
            SETTING_SUMMARY_MAX_INPUT_CHARS: self._read_setting_int(
                SETTING_SUMMARY_MAX_INPUT_CHARS,
                default=_DEFAULT_SUMMARY_MAX_INPUT_CHARS,
            ),
        }

    def _append_operation_log(
        self,
        *,
        event: str,
        outcome: str,
        code: str | None = None,
        detail: str | None = None,
    ) -> None:
        self._repository.append_operation_log(
            log_id=f"log_{uuid.uuid4().hex[:12]}",
            actor_type="local",
            actor_id=LOCAL_ACTOR_ID,
            action=event,
            status=outcome,
            reason_code=code,
            created_at=utc_now_iso(),
            meta_json=json.dumps({"detail": detail}, ensure_ascii=True),
        )

    def create_job(self, payload: JobCreateRequest) -> str:
        """Create one queued job under one project."""

        project_lock = self._get_project_lock(payload.project_id)
        with project_lock:
            project = self._repository.get_project(payload.project_id)
            if project is None:
                raise KeyError(f"project not found: {payload.project_id}")

            with self._project_delete_lock:
                if payload.project_id in self._deleting_projects:
                    raise ApiError(
                        code="project_delete_in_progress",
                        message="project deletion already in progress",
                        status_code=409,
                    )

            local_video_path = self._validate_local_video_path(
                payload.project_id,
                payload.local_video_path,
            )

            job_id = f"j_{uuid.uuid4().hex[:12]}"
            self._workspace.ensure_job_layout(payload.project_id, job_id)
            config_path = self._workspace.config_snapshot_file(payload.project_id, job_id)

            config: dict[str, object] = {
                "schema_version": "1.0",
                "project_id": payload.project_id,
                "job_id": job_id,
            }
            runtime_settings = self._current_settings()
            config["asr"] = {
                "provider": runtime_settings[SETTING_ASR_PROVIDER],
                "transport": "websocket",
                "endpoint": runtime_settings[SETTING_ASR_ENDPOINT],
                "language": runtime_settings[SETTING_ASR_LANGUAGE],
                "context": runtime_settings[SETTING_ASR_CONTEXT],
                "timeout_seconds": runtime_settings[SETTING_ASR_TIMEOUT_SECONDS],
                "credential_ref": self._active_provider_secret_ref(
                    PROVIDER_SECRET_ASR_TOKEN
                ),
                "segment_seconds": 60.0,
                "overlap_seconds": 4.0,
            }
            config["frame_summary"] = {
                "base_url": runtime_settings[SETTING_VLM_BASE_URL],
                "model": runtime_settings[SETTING_VLM_MODEL],
                "prompt_zh": runtime_settings[SETTING_VLM_FRAME_PROMPT_ZH],
                "prompt_en": runtime_settings[SETTING_VLM_FRAME_PROMPT_EN],
                "concurrency": runtime_settings[SETTING_VLM_CONCURRENCY],
                "rpm": runtime_settings[SETTING_VLM_RPM],
                "credential_ref": self._active_provider_secret_ref(
                    PROVIDER_SECRET_VLM_API_KEY
                ),
            }
            config["overall_summary"] = {
                "base_url": runtime_settings[SETTING_SUMMARY_BASE_URL],
                "model": runtime_settings[SETTING_SUMMARY_MODEL],
                "prompt_zh": runtime_settings[SETTING_SUMMARY_PROMPT_ZH],
                "prompt_en": runtime_settings[SETTING_SUMMARY_PROMPT_EN],
                "max_input_chars": runtime_settings[SETTING_SUMMARY_MAX_INPUT_CHARS],
                "credential_ref": self._active_provider_secret_ref(
                    PROVIDER_SECRET_SUMMARY_API_KEY
                ),
            }
            if payload.summary_enabled is not None:
                config["summary_enabled"] = payload.summary_enabled
            if payload.ingest:
                normalized_ingest, dedupe_estimate = self._normalize_ingest(payload.ingest)
                config["ingest"] = normalized_ingest
                config["dedupe_applied_estimate"] = dedupe_estimate
            if local_video_path is not None:
                config["local_video_path"] = str(local_video_path)
            if payload.local_video_context:
                config["local_video_context"] = payload.local_video_context

            config_path.write_text(
                json.dumps(
                    config,
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )
            # Queue visibility is the commit point: the independent worker must
            # never claim a job before its immutable configuration exists.
            self._repository.create_job(
                job_id, payload.project_id, status=JobStatus.QUEUED.value, stage=None
            )
            self._append_operation_log(
                event="job.submit",
                outcome="accepted",
                detail=f"job_id={job_id}",
            )

        return job_id

    def _validate_local_video_path(
        self, project_id: str, raw_path: str | None
    ) -> Path | None:
        if raw_path is None:
            return None
        upload_root = (self._workspace.project_root(project_id) / "uploads").resolve()
        candidate = Path(raw_path).resolve()
        if not candidate.is_relative_to(upload_root) or not candidate.is_file():
            raise ApiError(
                code="local_upload_invalid",
                message="local video must be a staged upload for this project",
                status_code=400,
            )
        return candidate

    def _get_project_lock(self, project_id: str) -> threading.RLock:
        # Keep locks cached per project in single-process mode.
        # We intentionally avoid lock eviction to prevent split-lock races.
        with self._project_locks_guard:
            lock = self._project_locks.get(project_id)
            if lock is None:
                lock = threading.RLock()
                self._project_locks[project_id] = lock
            return lock

    def _normalize_ingest(self, ingest: IngestParams) -> tuple[dict[str, object], bool]:
        analysis_asset = ingest.analysis_asset
        quality_asset = ingest.quality_asset

        if analysis_asset is None and quality_asset is None and ingest.video_format_id is not None:
            legacy = IngestAssetSelection(
                video_format_id=ingest.video_format_id,
                audio_format_id=ingest.audio_format_id,
            )
            analysis_asset = legacy
            quality_asset = legacy

        if analysis_asset is None and quality_asset is not None:
            analysis_asset = quality_asset
        if quality_asset is None and analysis_asset is not None:
            quality_asset = analysis_asset

        normalized: dict[str, object] = {}
        if ingest.source_url is not None:
            normalized["source_url"] = ingest.source_url
        if ingest.cookie_id is not None:
            normalized["cookie_id"] = ingest.cookie_id
        elif ingest.cookie_file_path is not None:
            normalized["cookie_file_path"] = ingest.cookie_file_path
            normalized["cookie_file_path_deprecated"] = True
        if ingest.cookie_secret_ref is not None:
            normalized["cookie_secret_ref"] = ingest.cookie_secret_ref
        if analysis_asset is not None:
            normalized["analysis_asset"] = analysis_asset.model_dump(mode="json", exclude_none=True)
        if quality_asset is not None:
            normalized["quality_asset"] = quality_asset.model_dump(mode="json", exclude_none=True)

        analysis_pair = (
            analysis_asset.video_format_id if analysis_asset is not None else None,
            analysis_asset.audio_format_id if analysis_asset is not None else None,
        )
        quality_pair = (
            quality_asset.video_format_id if quality_asset is not None else None,
            quality_asset.audio_format_id if quality_asset is not None else None,
        )
        return normalized, analysis_pair == quality_pair

    def probe_ingest_formats(self, payload: IngestProbeRequest) -> IngestProbeResponse:
        """Probe URL and return selectable quality options for frontend."""

        cookie_content: str | None = None
        cookie_file_path: str | None = payload.cookie_file_path
        if payload.cookie_id is not None:
            cookie_row = self._require_cookie(payload.cookie_id)
            cookie_content = self._decrypt_cookie(cookie_row.cookie_encrypted)
            cookie_file_path = None

        request = IngestRequest(
            project_id="p_probe",
            job_id="j_probe",
            source_url=payload.source_url,
            cookie_content=cookie_content,
            cookie_file_path=cookie_file_path,
        )
        result = probe_url_formats(request)
        return IngestProbeResponse(
            source_url=result.source_url,
            title=result.title,
            uploader=result.uploader,
            duration_seconds=result.duration_seconds,
            webpage_url=result.webpage_url,
            formats=[IngestFormatItem.model_validate(item.model_dump()) for item in result.formats],
        )

    def get_job(self, job_id: str) -> dict[str, str | None] | None:
        """Get one job by id."""

        job = self._repository.get_job(job_id)
        if job is None:
            return None
        return {
            "job_id": job.job_id,
            "project_id": job.project_id,
            "status": job.status,
            "stage": job.stage,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }

    def list_jobs_for_project(self, project_id: str) -> list[dict[str, str | None]]:
        """List jobs under one project."""

        jobs = self._repository.list_jobs_for_project(project_id)
        return [
            {
                "job_id": job.job_id,
                "project_id": job.project_id,
                "status": job.status,
                "stage": job.stage,
                "error_code": job.error_code,
                "error_message": job.error_message,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
            }
            for job in jobs
        ]

    def ensure_job_tracking(self, job_id: str) -> None:
        """Subscribe once to job event channel and maintain cache."""

        if job_id in self._subscriptions:
            return

        def _handler(event: InfraEvent) -> None:
            self._consume_event(event)

        self._subscriptions[job_id] = self._event_bus.subscribe(f"jobs:{job_id}", _handler)

    def release_job_tracking(self, job_id: str) -> None:
        """Drop one job subscription."""

        subscription = self._subscriptions.pop(job_id, None)
        if subscription is not None:
            subscription.unsubscribe()

    def list_artifacts(self, project_id: str, job_id: str) -> list[ArtifactItem]:
        """List workspace artifacts for one job."""

        root = self._workspace.job_root(project_id, job_id)
        if not root.exists():
            return []
        ready_deliverables = self._ready_deliverable_paths(project_id, job_id)

        items: list[ArtifactItem] = []
        for path in sorted(
            (
                item
                for item in root.rglob("*")
                if item.is_file() and not item.name.endswith(".tmp")
            ),
            key=lambda p: p.as_posix(),
        ):
            relative = path.relative_to(root).as_posix()
            if relative.startswith("outputs/") and relative not in ready_deliverables:
                continue
            items.append(ArtifactItem(path=relative, size_bytes=path.stat().st_size))
        return items

    def _ready_deliverable_paths(self, project_id: str, job_id: str) -> set[str]:
        root = self._workspace.job_root(project_id, job_id).resolve()
        manifest_path = self._workspace.deliverables_manifest_file(project_id, job_id)
        if not manifest_path.exists():
            return set()
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("ready") is not True
                or payload.get("project_id") != project_id
                or payload.get("job_id") != job_id
            ):
                return set()
            raw_artifacts = payload.get("artifacts")
            if not isinstance(raw_artifacts, list) or not raw_artifacts:
                return set()
            ready_paths: set[str] = set()
            for item in raw_artifacts:
                if not isinstance(item, dict):
                    return set()
                relative = item.get("path")
                size_bytes = item.get("size_bytes")
                expected_hash = item.get("sha256")
                if (
                    not isinstance(relative, str)
                    or not relative.startswith("outputs/")
                    or not isinstance(size_bytes, int)
                    or size_bytes < 0
                    or not isinstance(expected_hash, str)
                    or len(expected_hash) != 64
                ):
                    return set()
                candidate = (root / relative).resolve()
                if not candidate.is_relative_to(root) or not candidate.is_file():
                    return set()
                if candidate.stat().st_size != size_bytes:
                    return set()
                digest = sha256()
                with candidate.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != expected_hash:
                    return set()
                ready_paths.add(relative)
            ready_paths.add(manifest_path.relative_to(root).as_posix())
            return ready_paths
        except (OSError, ValueError, json.JSONDecodeError):
            return set()

    def get_job_snapshot(self, job_id: str) -> JobSnapshot:
        """Build one authoritative job snapshot for UI convergence."""

        job = self._repository.get_job(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")

        if job.delete_pending:
            with self._pending_job_delete_cache_lock:
                self._pending_job_deletes_cache.add(job_id)

        if self._is_job_delete_pending(job_id):
            self._try_finalize_pending_job_delete(job.project_id, job_id)
            job = self._repository.get_job(job_id)
            if job is None:
                raise KeyError(f"job not found: {job_id}")

        self.ensure_job_tracking(job_id)
        progress = self._coalesce_progress(job)
        stage = self._latest_stage.get(job_id) or job.stage
        # worker.log is primarily written by the pipeline orchestrator.
        # Control plane only appends dispatch-failure fallback lines.
        persisted_logs = self._read_worker_log_tail(job.project_id, job_id)
        memory_logs = list(self._latest_logs.get(job_id) or [])
        merged_logs = self._merge_logs_with_tail_overlap(persisted_logs, memory_logs)

        return JobSnapshot(
            project_id=job.project_id,
            job_id=job_id,
            state_version=job.state_version,
            status=job.status,
            current_stage=stage,
            requested_action=(
                job.control_command
                if job.control_version > job.control_ack_version
                else None
            ),
            control_phase=(
                "accepted"
                if job.control_version > job.control_ack_version
                else ("applied" if job.control_command is not None else None)
            ),
            control_request_id=job.control_request_id,
            attempt=job.attempt,
            progress=progress,
            error_code=job.error_code,
            error_message=job.error_message,
            latest_logs=list(merged_logs),
            artifacts=self.list_artifacts(job.project_id, job_id),
        )

    def dispatch_control_command(
        self,
        *,
        job_id: str,
        command: ControlCommandType,
        request_id: str | None = None,
    ) -> dict[str, str | bool]:
        """Dispatch one job-scoped control command."""

        job = self._repository.get_job(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
        if self._uses_default_control_dispatcher:
            return self._default_control_dispatcher(
                job.project_id,
                job_id,
                command,
                request_id=request_id,
            )
        return self._control_dispatcher(job.project_id, job_id, command)

    def _consume_event(self, event: InfraEvent) -> None:
        if event.event_type == "progress":
            pct = float(event.payload.get("pct", 0.0))
            self._latest_progress[event.job_id] = max(0.0, min(100.0, pct))
            stage = event.payload.get("stage")
            if isinstance(stage, str):
                self._latest_stage[event.job_id] = stage
            return

        if event.event_type == "stage_changed":
            stage = event.payload.get("to")
            if isinstance(stage, str):
                self._latest_stage[event.job_id] = stage
            return

        if event.event_type == "log":
            message = event.payload.get("message")
            level = event.payload.get("level")
            if isinstance(message, str):
                prefix = f"[{level}] " if isinstance(level, str) else ""
                self._latest_logs[event.job_id].append(f"{prefix}{message}")

        if self._is_job_delete_pending(event.job_id):
            self._try_finalize_pending_job_delete(event.project_id, event.job_id)

    def _clear_job_tracking(self, job_id: str) -> None:
        subscription = self._subscriptions.pop(job_id, None)
        if subscription is not None:
            subscription.unsubscribe()
        self._latest_progress.pop(job_id, None)
        self._latest_stage.pop(job_id, None)
        self._latest_logs.pop(job_id, None)

    def _wait_for_project_jobs_to_finish(self, project_id: str) -> list[str]:
        deadline = time.monotonic() + PROJECT_DELETE_WAIT_SECONDS
        while time.monotonic() < deadline:
            pending = self._pending_project_job_ids(project_id)
            if not pending:
                return []
            time.sleep(PROJECT_DELETE_POLL_SECONDS)

        return self._pending_project_job_ids(project_id)

    def _pending_project_job_ids(
        self,
        project_id: str,
        jobs: list[JobRecord] | None = None,
    ) -> list[str]:
        rows = jobs if jobs is not None else self._repository.list_jobs_for_project(project_id)
        pending_statuses = {
            JobStatus.QUEUED.value,
            JobStatus.RUNNING.value,
            JobStatus.PAUSED.value,
            JobStatus.INTERRUPTED.value,
        }
        return [
            job.job_id
            for job in rows
            if job.status in pending_statuses
        ]

    def _read_worker_log_tail(self, project_id: str, job_id: str) -> list[str]:
        log_file = self._workspace.worker_log_file(project_id, job_id)
        if not log_file.exists() or not log_file.is_file():
            return []
        tail: deque[str] = deque(maxlen=MAX_LOG_BUFFER)
        with log_file.open("r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.rstrip("\r\n")
                if line:
                    tail.append(line)
        return list(tail)

    def _merge_logs_with_tail_overlap(
        self, persisted_logs: list[str], memory_logs: list[str]
    ) -> list[str]:
        if not persisted_logs:
            return memory_logs[-MAX_LOG_BUFFER:]
        if not memory_logs:
            return persisted_logs[-MAX_LOG_BUFFER:]

        max_overlap = min(len(persisted_logs), len(memory_logs))
        overlap = 0
        for size in range(max_overlap, 0, -1):
            if persisted_logs[-size:] == memory_logs[:size]:
                overlap = size
                break

        merged = [*persisted_logs, *memory_logs[overlap:]]
        return merged[-MAX_LOG_BUFFER:]

    def _coalesce_progress(self, job: JobRecord) -> float:
        if job.status == JobStatus.SUCCEEDED.value:
            return 100.0
        live_progress = self._latest_progress.get(job.job_id, 0.0)
        return float(max(float(job.progress), live_progress))

    def _default_control_dispatcher(
        self,
        project_id: str,
        job_id: str,
        command: ControlCommandType,
        *,
        request_id: str | None = None,
    ) -> dict[str, str | bool]:
        current = self._repository.get_job(job_id)
        if current is None:
            raise KeyError(f"job not found: {job_id}")

        decision = evaluate_control_command(command, JobStatus(current.status))

        if not decision.accepted:
            return cast(
                dict[str, str | bool],
                ControlAckPayload(
                    command=command.value,
                    accepted=False,
                    reason=decision.reason,
                    code=decision.code,
                ).to_dict(),
            )

        if command is ControlCommandType.PAUSE and decision.request_pause:
            control_version = self._repository.request_job_control(
                job_id,
                ControlCommandType.PAUSE.value,
                request_id=request_id,
                expected_status=current.status,
                expected_state_version=current.state_version,
            )
            if control_version is None:
                return self._control_state_changed_ack(command)
            return cast(
                dict[str, str | bool],
                ControlAckPayload(
                    command=command.value,
                    accepted=True,
                    reason="pause requested; awaiting worker acknowledgement",
                ).to_dict(),
            )

        if command is ControlCommandType.RESUME and decision.target_status is not None:
            if JobStatus(current.status) is JobStatus.INTERRUPTED:
                recovered = self._repository.recover_interrupted_job(
                    job_id,
                    request_id=request_id,
                    expected_state_version=current.state_version,
                )
                if not recovered:
                    return self._control_state_changed_ack(command)
            else:
                control_version = self._repository.request_job_control(
                    job_id,
                    ControlCommandType.RESUME.value,
                    request_id=request_id,
                    expected_status=current.status,
                    expected_state_version=current.state_version,
                )
                if control_version is None:
                    return self._control_state_changed_ack(command)
            return cast(
                dict[str, str | bool],
                ControlAckPayload(
                    command=command.value,
                    accepted=True,
                    reason="resume requested; awaiting worker claim",
                ).to_dict(),
            )

        if decision.request_cancel:
            control_version = self._repository.request_job_control(
                job_id,
                ControlCommandType.CANCEL.value,
                request_id=request_id,
                expected_status=current.status,
                expected_state_version=current.state_version,
                finalize_cancel_if_unowned=True,
            )
            if control_version is None:
                return self._control_state_changed_ack(command)

        if command is ControlCommandType.DELETE:
            if self._job_worker_may_be_running(job_id):
                self._mark_job_delete_pending(job_id)
                return cast(
                    dict[str, str | bool],
                    ControlAckPayload(
                        command=command.value,
                        accepted=True,
                        code=DELETE_PENDING_CLEANUP,
                        reason="delete accepted, waiting for worker to stop before cleanup",
                    ).to_dict(),
                )

            latest = self._repository.get_job(job_id)
            if latest is None:
                self._clear_job_delete_pending(job_id)
                return cast(
                    dict[str, str | bool],
                    ControlAckPayload(
                        command=command.value,
                        accepted=True,
                        reason="job already deleted",
                    ).to_dict(),
                )
            latest_status = JobStatus(latest.status)
            if decision.request_cleanup or latest_status is JobStatus.CANCELLED:
                if not self._cleanup_job_workspace(project_id, job_id):
                    self._mark_job_delete_pending(job_id)
                    return cast(
                        dict[str, str | bool],
                        ControlAckPayload(
                            command=command.value,
                            accepted=True,
                            code=DELETE_PENDING_CLEANUP,
                            reason="delete accepted, waiting for file handles to release",
                        ).to_dict(),
                    )
                self._repository.delete_job(job_id)
                self._clear_job_tracking(job_id)
                self._clear_job_delete_pending(job_id)
                return cast(
                    dict[str, str | bool],
                    ControlAckPayload(
                        command=command.value,
                        accepted=True,
                        reason="job deleted",
                    ).to_dict(),
                )

        ack_payload: dict[str, str | bool] = ControlAckPayload(
            command=command.value,
            accepted=decision.accepted,
            reason=decision.reason,
            code=decision.code,
        ).to_dict()
        return ack_payload

    def _control_state_changed_ack(
        self, command: ControlCommandType
    ) -> dict[str, str | bool]:
        return cast(
            dict[str, str | bool],
            ControlAckPayload(
                command=command.value,
                accepted=False,
                code="job_state_changed",
                reason="job state changed while applying control; refresh and retry",
            ).to_dict(),
        )

    def _job_worker_may_be_running(self, job_id: str) -> bool:
        job = self._repository.get_job(job_id)
        return job is not None and job.worker_id is not None

    def _cleanup_job_workspace(self, project_id: str, job_id: str) -> bool:
        root = self._workspace.job_root(project_id, job_id)
        if not root.exists():
            return True

        attempts = 4
        for index in range(attempts):
            try:
                self._cleanup_staged_upload_for_job(project_id, job_id)
                shutil.rmtree(root)
                return True
            except OSError:
                if index + 1 >= attempts:
                    return False
                time.sleep(0.2 * (index + 1))
        return False

    def _cleanup_staged_upload_for_job(self, project_id: str, job_id: str) -> None:
        config_path = self._workspace.config_snapshot_file(project_id, job_id)
        if not config_path.exists():
            return
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        raw_path = payload.get("local_video_path")
        if not isinstance(raw_path, str) or not raw_path:
            return
        upload_root = (self._workspace.project_root(project_id) / "uploads").resolve()
        candidate = Path(raw_path).resolve()
        try:
            candidate.relative_to(upload_root)
        except ValueError:
            return
        candidate.unlink(missing_ok=True)

    def _mark_job_delete_pending(self, job_id: str) -> None:
        self._repository.set_job_delete_pending(job_id, True)
        with self._pending_job_delete_cache_lock:
            self._pending_job_deletes_cache.add(job_id)

    def _clear_job_delete_pending(self, job_id: str) -> None:
        self._repository.set_job_delete_pending(job_id, False)
        with self._pending_job_delete_cache_lock:
            self._pending_job_deletes_cache.discard(job_id)

    def _is_job_delete_pending(self, job_id: str) -> bool:
        with self._pending_job_delete_cache_lock:
            return job_id in self._pending_job_deletes_cache

    def _hydrate_pending_job_delete_cache(self) -> None:
        pending_ids = self._repository.list_pending_delete_job_ids()
        with self._pending_job_delete_cache_lock:
            self._pending_job_deletes_cache = set(pending_ids)

    def _reconcile_pending_job_deletes(self) -> None:
        with self._pending_job_delete_cache_lock:
            pending_ids = list(self._pending_job_deletes_cache)
        for job_id in pending_ids:
            job = self._repository.get_job(job_id)
            if job is None:
                with self._pending_job_delete_cache_lock:
                    self._pending_job_deletes_cache.discard(job_id)
                continue
            self.ensure_job_tracking(job_id)
            self._try_finalize_pending_job_delete(job.project_id, job_id)

    def _try_finalize_pending_job_delete(self, project_id: str, job_id: str) -> bool:
        if not self._is_job_delete_pending(job_id):
            return False
        if self._job_worker_may_be_running(job_id):
            return False

        job = self._repository.get_job(job_id)
        if job is None:
            self._clear_job_delete_pending(job_id)
            return True

        if job.status not in {
            JobStatus.SUCCEEDED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
        }:
            return False

        if not self._cleanup_job_workspace(project_id, job_id):
            return False

        self._repository.delete_job(job_id)
        self._clear_job_tracking(job_id)
        self._clear_job_delete_pending(job_id)
        return True
