import {
  Project,
  Job,
  JobSnapshot,
  ControlAck,
  ControlCommandType,
  CreateProjectRequest,
  DeleteProjectResponse,
  ApiErrorResponse,
  AuthBootstrapStatusResponse,
  AuthBootstrapRequest,
  AuthLoginRequest,
  AuthTokenResponse,
  AuthMeResponse,
  PublicAccessFlagsResponse,
  SystemSettingsResponse,
  SystemSettingsPatchRequest,
  GuestCooldownResponse,
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
import { withAuthHeaders } from "../auth/session";

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
      throw new ApiClientError(`API Error ${res.status}: ${parsed.message}`, res.status, parsed.code, parsed);
    }
    throw new ApiClientError(`API Error ${res.status}: ${bodyText}`, res.status);
  }
  return res.json();
}

export const api = {
  // Auth
  getAuthBootstrapStatus: () => fetchJson<AuthBootstrapStatusResponse>("/auth/bootstrap-status"),

  bootstrapAuth: (payload: AuthBootstrapRequest) =>
    fetchJson<AuthTokenResponse>("/auth/bootstrap", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  loginAuth: (payload: AuthLoginRequest) =>
    fetchJson<AuthTokenResponse>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  logoutAuth: (token: string | null) =>
    fetchJson<{ ok: boolean }>("/auth/logout", {
      method: "POST",
      headers: withAuthHeaders(token),
    }),

  getAuthMe: (token: string | null) =>
    fetchJson<AuthMeResponse>("/auth/me", {
      headers: withAuthHeaders(token),
    }),

  getPublicAccessFlags: () => fetchJson<PublicAccessFlagsResponse>("/public/access-flags"),

  getSystemSettings: (token: string | null) =>
    fetchJson<SystemSettingsResponse>("/settings/system", {
      headers: withAuthHeaders(token),
    }),

  patchSystemSettings: (token: string | null, payload: SystemSettingsPatchRequest) =>
    fetchJson<SystemSettingsResponse>("/settings/system", {
      method: "PATCH",
      headers: withAuthHeaders(token, { "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    }),

  getGuestCooldown: () => fetchJson<GuestCooldownResponse>("/guest/cooldown"),

  // Projects
  createProject: (payload: CreateProjectRequest) =>
    fetchJson<{ project_id: string }>("/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

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
  createJob: (payload: CreateJobRequest, token: string | null = null) =>
    fetchJson<{ job_id: string }>("/jobs", {
      method: "POST",
      headers: withAuthHeaders(token, { "Content-Type": "application/json" }),
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

  validateMeCookie: (cookieId: string, payload: CookieValidateRequest) =>
    fetchJson<CookieValidateResponse>(`/me/cookies/${cookieId}/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  getRuntimeMode: (): "remote" | "mock" => "remote",
};
