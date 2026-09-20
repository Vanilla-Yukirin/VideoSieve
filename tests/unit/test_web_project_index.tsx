/** @jest-environment jsdom */

import { renderHook, waitFor } from "@testing-library/react";
import { useProjectIndex } from "../../apps/web/lib/hooks/useProjectIndex";

const STORAGE_KEY = "videosieve_project_index";

function project(projectId: string) {
  return {
    project_id: projectId,
    title: projectId,
    status: "queued",
    created_at: "2026-01-01T00:00:00+00:00",
    updated_at: "2026-01-01T00:00:00+00:00",
  };
}

function mockProjectList(payload: ReturnType<typeof project>[]) {
  (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  });
}

describe("SQLite-backed project index", () => {
  beforeEach(() => {
    localStorage.clear();
    jest.restoreAllMocks();
  });

  it("loads persisted projects even when localStorage was cleared", async () => {
    mockProjectList([project("p-new"), project("p-old")]);

    const { result } = renderHook(() => useProjectIndex());

    await waitFor(() => expect(result.current.isLoaded).toBe(true));
    expect(result.current.projectIds).toEqual(["p-new", "p-old"]);
    expect(result.current.loadError).toBeNull();
    expect(localStorage.getItem(STORAGE_KEY)).toBe('["p-new","p-old"]');
    expect(global.fetch).toHaveBeenCalledWith("/api/projects", undefined);
  });

  it("replaces a stale legacy browser index with the SQLite list", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(["p-stale", "p-old"]));
    mockProjectList([project("p-current")]);

    const { result } = renderHook(() => useProjectIndex());

    await waitFor(() => expect(result.current.isLoaded).toBe(true));
    expect(result.current.projectIds).toEqual(["p-current"]);
    expect(localStorage.getItem(STORAGE_KEY)).toBe('["p-current"]');
  });
});
