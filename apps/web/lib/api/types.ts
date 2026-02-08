export interface Project {
  project_id: string;
  source_type: string;
  source_ref: string;
  title: string;
  status: string;
  created_at: string;
  updated_at?: string;
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
  status: string;
  current_stage: string | null;
  progress: number;
  latest_logs: string[];
  artifacts: ArtifactItem[];
}

export interface ControlAck {
  command: string;
  accepted: boolean;
  reason?: string;
  code?: string;
}

export type ControlCommandType = "pause" | "resume" | "cancel" | "delete";

export interface CreateProjectRequest {
  title?: string;
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

// --- Dual-asset ingest types (W08 contract) ---

export interface AssetSelection {
  video_format_id?: string;
  audio_format_id?: string;
}

export interface DualAssetIngestParams {
  source_url: string;
  analysis_asset: AssetSelection;
  quality_asset: AssetSelection;
}

export interface CreateJobRequest {
  project_id: string;
  summary_enabled?: boolean;
  ingest?: DualAssetIngestParams;
}
