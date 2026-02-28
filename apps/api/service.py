"""Job-scoped API control plane service."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import threading
import time
import uuid
from base64 import urlsafe_b64encode
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from math import ceil

from cryptography.fernet import Fernet, InvalidToken
from workers import WorkerRuntime

from contracts import ControlCommandType, JobStatus
from core import DELETE_PENDING_CLEANUP
from infra import (
    EventBus,
    EventSubscription,
    FileSystemWorkspaceStore,
    InfraEvent,
    JobRecord,
    JobRepository,
    SQLiteJobRepository,
    UserCookieRecord,
    WorkspaceStore,
)
from ingest import IngestRequest, probe_url_formats
from ingest.errors import INGEST_AUTH_REQUIRED, IngestError
from pipeline import PipelineOrchestrator
from pipeline.control import ControlAckPayload, evaluate_control_command
from pipeline.dispatch import (
    PIPELINE_DISPATCH_FAILED,
    extract_ingest_config,
    load_job_config_snapshot,
)

from .models import (
    ArtifactItem,
    AuthBootstrapRequest,
    AuthBootstrapStatusResponse,
    AuthLoginRequest,
    AuthMeResponse,
    AuthTokenResponse,
    CookieCreateRequest,
    CookieListItem,
    CookiePatchRequest,
    CookieValidateRequest,
    CookieValidateResponse,
    GuestCooldownResponse,
    IngestAssetSelection,
    IngestFormatItem,
    IngestParams,
    IngestProbeRequest,
    IngestProbeResponse,
    JobCreateRequest,
    JobSnapshot,
    ProjectCreateRequest,
    PublicAccessFlagsResponse,
    SystemSettingsPatchRequest,
    SystemSettingsResponse,
    utc_now_iso,
)

MAX_LOG_BUFFER = 100
PROJECT_DELETE_WAIT_SECONDS = 10.0
PROJECT_DELETE_POLL_SECONDS = 0.2
DEFAULT_COOKIE_USER_ID = "default_user"
SETTING_GUEST_MODE_ENABLED = "guest_mode_enabled"
SETTING_GUEST_ALLOW_COOKIE_INPUT = "guest_allow_cookie_input"


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


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


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
        job_dispatcher: Callable[[str, str], None] | None = None,
        worker_runtime: WorkerRuntime | None = None,
    ) -> None:
        self._repository = repository
        self._workspace = workspace
        self._event_bus = event_bus
        self._control_dispatcher = control_dispatcher or self._default_control_dispatcher
        self._worker_runtime = worker_runtime or WorkerRuntime(
            PipelineOrchestrator(
                repository=repository,
                workspace=workspace,
                event_bus=event_bus,
            )
        )
        # Dispatcher mode is fixed at construction time.
        # Runtime hot-swap is not supported.
        self._uses_default_job_dispatcher = job_dispatcher is None
        self._job_dispatcher = job_dispatcher or self._default_job_dispatcher
        self._subscriptions: dict[str, EventSubscription] = {}
        self._latest_progress: dict[str, float] = {}
        self._latest_stage: dict[str, str | None] = {}
        self._latest_logs: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=MAX_LOG_BUFFER))
        self._dispatch_lock = threading.Lock()
        self._dispatched_jobs: set[str] = set()
        self._project_locks_guard = threading.Lock()
        self._project_locks: dict[str, threading.RLock] = {}
        self._project_delete_lock = threading.Lock()
        self._deleting_projects: set[str] = set()
        self._pending_job_delete_cache_lock = threading.Lock()
        self._pending_job_deletes_cache: set[str] = set()
        self._hydrate_pending_job_delete_cache()
        self._sessions: dict[str, str] = {}
        self._session_lock = threading.Lock()
        self._validate_app_secret_or_raise()
        cooldown_raw = os.getenv("GUEST_JOB_COOLDOWN_SECONDS", "30")
        try:
            self._guest_cooldown_seconds = max(0, int(cooldown_raw))
        except ValueError:
            self._guest_cooldown_seconds = 30
        self._initialize_settings_from_env_once()
        self._validate_guest_cookie_setting_or_raise()

    def create_project(self, payload: ProjectCreateRequest) -> str:
        """Create one project and its workspace."""

        project_id = f"p_{uuid.uuid4().hex[:12]}"
        self._repository.upsert_project(
            project_id, title=payload.title, status=JobStatus.QUEUED.value
        )
        self._workspace.ensure_project_layout(project_id)
        return project_id

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

    def get_bootstrap_status(self) -> AuthBootstrapStatusResponse:
        required = self._repository.get_auth_user() is None
        return AuthBootstrapStatusResponse(bootstrap_required=required)

    def bootstrap_user(self, payload: AuthBootstrapRequest) -> AuthTokenResponse:
        if self._repository.get_auth_user() is not None:
            self._append_operation_log(
                event="auth.bootstrap",
                actor="system",
                outcome="rejected",
                code="bootstrap_required",
                detail="already bootstrapped",
            )
            raise ApiError(
                code="bootstrap_required",
                message="bootstrap already completed",
                status_code=409,
            )

        user_id = f"u_{uuid.uuid4().hex[:12]}"
        password_hash = self._hash_password(payload.password)
        token = self._issue_token()
        self._repository.create_auth_user(
            user_id=user_id,
            username=payload.username,
            password_hash=password_hash,
        )
        with self._session_lock:
            self._sessions[token] = payload.username
        self._append_operation_log(
            event="auth.bootstrap",
            actor=payload.username,
            outcome="accepted",
        )
        return AuthTokenResponse(token=token, username=payload.username)

    def login(self, payload: AuthLoginRequest) -> AuthTokenResponse:
        auth = self._repository.get_auth_user()
        if auth is None:
            self._append_operation_log(
                event="auth.login",
                actor=payload.username,
                outcome="rejected",
                code="bootstrap_required",
                detail="bootstrap not completed",
            )
            raise ApiError(
                code="bootstrap_required",
                message="bootstrap is required before login",
                status_code=409,
            )

        if payload.username != auth.username or not self._verify_password(
            payload.password, auth.password_hash
        ):
            self._append_operation_log(
                event="auth.login",
                actor=payload.username,
                outcome="rejected",
                code="invalid_credentials",
                detail="username or password mismatch",
            )
            raise ApiError(
                code="invalid_credentials",
                message="invalid credentials",
                status_code=401,
            )

        token = self._issue_token()
        with self._session_lock:
            self._sessions[token] = auth.username
        self._append_operation_log(event="auth.login", actor=auth.username, outcome="accepted")
        return AuthTokenResponse(token=token, username=auth.username)

    def logout(self, token: str | None) -> None:
        username = self._require_user_from_token(token)
        with self._session_lock:
            self._sessions.pop(token or "", None)
        self._append_operation_log(event="auth.logout", actor=username, outcome="accepted")

    def get_me(self, token: str | None) -> AuthMeResponse:
        username = self._require_user_from_token(token)
        return AuthMeResponse(username=username)

    def get_system_settings(self, token: str | None) -> SystemSettingsResponse:
        _ = self._require_user_from_token(token)
        settings = self._current_settings()
        return SystemSettingsResponse(
            guest_mode_enabled=settings[SETTING_GUEST_MODE_ENABLED],
            guest_allow_cookie_input=settings[SETTING_GUEST_ALLOW_COOKIE_INPUT],
        )

    def get_public_access_flags(self) -> PublicAccessFlagsResponse:
        settings = self._current_settings()
        return PublicAccessFlagsResponse(
            guest_mode_enabled=settings[SETTING_GUEST_MODE_ENABLED],
        )

    def patch_system_settings(
        self, token: str | None, payload: SystemSettingsPatchRequest
    ) -> SystemSettingsResponse:
        username = self._require_user_from_token(token)
        current = self._current_settings()
        next_guest_mode = (
            payload.guest_mode_enabled
            if payload.guest_mode_enabled is not None
            else current[SETTING_GUEST_MODE_ENABLED]
        )
        next_allow_cookie = (
            payload.guest_allow_cookie_input
            if payload.guest_allow_cookie_input is not None
            else current[SETTING_GUEST_ALLOW_COOKIE_INPUT]
        )
        if next_allow_cookie and not self._guest_cookie_key():
            self._append_operation_log(
                event="settings.patch",
                actor=username,
                outcome="rejected",
                code="guest_cookie_key_required",
                detail="missing GUEST_COOKIE_KEY",
            )
            raise ApiError(
                code="guest_cookie_key_required",
                message="GUEST_COOKIE_KEY is required when guest cookie input is enabled",
                status_code=422,
            )
        self._repository.set_setting(SETTING_GUEST_MODE_ENABLED, json.dumps(next_guest_mode))
        self._repository.set_setting(
            SETTING_GUEST_ALLOW_COOKIE_INPUT, json.dumps(next_allow_cookie)
        )
        self._append_operation_log(event="settings.patch", actor=username, outcome="accepted")
        return SystemSettingsResponse(
            guest_mode_enabled=next_guest_mode,
            guest_allow_cookie_input=next_allow_cookie,
        )

    def get_guest_cooldown(self) -> GuestCooldownResponse:
        remaining = self._guest_remaining_seconds(datetime.now(UTC))
        return GuestCooldownResponse(
            active=remaining > 0,
            remaining_seconds=remaining,
            cooldown_seconds=self._guest_cooldown_seconds,
        )

    def create_cookie(self, payload: CookieCreateRequest) -> CookieListItem:
        """Create one user-scoped encrypted cookie entry."""

        user_id = DEFAULT_COOKIE_USER_ID
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
        """List cookie metadata for current user scope."""

        return [
            self._to_cookie_list_item(row)
            for row in self._repository.list_user_cookies(DEFAULT_COOKIE_USER_ID)
        ]

    def patch_cookie(self, cookie_id: str, payload: CookiePatchRequest) -> CookieListItem:
        """Patch mutable cookie metadata/content without exposing plaintext."""

        _ = self._require_cookie(cookie_id)
        if payload.is_default:
            self._repository.clear_default_cookie_for_user(DEFAULT_COOKIE_USER_ID)

        self._repository.update_user_cookie(
            cookie_id=cookie_id,
            user_id=DEFAULT_COOKIE_USER_ID,
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
        """Delete one cookie entry in current user scope."""

        _ = self._require_cookie(cookie_id)
        self._repository.delete_user_cookie(cookie_id, DEFAULT_COOKIE_USER_ID)

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
                user_id=DEFAULT_COOKIE_USER_ID,
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
            user_id=DEFAULT_COOKIE_USER_ID,
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
        row = self._repository.get_user_cookie(cookie_id, DEFAULT_COOKIE_USER_ID)
        if row is None:
            raise KeyError(f"cookie not found: {cookie_id}")
        return row

    def _to_cookie_list_item(self, row: UserCookieRecord) -> CookieListItem:
        return CookieListItem(
            id=row.id,
            user_id=row.user_id,
            name=row.name,
            is_default=row.is_default,
            status=row.status,
            last_validated_at=row.last_validated_at,
            last_error_code=row.last_error_code,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _get_fernet(self) -> Fernet:
        secret = os.getenv("APP_SECRET_KEY")
        if not secret:
            raise ApiConfigError("APP_SECRET_KEY is required for cookie vault operations")
        digest = sha256(secret.encode("utf-8")).digest()
        return Fernet(urlsafe_b64encode(digest))

    def _encrypt_cookie(self, cookie_text: str) -> str:
        return self._get_fernet().encrypt(cookie_text.encode("utf-8")).decode("utf-8")

    def _decrypt_cookie(self, cookie_encrypted: str) -> str:
        try:
            decoded = self._get_fernet().decrypt(cookie_encrypted.encode("utf-8"))
        except InvalidToken as exc:
            raise ApiConfigError("APP_SECRET_KEY does not match stored cookie encryption") from exc
        return decoded.decode("utf-8")

    def _hash_password(self, password: str) -> str:
        salt = uuid.uuid4().hex
        digest = sha256(f"{salt}:{password}".encode()).hexdigest()
        return f"v1${salt}${digest}"

    def _verify_password(self, password: str, packed_hash: str) -> bool:
        parts = packed_hash.split("$", 2)
        if len(parts) != 3:
            return False
        _version, salt, expected = parts
        actual = sha256(f"{salt}:{password}".encode()).hexdigest()
        return secrets.compare_digest(actual, expected)

    def _issue_token(self) -> str:
        return secrets.token_urlsafe(32)

    def _require_user_from_token(self, token: str | None) -> str:
        if not token:
            raise ApiError(
                code="auth_required",
                message="authentication required",
                status_code=401,
            )
        with self._session_lock:
            username = self._sessions.get(token)
        if not isinstance(username, str):
            raise ApiError(
                code="auth_required",
                message="authentication required",
                status_code=401,
            )
        return username

    def _guest_cookie_key(self) -> str:
        return os.getenv("GUEST_COOKIE_KEY", "").strip()

    def _validate_app_secret_or_raise(self) -> None:
        secret = os.getenv("APP_SECRET_KEY", "").strip()
        if not secret:
            raise ApiConfigError("APP_SECRET_KEY is required for API startup")

    def _read_bool_env(self, name: str, *, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _read_setting_bool(self, key: str, *, default: bool) -> bool:
        raw = self._repository.get_setting(key)
        if raw is None:
            self._repository.set_setting(key, json.dumps(default))
            return default
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return default
        if isinstance(parsed, bool):
            return parsed
        return default

    def _initialize_settings_from_env_once(self) -> None:
        _ = self._read_setting_bool(
            SETTING_GUEST_MODE_ENABLED,
            default=self._read_bool_env("ENABLE_GUEST_MODE", default=False),
        )
        _ = self._read_setting_bool(
            SETTING_GUEST_ALLOW_COOKIE_INPUT,
            default=self._read_bool_env("GUEST_ALLOW_COOKIE_INPUT", default=False),
        )

    def _current_settings(self) -> dict[str, bool]:
        return {
            SETTING_GUEST_MODE_ENABLED: self._read_setting_bool(
                SETTING_GUEST_MODE_ENABLED,
                default=self._read_bool_env("ENABLE_GUEST_MODE", default=False),
            ),
            SETTING_GUEST_ALLOW_COOKIE_INPUT: self._read_setting_bool(
                SETTING_GUEST_ALLOW_COOKIE_INPUT,
                default=self._read_bool_env("GUEST_ALLOW_COOKIE_INPUT", default=False),
            ),
        }

    def _validate_guest_cookie_setting_or_raise(self) -> None:
        settings = self._current_settings()
        if settings[SETTING_GUEST_ALLOW_COOKIE_INPUT] and not self._guest_cookie_key():
            raise ApiConfigError(
                "guest_cookie_key_required: GUEST_COOKIE_KEY is required "
                "when guest cookie input is enabled"
            )

    def _parse_iso8601(self, value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _guest_remaining_seconds(self, now: datetime) -> int:
        next_allowed_at = self._repository.get_next_allowed_at()
        if next_allowed_at is None:
            return 0
        target = self._parse_iso8601(next_allowed_at)
        delta = (target - now.astimezone(UTC)).total_seconds()
        return max(0, ceil(delta))

    def _append_operation_log(
        self,
        *,
        event: str,
        actor: str,
        outcome: str,
        code: str | None = None,
        detail: str | None = None,
    ) -> None:
        actor_type = "guest" if actor == "guest" else "user"
        self._repository.append_operation_log(
            log_id=f"log_{uuid.uuid4().hex[:12]}",
            actor_type=actor_type,
            actor_id=None if actor_type == "guest" else actor,
            action=event,
            status=outcome,
            reason_code=code,
            created_at=utc_now_iso(),
            meta_json=json.dumps({"detail": detail}, ensure_ascii=True),
        )

    def create_job(self, payload: JobCreateRequest, *, actor: str = "guest") -> str:
        """Create one queued job under one project."""

        if actor == "guest":
            settings = self._current_settings()
            if not settings[SETTING_GUEST_MODE_ENABLED]:
                self._append_operation_log(
                    event="guest.job_submit",
                    actor="guest",
                    outcome="rejected",
                    code="auth_required",
                    detail="guest mode disabled",
                )
                raise ApiError(
                    code="auth_required",
                    message="authentication required",
                    status_code=401,
                )
            if payload.ingest and payload.ingest.cookie_id is not None:
                if not settings[SETTING_GUEST_ALLOW_COOKIE_INPUT]:
                    self._append_operation_log(
                        event="guest.job_submit",
                        actor="guest",
                        outcome="rejected",
                        code="auth_required",
                        detail="guest cookie input disabled",
                    )
                    raise ApiError(
                        code="auth_required",
                        message="authentication required",
                        status_code=401,
                    )

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

            if actor == "guest":
                now = datetime.now(UTC)
                acquired = self._repository.try_acquire(now, self._guest_cooldown_seconds)
                if not acquired:
                    remaining = self._guest_remaining_seconds(now)
                    self._append_operation_log(
                        event="guest.job_submit",
                        actor="guest",
                        outcome="rejected",
                        code="guest_cooldown_active",
                        detail=f"remaining_seconds={remaining}",
                    )
                    raise ApiError(
                        code="guest_cooldown_active",
                        message="guest cooldown is active",
                        status_code=429,
                        details={"remaining_seconds": remaining},
                    )

            job_id = f"j_{uuid.uuid4().hex[:12]}"
            self._repository.create_job(
                job_id, payload.project_id, status=JobStatus.QUEUED.value, stage=None
            )
            self._workspace.ensure_job_layout(payload.project_id, job_id)
            config_path = self._workspace.config_snapshot_file(payload.project_id, job_id)

            config: dict[str, object] = {
                "schema_version": "1.0",
                "project_id": payload.project_id,
                "job_id": job_id,
            }
            if payload.summary_enabled is not None:
                config["summary_enabled"] = payload.summary_enabled
            if payload.ingest:
                normalized_ingest, dedupe_estimate = self._normalize_ingest(payload.ingest)
                config["ingest"] = normalized_ingest
                config["dedupe_applied_estimate"] = dedupe_estimate

            config_path.write_text(
                json.dumps(
                    config,
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )
            if actor == "guest":
                self._append_operation_log(
                    event="guest.job_submit",
                    actor="guest",
                    outcome="accepted",
                    detail=f"job_id={job_id}",
                )

        self._dispatch_job_if_needed(payload.project_id, job_id)
        return job_id

    def _get_project_lock(self, project_id: str) -> threading.RLock:
        # Keep locks cached per project in single-process mode.
        # We intentionally avoid lock eviction to prevent split-lock races.
        with self._project_locks_guard:
            lock = self._project_locks.get(project_id)
            if lock is None:
                lock = threading.RLock()
                self._project_locks[project_id] = lock
            return lock

    def _dispatch_job_if_needed(self, project_id: str, job_id: str) -> None:
        if self._uses_default_job_dispatcher:
            with self._dispatch_lock:
                if job_id in self._dispatched_jobs:
                    return
                self._dispatched_jobs.add(job_id)

            try:
                self._job_dispatcher(project_id, job_id)
            except Exception as exc:  # pragma: no cover - thread start failures are rare
                with self._dispatch_lock:
                    self._dispatched_jobs.discard(job_id)
                self._mark_dispatch_failure(project_id, job_id, exc)
            return

        try:
            self._job_dispatcher(project_id, job_id)
        except Exception as exc:
            self._mark_dispatch_failure(project_id, job_id, exc)

    def _default_job_dispatcher(self, project_id: str, job_id: str) -> None:
        def _runner() -> None:
            thread_repo: SQLiteJobRepository | None = None
            try:
                thread_repo = self._open_thread_safe_repository()
                thread_workspace = self._open_thread_safe_workspace()
                worker_runtime = WorkerRuntime(
                    PipelineOrchestrator(
                        repository=thread_repo,
                        workspace=thread_workspace,
                        event_bus=self._event_bus,
                    )
                )
                config_snapshot = load_job_config_snapshot(
                    thread_workspace,
                    project_id=project_id,
                    job_id=job_id,
                )
                ingest_config = extract_ingest_config(config_snapshot)
                worker_runtime.run_job(
                    project_id=project_id,
                    job_id=job_id,
                    source_path=None,
                    ingest_config=ingest_config,
                    title=_as_optional_str(config_snapshot.get("title")),
                    description=_as_optional_str(config_snapshot.get("description")) or "",
                    tags=_as_str_list(config_snapshot.get("tags")),
                    language_hint=_as_optional_str(config_snapshot.get("language_hint")),
                )
            except Exception as exc:
                self._mark_dispatch_failure(project_id, job_id, exc)
            finally:
                if thread_repo is not None:
                    thread_repo.close()
                with self._dispatch_lock:
                    self._dispatched_jobs.discard(job_id)

        threading.Thread(target=_runner, name=f"pipeline-dispatch-{job_id}", daemon=True).start()

    def _mark_dispatch_failure(self, project_id: str, job_id: str, error: Exception) -> None:
        message = str(error) or error.__class__.__name__
        repository = self._open_thread_safe_repository()
        repository.update_job_status(
            job_id,
            status=JobStatus.FAILED.value,
            stage=None,
            error_code=PIPELINE_DISPATCH_FAILED,
            error_message=message,
        )
        repository.update_project_status(project_id, JobStatus.FAILED.value)
        repository.close()
        self._append_worker_log_line(project_id, job_id, f"[error] 任务派发失败: {message}")
        self._event_bus.publish(
            f"jobs:{job_id}",
            InfraEvent(
                event_type="log",
                project_id=project_id,
                job_id=job_id,
                payload={"level": "error", "message": f"任务派发失败: {message}"},
            ),
        )
        self._event_bus.publish(
            f"jobs:{job_id}",
            InfraEvent(
                event_type="error",
                project_id=project_id,
                job_id=job_id,
                payload={
                    "stage": "dispatch",
                    "code": PIPELINE_DISPATCH_FAILED,
                    "message": message,
                },
            ),
        )

    def _open_thread_safe_repository(self) -> SQLiteJobRepository:
        db_path = getattr(self._repository, "_db_path", None)
        if db_path is None:
            raise RuntimeError("thread dispatch requires sqlite repository")
        repository = SQLiteJobRepository(db_path)
        repository.ensure_schema()
        return repository

    def _open_thread_safe_workspace(self) -> FileSystemWorkspaceStore:
        base_dir = getattr(self._workspace, "_base_dir", None)
        if base_dir is None:
            raise RuntimeError("thread dispatch requires filesystem workspace")
        return FileSystemWorkspaceStore(base_dir)

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

        items: list[ArtifactItem] = []
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()), key=lambda p: p.as_posix()
        ):
            relative = path.relative_to(root).as_posix()
            items.append(ArtifactItem(path=relative, size_bytes=path.stat().st_size))
        return items

    def get_job_snapshot(self, job_id: str) -> JobSnapshot:
        """Build one HTTP snapshot for UI convergence."""

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
        progress = self._coalesce_progress(job_id, job.status)
        stage = self._latest_stage.get(job_id) or job.stage
        # worker.log is primarily written by the pipeline orchestrator.
        # Control plane only appends dispatch-failure fallback lines.
        persisted_logs = self._read_worker_log_tail(job.project_id, job_id)
        memory_logs = list(self._latest_logs.get(job_id) or [])
        merged_logs = self._merge_logs_with_tail_overlap(persisted_logs, memory_logs)

        return JobSnapshot(
            project_id=job.project_id,
            job_id=job_id,
            status=job.status,
            current_stage=stage,
            progress=progress,
            latest_logs=list(merged_logs),
            artifacts=self.list_artifacts(job.project_id, job_id),
        )

    def dispatch_control_command(
        self,
        *,
        job_id: str,
        command: ControlCommandType,
    ) -> dict[str, str | bool]:
        """Dispatch one job-scoped control command."""

        job = self._repository.get_job(job_id)
        if job is None:
            raise KeyError(f"job not found: {job_id}")
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
        with self._dispatch_lock:
            self._dispatched_jobs.discard(job_id)

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
            JobStatus.CANCEL_REQUESTED.value,
        }
        with self._dispatch_lock:
            running_jobs = set(self._dispatched_jobs)
        return [
            job.job_id
            for job in rows
            if job.status in pending_statuses or job.job_id in running_jobs
        ]

    def _append_worker_log_line(self, project_id: str, job_id: str, line: str) -> None:
        log_file = self._workspace.worker_log_file(project_id, job_id)
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")
        except OSError:
            return

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

    def _coalesce_progress(self, job_id: str, status: str) -> float:
        if job_id in self._latest_progress:
            return self._latest_progress[job_id]
        if status == JobStatus.SUCCEEDED.value:
            return 100.0
        return 0.0

    def _default_control_dispatcher(
        self,
        project_id: str,
        job_id: str,
        command: ControlCommandType,
    ) -> dict[str, str | bool]:
        current = self._repository.get_job(job_id)
        if current is None:
            raise KeyError(f"job not found: {job_id}")

        decision = evaluate_control_command(command, JobStatus(current.status))

        if decision.target_status is not None:
            self._repository.update_job_status(
                job_id, status=decision.target_status.value, stage=None
            )
            if decision.target_status is JobStatus.CANCEL_REQUESTED:
                is_running = False
                if self._uses_default_job_dispatcher:
                    with self._dispatch_lock:
                        is_running = job_id in self._dispatched_jobs
                if not is_running:
                    self._repository.update_job_status(
                        job_id,
                        status=JobStatus.CANCELLED.value,
                        stage=None,
                    )
                    self._repository.update_project_status(project_id, JobStatus.CANCELLED.value)
                    decision = ControlAckPayload(
                        command=command.value,
                        accepted=decision.accepted,
                        reason="cancel completed (no active worker)",
                        code=decision.code,
                    )
                    return decision.to_dict()
            if decision.target_status is not JobStatus.CANCEL_REQUESTED:
                self._repository.update_project_status(project_id, decision.target_status.value)

        if command is ControlCommandType.DELETE:
            if self._job_worker_may_be_running(job_id):
                self._mark_job_delete_pending(job_id)
                return ControlAckPayload(
                    command=command.value,
                    accepted=True,
                    code=DELETE_PENDING_CLEANUP,
                    reason="delete accepted, waiting for worker to stop before cleanup",
                ).to_dict()

            latest = self._repository.get_job(job_id)
            if latest is None:
                self._clear_job_delete_pending(job_id)
                return ControlAckPayload(
                    command=command.value,
                    accepted=True,
                    reason="job already deleted",
                ).to_dict()
            latest_status = JobStatus(latest.status)
            if latest_status is JobStatus.CANCEL_REQUESTED:
                self._repository.update_job_status(
                    job_id,
                    status=JobStatus.CANCELLED.value,
                    stage=None,
                )
                self._repository.update_project_status(project_id, JobStatus.CANCELLED.value)

            if decision.request_cleanup or latest_status is JobStatus.CANCEL_REQUESTED:
                if not self._cleanup_job_workspace(project_id, job_id):
                    self._mark_job_delete_pending(job_id)
                    return ControlAckPayload(
                        command=command.value,
                        accepted=True,
                        code=DELETE_PENDING_CLEANUP,
                        reason="delete accepted, waiting for file handles to release",
                    ).to_dict()
                self._repository.delete_job(job_id)
                self._clear_job_tracking(job_id)
                self._clear_job_delete_pending(job_id)
                return ControlAckPayload(
                    command=command.value,
                    accepted=True,
                    reason="job deleted",
                ).to_dict()

        ack_payload: dict[str, str | bool] = ControlAckPayload(
            command=command.value,
            accepted=decision.accepted,
            reason=decision.reason,
            code=decision.code,
        ).to_dict()
        return ack_payload

    def _job_worker_may_be_running(self, job_id: str) -> bool:
        if not self._uses_default_job_dispatcher:
            return False
        with self._dispatch_lock:
            return job_id in self._dispatched_jobs

    def _cleanup_job_workspace(self, project_id: str, job_id: str) -> bool:
        root = self._workspace.job_root(project_id, job_id)
        if not root.exists():
            return True

        attempts = 4
        for index in range(attempts):
            try:
                shutil.rmtree(root)
                return True
            except OSError:
                if index + 1 >= attempts:
                    return False
                time.sleep(0.2 * (index + 1))
        return False

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
