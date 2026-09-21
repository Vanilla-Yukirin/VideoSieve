export interface Project {
  project_id: string;
  title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Job {
  job_id: string;
  project_id: string;
  status: string;
  stage: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface ArtifactItem {
  path: string;
  size_bytes: number;
}

export interface JobSnapshot {
  project_id: string;
  job_id: string;
  state_version: number;
  status: string;
  current_stage: string | null;
  requested_action: string | null;
  control_phase: "accepted" | "applied" | null;
  control_request_id: string | null;
  attempt: number;
  progress: number;
  error_code: string | null;
  error_message: string | null;
  latest_logs: string[];
  artifacts: ArtifactItem[];
}

export interface ControlAck {
  command: string;
  accepted: boolean;
  phase?: "accepted" | "applied" | "rejected" | "failed";
  confirmed?: boolean;
  execution_state?: string;
  requested_action?: string | null;
  reason?: string;
  code?: string;
  request_id?: string;
}

export type ControlCommandType = "pause" | "resume" | "cancel" | "delete";

export interface CreateProjectRequest {
  title?: string;
}

export interface ApiErrorResponse {
  code: string;
  message: string;
  retryable?: boolean;
  active_job_ids?: string[];
  pending_job_ids?: string[];
}

export interface DeleteProjectResponse {
  deleted: boolean;
  cancelled_job_ids?: string[];
}

export interface SystemSettingsResponse {
  asr_provider: "unconfigured" | "capswriter";
  asr_endpoint: string;
  asr_language: string;
  asr_context: string;
  asr_timeout_seconds: number;
  asr_token_configured: boolean;
  vlm_api_key_configured: boolean;
  vlm_base_url: string;
  vlm_model: string;
  vlm_frame_prompt_zh: string;
  vlm_frame_prompt_en: string;
  vlm_concurrency: number;
  vlm_rpm: number;
  vlm_frame_prompt_zh_default: string;
  vlm_frame_prompt_en_default: string;
  summary_base_url: string;
  summary_model: string;
  summary_prompt_zh: string;
  summary_prompt_en: string;
  summary_max_input_chars: number;
  summary_api_key_configured: boolean;
  summary_prompt_zh_default: string;
  summary_prompt_en_default: string;
}

export interface SystemSettingsPatchRequest {
  asr_provider?: "unconfigured" | "capswriter";
  asr_endpoint?: string;
  asr_language?: string;
  asr_context?: string;
  asr_timeout_seconds?: number;
  asr_token?: string;
  clear_asr_token?: boolean;
  vlm_base_url?: string;
  vlm_model?: string;
  vlm_api_key?: string;
  clear_vlm_api_key?: boolean;
  vlm_frame_prompt_zh?: string;
  vlm_frame_prompt_en?: string;
  vlm_concurrency?: number;
  vlm_rpm?: number;
  summary_base_url?: string;
  summary_model?: string;
  summary_api_key?: string;
  clear_summary_api_key?: boolean;
  summary_prompt_zh?: string;
  summary_prompt_en?: string;
  summary_max_input_chars?: number;
}

export interface IngestFormatItem {
  format_id: string;
  ext?: string;
  resolution?: string;
  fps?: number;
  tbr?: number;
  protocol?: string;
  vcodec?: string;
  acodec?: string;
  filesize_approx?: number;
  is_video_only: boolean;
  is_audio_only: boolean;
}

export interface IngestProbeResponse {
  source_url: string;
  title: string;
  uploader?: string;
  duration_seconds?: number;
  webpage_url?: string;
  formats: IngestFormatItem[];
}

export interface IngestProbeRequest {
  source_url: string;
  cookie_id?: string;
}

// --- Dual-asset ingest types (W08 contract) ---

export interface AssetSelection {
  video_format_id?: string;
  audio_format_id?: string;
}

export interface DualAssetIngestParams {
  source_url: string;
  analysis_asset: AssetSelection;
  quality_asset: AssetSelection;
  cookie_id?: string;
}

export interface CreateJobRequest {
  project_id: string;
  summary_enabled?: boolean;
  ingest?: DualAssetIngestParams;
}

export interface CookieListItem {
  id: string;
  name: string;
  is_default: boolean;
  status: "unknown" | "valid" | "expired" | "invalid";
  last_validated_at?: string | null;
  last_error_code?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CookieCreateRequest {
  name: string;
  cookie_netscape_text: string;
  is_default?: boolean;
}

export interface CookiePatchRequest {
  name?: string;
  cookie_netscape_text?: string;
  is_default?: boolean;
}

export interface CookieValidateRequest {
  source_url: string;
}

export interface CookieValidateResponse {
  id: string;
  status: "unknown" | "valid" | "expired" | "invalid";
  last_validated_at?: string | null;
  last_error_code?: string | null;
}
