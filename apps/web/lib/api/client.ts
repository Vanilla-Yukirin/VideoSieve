import {
  Project,
  Job,
  JobSnapshot,
  CreateProjectRequest,
  DeleteProjectResponse,
  ApiErrorResponse,
  SystemSettingsResponse,
  SystemSettingsPatchRequest,
  CreateJobRequest,
  ArtifactItem,
  IngestProbeRequest,
  IngestProbeResponse,
  CookieListItem,
  CookieCreateRequest,
  CookiePatchRequest,
  CookieValidateRequest,
  CookieValidateResponse,
  ProviderCapability,
  ProviderProfile,
  ProviderProfileCreateRequest,
  ProviderProfilePatchRequest,
  ProviderProfileTestResponse,
} from "./types";

const API_BASE = "/api"; // Rewrites will handle the proxy

export class ApiClientError extends Error {
  status: number;
  code?: string;
  details?: ApiErrorResponse;

  constructor(message: string, status: number, code?: string, details?: ApiErrorResponse) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, options);
  if (!res.ok) {
    const bodyText = await res.text();
    let parsed: ApiErrorResponse | undefined;
    try {
      parsed = JSON.parse(bodyText) as ApiErrorResponse;
    } catch {
      parsed = undefined;
    }
    if (parsed?.code && parsed?.message) {
      const hint = parsed.hint ? `\n建议：${parsed.hint}` : "";
      throw new ApiClientError(
        `API Error ${res.status}: ${parsed.message}${hint}`,
        res.status,
        parsed.code,
        parsed,
      );
    }
    throw new ApiClientError(`API Error ${res.status}: ${bodyText}`, res.status);
  }
  return res.json();
}

export const api = {
  getSystemSettings: () => fetchJson<SystemSettingsResponse>("/settings/system"),

  patchSystemSettings: (payload: SystemSettingsPatchRequest) =>
    fetchJson<SystemSettingsResponse>("/settings/system", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  listProviderProfiles: (capability?: ProviderCapability) => {
    const query = capability ? `?capability=${encodeURIComponent(capability)}` : "";
    return fetchJson<ProviderProfile[]>(`/provider-profiles${query}`);
  },

  createProviderProfile: (payload: ProviderProfileCreateRequest) =>
    fetchJson<ProviderProfile>("/provider-profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  patchProviderProfile: (profileId: string, payload: ProviderProfilePatchRequest) =>
    fetchJson<ProviderProfile>(`/provider-profiles/${profileId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  deleteProviderProfile: (profileId: string) =>
    fetchJson<{ deleted: boolean }>(`/provider-profiles/${profileId}`, {
      method: "DELETE",
    }),

  testProviderProfile: (profileId: string) =>
    fetchJson<ProviderProfileTestResponse>(`/provider-profiles/${profileId}/test`, {
      method: "POST",
    }),

  // Projects
  createProject: (payload: CreateProjectRequest) =>
    fetchJson<{ project_id: string }>("/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  listProjects: () => fetchJson<Project[]>("/projects"),

  getProject: (projectId: string) => fetchJson<Project>(`/projects/${projectId}`),

  deleteProject: (projectId: string, forceCancelActive = false) =>
    fetchJson<DeleteProjectResponse>(
      `/projects/${projectId}?force_cancel_active=${forceCancelActive ? "true" : "false"}`,
      {
        method: "DELETE",
      }
    ),

  getProjectJobs: (projectId: string) => fetchJson<Job[]>(`/projects/${projectId}/jobs`),

  // Jobs
  createJob: (payload: CreateJobRequest) =>
    fetchJson<{ job_id: string }>("/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  uploadLocalVideo: (projectId: string, formData: FormData) =>
    fetchJson<{ job_id: string }>(`/projects/${projectId}/jobs/upload`, {
      method: "POST",
      body: formData,
    }),

  getJob: (jobId: string) => fetchJson<Job>(`/jobs/${jobId}`),

  getJobSnapshot: (jobId: string) => fetchJson<JobSnapshot>(`/jobs/${jobId}/snapshot`),

  listJobArtifacts: (jobId: string) => fetchJson<ArtifactItem[]>(`/jobs/${jobId}/artifacts`),

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
  listCookies: () => fetchJson<CookieListItem[]>("/cookies"),

  createCookie: (payload: CookieCreateRequest) =>
    fetchJson<CookieListItem>("/cookies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  patchCookie: (cookieId: string, payload: CookiePatchRequest) =>
    fetchJson<CookieListItem>(`/cookies/${cookieId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  deleteCookie: (cookieId: string) =>
    fetchJson<{ deleted: boolean }>(`/cookies/${cookieId}`, {
      method: "DELETE",
    }),

  validateCookie: (cookieId: string, payload: CookieValidateRequest) =>
    fetchJson<CookieValidateResponse>(`/cookies/${cookieId}/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
};
