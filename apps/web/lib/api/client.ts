import {
  Project,
  Job,
  JobSnapshot,
  ControlAck,
  ControlCommandType,
  CreateProjectRequest,
  CreateJobRequest,
  ArtifactItem,
  IngestProbeRequest,
  IngestProbeResponse,
  CookieListItem,
  CookieCreateRequest,
  CookiePatchRequest,
  CookieValidateRequest,
  CookieValidateResponse,
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

  // Probe: source_url with optional cookie_id
  probeIngestFormats: (payload: IngestProbeRequest) => {
    const trimmedCookieId = payload.cookie_id?.trim();
    const requestBody = trimmedCookieId
      ? { source_url: payload.source_url, cookie_id: trimmedCookieId }
      : { source_url: payload.source_url };

    return fetchJson<IngestProbeResponse>("/ingest/probe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    });
  },

  // Cookie Vault
  listMeCookies: () => fetchJson<CookieListItem[]>("/me/cookies"),

  createMeCookie: (payload: CookieCreateRequest) =>
    fetchJson<CookieListItem>("/me/cookies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  patchMeCookie: (cookieId: string, payload: CookiePatchRequest) =>
    fetchJson<CookieListItem>(`/me/cookies/${cookieId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  deleteMeCookie: (cookieId: string) =>
    fetchJson<{ deleted: boolean }>(`/me/cookies/${cookieId}`, {
      method: "DELETE",
    }),

  validateMeCookie: (cookieId: string, payload: CookieValidateRequest = {}) =>
    fetchJson<CookieValidateResponse>(`/me/cookies/${cookieId}/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  getRuntimeMode: (): "remote" | "mock" => "remote",
};
