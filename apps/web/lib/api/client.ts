import {
  ArtifactItem,
  ControlAck,
  ControlCommandType,
  CreateJobRequest,
  CreateProjectRequest,
  Job,
  JobSnapshot,
  Project,
} from "./types";

const API_BASE = "/api";
const STORAGE_KEY = "videosieve_mock_backend_v1";

type ApiMode = "auto" | "remote" | "mock";

let backendUnavailable = false;

type MockStore = {
  projects: Record<string, Project>;
  jobs: Record<string, Job>;
  jobsByProject: Record<string, string[]>;
};

const defaultStore: MockStore = {
  projects: {},
  jobs: {},
  jobsByProject: {},
};

function nowIso(): string {
  return new Date().toISOString();
}

function genId(prefix: "p" | "j"): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function getConfiguredMode(): ApiMode {
  const mode = (process.env.NEXT_PUBLIC_API_MODE || "auto").toLowerCase();
  if (mode === "mock" || mode === "remote") {
    return mode;
  }
  if (process.env.NODE_ENV === "development") {
    return "mock";
  }
  return "auto";
}

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function readStore(): MockStore {
  if (!canUseStorage()) {
    return { ...defaultStore };
  }
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return { ...defaultStore };
  }
  try {
    const parsed = JSON.parse(raw) as MockStore;
    return {
      projects: parsed.projects || {},
      jobs: parsed.jobs || {},
      jobsByProject: parsed.jobsByProject || {},
    };
  } catch {
    return { ...defaultStore };
  }
}

function writeStore(store: MockStore): void {
  if (!canUseStorage()) {
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
}

function asProjectResponse(project: Project): Project {
  return project;
}

function parsePath(url: string): string[] {
  return url.split("?")[0].split("/").filter(Boolean);
}

function mockRequest<T>(url: string, options?: RequestInit): T {
  const store = readStore();
  const method = (options?.method || "GET").toUpperCase();
  const segments = parsePath(url);

  if (method === "POST" && segments.length === 1 && segments[0] === "projects") {
    const payload = options?.body ? (JSON.parse(options.body as string) as CreateProjectRequest) : {};
    const projectId = genId("p");
    const ts = nowIso();
    store.projects[projectId] = {
      project_id: projectId,
      source_type: "local_file",
      source_ref: "",
      title: payload.title || `Mock Project ${projectId}`,
      status: "queued",
      created_at: ts,
      updated_at: ts,
    };
    store.jobsByProject[projectId] = store.jobsByProject[projectId] || [];
    writeStore(store);
    return { project_id: projectId } as T;
  }

  if (method === "GET" && segments.length === 2 && segments[0] === "projects") {
    const project = store.projects[segments[1]];
    if (!project) {
      throw new Error(`API Error 404: project not found (${segments[1]})`);
    }
    return asProjectResponse(project) as T;
  }

  if (method === "GET" && segments.length === 3 && segments[0] === "projects" && segments[2] === "jobs") {
    const projectId = segments[1];
    const ids = store.jobsByProject[projectId] || [];
    return ids.map((id) => store.jobs[id]).filter(Boolean) as T;
  }

  if (method === "POST" && segments.length === 1 && segments[0] === "jobs") {
    const payload = options?.body ? (JSON.parse(options.body as string) as CreateJobRequest) : undefined;
    if (!payload || !store.projects[payload.project_id]) {
      throw new Error(`API Error 404: project not found (${payload?.project_id || "unknown"})`);
    }
    const jobId = genId("j");
    const ts = nowIso();
    const job: Job = {
      job_id: jobId,
      project_id: payload.project_id,
      status: "queued",
      stage: null,
      error_code: null,
      error_message: null,
      created_at: ts,
      updated_at: ts,
    };
    store.jobs[jobId] = job;
    store.jobsByProject[payload.project_id] = [jobId, ...(store.jobsByProject[payload.project_id] || [])];
    writeStore(store);
    return { job_id: jobId } as T;
  }

  if (method === "GET" && segments.length === 2 && segments[0] === "jobs") {
    const job = store.jobs[segments[1]];
    if (!job) {
      throw new Error(`API Error 404: job not found (${segments[1]})`);
    }
    return job as T;
  }

  if (method === "GET" && segments.length === 3 && segments[0] === "jobs" && segments[2] === "snapshot") {
    const job = store.jobs[segments[1]];
    if (!job) {
      throw new Error(`API Error 404: job not found (${segments[1]})`);
    }
    const snapshot: JobSnapshot = {
      project_id: job.project_id,
      job_id: job.job_id,
      status: job.status,
      current_stage: job.stage,
      progress: job.status === "succeeded" ? 100 : job.status === "running" ? 30 : 0,
      latest_logs: [
        `[mock] job ${job.job_id} status: ${job.status}`,
        "[mock] backend unavailable, running in local mock mode",
      ],
      artifacts: [],
    };
    return snapshot as T;
  }

  if (method === "GET" && segments.length === 3 && segments[0] === "jobs" && segments[2] === "artifacts") {
    const job = store.jobs[segments[1]];
    if (!job) {
      throw new Error(`API Error 404: job not found (${segments[1]})`);
    }
    return [] as ArtifactItem[] as T;
  }

  if (
    method === "POST" &&
    segments.length === 4 &&
    segments[0] === "jobs" &&
    segments[2] === "control"
  ) {
    const jobId = segments[1];
    const command = segments[3] as ControlCommandType;
    const job = store.jobs[jobId];
    if (!job) {
      throw new Error(`API Error 404: job not found (${jobId})`);
    }

    if (command === "pause" && job.status === "running") {
      job.status = "paused";
    } else if (command === "resume" && job.status === "paused") {
      job.status = "running";
    } else if (command === "cancel" && ["queued", "running", "paused"].includes(job.status)) {
      job.status = "cancelled";
    } else if (command === "delete" && ["succeeded", "failed", "cancelled"].includes(job.status)) {
      delete store.jobs[jobId];
      store.jobsByProject[job.project_id] = (store.jobsByProject[job.project_id] || []).filter(
        (id) => id !== jobId,
      );
      writeStore(store);
      return {
        command,
        accepted: true,
      } as ControlAck as T;
    }

    job.updated_at = nowIso();
    writeStore(store);
    return {
      command,
      accepted: true,
      reason: backendUnavailable ? "mock control path" : undefined,
    } as ControlAck as T;
  }

  throw new Error(`API Error 501: mock route not implemented (${method} ${url})`);
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const mode = getConfiguredMode();

  if (mode === "mock" || (mode === "auto" && backendUnavailable)) {
    return mockRequest<T>(url, options);
  }

  try {
    const res = await fetch(`${API_BASE}${url}`, options);
    if (!res.ok) {
      throw new Error(`API Error ${res.status}: ${await res.text()}`);
    }
    return res.json() as Promise<T>;
  } catch (error) {
    if (mode === "remote") {
      throw error;
    }
    backendUnavailable = true;
    return mockRequest<T>(url, options);
  }
}

export const api = {
  createProject: (payload: CreateProjectRequest) =>
    fetchJson<{ project_id: string }>("/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  getProject: (projectId: string) => fetchJson<Project>(`/projects/${projectId}`),

  getProjectJobs: (projectId: string) => fetchJson<Job[]>(`/projects/${projectId}/jobs`),

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

  getRuntimeMode: (): "remote" | "mock" => {
    const mode = getConfiguredMode();
    if (mode === "mock") {
      return "mock";
    }
    return backendUnavailable ? "mock" : "remote";
  },
};
