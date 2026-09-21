"""Request/response models for the API control plane."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from contracts import ControlCommandType


class ApiModel(BaseModel):
    """Base API model with strict field handling."""

    model_config = ConfigDict(extra="forbid")


class IngestAssetSelection(ApiModel):
    """One asset quality selection via format ids only."""

    video_format_id: str
    audio_format_id: str | None = None


class IngestParams(ApiModel):
    """Parameters for job ingestion configuration."""

    source_url: str | None = None
    video_format_id: str | None = None
    audio_format_id: str | None = None
    cookie_id: str | None = None
    cookie_file_path: str | None = None
    cookie_secret_ref: str | None = None
    analysis_asset: IngestAssetSelection | None = None
    quality_asset: IngestAssetSelection | None = None

    @model_validator(mode="after")
    def validate_legacy_pair(self) -> IngestParams:
        if self.audio_format_id and not self.video_format_id:
            raise ValueError("audio_format_id requires video_format_id")
        return self


class ProjectCreateRequest(ApiModel):
    """Project create payload."""

    title: str | None = None


class SystemSettingsResponse(ApiModel):
    """System settings consumed by settings page."""

    # ASR routing. Credentials are write-only and encrypted at rest.
    asr_provider: str
    asr_endpoint: str
    asr_language: str
    asr_context: str
    asr_timeout_seconds: int
    asr_token_configured: bool
    # VLM configuration (mutable via PATCH)
    vlm_base_url: str
    vlm_model: str
    vlm_frame_prompt_zh: str
    vlm_frame_prompt_en: str
    vlm_concurrency: int
    vlm_rpm: int
    vlm_api_key_configured: bool
    # VLM prompt defaults (read-only, always reflects code constants)
    vlm_frame_prompt_zh_default: str
    vlm_frame_prompt_en_default: str
    # Overall summary LLM configuration. Credentials are never returned.
    summary_base_url: str
    summary_model: str
    summary_prompt_zh: str
    summary_prompt_en: str
    summary_max_input_chars: int
    summary_api_key_configured: bool
    summary_prompt_zh_default: str
    summary_prompt_en_default: str


class SystemSettingsPatchRequest(ApiModel):
    """Patch payload for mutable system settings."""

    asr_provider: str | None = None
    asr_endpoint: str | None = None
    asr_language: str | None = None
    asr_context: str | None = None
    asr_timeout_seconds: int | None = None
    asr_token: SecretStr | None = None
    clear_asr_token: bool | None = None
    vlm_base_url: str | None = None
    vlm_model: str | None = None
    vlm_frame_prompt_zh: str | None = None
    vlm_frame_prompt_en: str | None = None
    vlm_concurrency: int | None = None
    vlm_rpm: int | None = None
    vlm_api_key: SecretStr | None = None
    clear_vlm_api_key: bool | None = None
    summary_base_url: str | None = None
    summary_model: str | None = None
    summary_prompt_zh: str | None = None
    summary_prompt_en: str | None = None
    summary_max_input_chars: int | None = None
    summary_api_key: SecretStr | None = None
    clear_summary_api_key: bool | None = None

    @model_validator(mode="after")
    def validate_non_empty_patch(self) -> SystemSettingsPatchRequest:
        if all(
            v is None
            for v in [
                self.asr_provider,
                self.asr_endpoint,
                self.asr_language,
                self.asr_context,
                self.asr_timeout_seconds,
                self.asr_token,
                self.clear_asr_token,
                self.vlm_base_url,
                self.vlm_model,
                self.vlm_frame_prompt_zh,
                self.vlm_frame_prompt_en,
                self.vlm_concurrency,
                self.vlm_rpm,
                self.vlm_api_key,
                self.clear_vlm_api_key,
                self.summary_base_url,
                self.summary_model,
                self.summary_prompt_zh,
                self.summary_prompt_en,
                self.summary_max_input_chars,
                self.summary_api_key,
                self.clear_summary_api_key,
            ]
        ):
            raise ValueError("at least one settings field must be provided")
        return self


class JobCreateRequest(ApiModel):
    """Job create payload."""

    project_id: str
    ingest: IngestParams | None = None
    summary_enabled: bool | None = None
    local_video_path: str | None = None
    local_video_context: str | None = None


class IngestProbeRequest(ApiModel):
    """Probe payload for URL format options."""

    source_url: str
    # When both are provided, cookie_id takes precedence over cookie_file_path.
    cookie_id: str | None = None
    cookie_file_path: str | None = None


class IngestFormatItem(ApiModel):
    """One selectable format option for frontend quality picker."""

    format_id: str
    ext: str | None = None
    resolution: str | None = None
    fps: float | None = None
    tbr: float | None = None
    protocol: str | None = None
    vcodec: str | None = None
    acodec: str | None = None
    filesize_approx: int | None = None
    is_video_only: bool = False
    is_audio_only: bool = False


class IngestProbeResponse(ApiModel):
    """Probe response consumed by web quality selection UI."""

    source_url: str
    title: str
    uploader: str | None = None
    duration_seconds: float | None = None
    webpage_url: str | None = None
    formats: list[IngestFormatItem] = Field(default_factory=list)


class ArtifactItem(ApiModel):
    """Workspace artifact descriptor."""

    path: str
    size_bytes: int = Field(ge=0)


class JobSnapshot(ApiModel):
    """Authoritative job snapshot for HTTP compatibility and WebSocket convergence."""

    project_id: str
    job_id: str
    state_version: int = Field(default=0, ge=0)
    status: str
    current_stage: str | None = None
    requested_action: str | None = None
    control_phase: str | None = None
    control_request_id: str | None = None
    attempt: int = Field(default=0, ge=0)
    progress: float = Field(ge=0.0, le=100.0)
    error_code: str | None = None
    error_message: str | None = None
    latest_logs: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactItem] = Field(default_factory=list)


class WsControlCommand(ApiModel):
    """WS client command payload."""

    command: ControlCommandType
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


def validate_netscape_cookie_text(raw: str) -> str:
    """Validate Netscape cookie text lines and return normalized string."""

    lines = [line.strip() for line in raw.splitlines()]
    records = [line for line in lines if line and not line.startswith("#")]
    if not records:
        raise ValueError("cookie_netscape_text must include at least one cookie record")

    for index, line in enumerate(records, start=1):
        parts = line.split("\t")
        if len(parts) != 7:
            raise ValueError(f"cookie row {index} must contain exactly 7 tab-separated fields")
        include_subdomains = parts[1]
        secure = parts[3]
        expires = parts[4]
        name = parts[5]
        value = parts[6]
        if include_subdomains not in {"TRUE", "FALSE"}:
            raise ValueError(f"cookie row {index} has invalid include_subdomains flag")
        if secure not in {"TRUE", "FALSE"}:
            raise ValueError(f"cookie row {index} has invalid secure flag")
        if not expires.isdigit():
            raise ValueError(f"cookie row {index} has invalid expires value")
        if not name:
            raise ValueError(f"cookie row {index} has empty cookie name")
        if not value:
            raise ValueError(f"cookie row {index} has empty cookie value")

    normalized = "\n".join(lines).strip()
    if not normalized.endswith("\n"):
        normalized = f"{normalized}\n"
    return normalized


class CookieCreateRequest(ApiModel):
    """Create one encrypted cookie vault entry."""

    name: str
    cookie_netscape_text: str
    is_default: bool = False

    @model_validator(mode="after")
    def validate_cookie_text(self) -> CookieCreateRequest:
        self.cookie_netscape_text = validate_netscape_cookie_text(self.cookie_netscape_text)
        return self


class CookiePatchRequest(ApiModel):
    """Patch mutable cookie vault fields."""

    name: str | None = None
    cookie_netscape_text: str | None = None
    is_default: bool | None = None

    @model_validator(mode="after")
    def validate_patch_payload(self) -> CookiePatchRequest:
        if self.name is None and self.cookie_netscape_text is None and self.is_default is None:
            raise ValueError("at least one field must be provided")
        if self.cookie_netscape_text is not None:
            self.cookie_netscape_text = validate_netscape_cookie_text(self.cookie_netscape_text)
        return self


class CookieValidateRequest(ApiModel):
    """Request payload for cookie validity probe."""

    source_url: str | None = None

    @model_validator(mode="after")
    def validate_source_url(self) -> CookieValidateRequest:
        raw = (self.source_url or "").strip()
        if not raw:
            raise ValueError("source_url is required")

        parsed = urlparse(raw)
        host = parsed.netloc.lower()
        if host in {"bilibili.com", "www.bilibili.com"} and parsed.path in {"", "/"}:
            raise ValueError("请传具体视频页 URL")

        self.source_url = raw
        return self


class CookieListItem(ApiModel):
    """Public cookie metadata row without plaintext content."""

    id: str
    name: str
    is_default: bool
    status: str
    last_validated_at: str | None = None
    last_error_code: str | None = None
    created_at: str
    updated_at: str


class CookieValidateResponse(ApiModel):
    """Response for cookie validation action."""

    id: str
    status: str
    last_validated_at: str | None = None
    last_error_code: str | None = None


def utc_now_iso() -> str:
    """Generate UTC ISO8601 timestamp string."""

    return datetime.now(UTC).isoformat()
