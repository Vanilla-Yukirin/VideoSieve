import {
  Project,
  Job,
  JobSnapshot,
  ControlAck,
  ControlCommandType,
  CreateProjectRequest,
  CreateJobRequest,
  ArtifactItem,
  IngestProbeResponse,
} from "./types";

const API_BASE = "/api"; // Rewrites will handle the proxy

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, options);
  if (!res.ok) {
    throw new Error(`API Error ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export const api = {
  // Projects
  createProject: (payload: CreateProjectRequest) =>
    fetchJson<{ project_id: string }>("/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  getProject: (projectId: string) => fetchJson<Project>(`/projects/${projectId}`),

  getProjectJobs: (projectId: string) => fetchJson<Job[]>(`/projects/${projectId}/jobs`),

  // Jobs
  createJob: (payload: CreateJobRequest) =>
    fetchJson<{ job_id: string }>("/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  getJob: (jobId: string) => fetchJson<Job>(`/jobs/${jobId}`),

  getJobSnapshot: (jobId: string) => fetchJson<JobSnapshot>(`/jobs/${jobId}/snapshot`),

  listJobArtifacts: (jobId: string) => fetchJson<ArtifactItem[]>(`/jobs/${jobId}/artifacts`),

  controlJob: (jobId: string, command: ControlCommandType) =>
    fetchJson<ControlAck>(`/jobs/${jobId}/control/${command}`, {
      method: "POST",
    }),

  probeIngestFormats: (sourceUrl: string, cookieContent?: string) =>
    fetchJson<IngestProbeResponse>("/ingest/probe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_url: sourceUrl, cookie_content: cookieContent }),
    }),

  getRuntimeMode: (): "remote" | "mock" => "remote",
};
