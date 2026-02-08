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

export interface CreateJobRequest {
  project_id: string;
}
