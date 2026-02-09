import { api } from "../../apps/web/lib/api/client";
import { resolveDefaultCookieId } from "../../apps/web/lib/cookies/helpers";
import { CookieListItem, CreateJobRequest } from "../../apps/web/lib/api/types";

function mockFetchOk(payload: unknown) {
  (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  });
}

describe("cookie vault client CRUD interactions", () => {
  it("lists cookies via GET /me/cookies", async () => {
    mockFetchOk([]);

    await api.listMeCookies();

    expect(global.fetch).toHaveBeenCalledWith("/api/me/cookies", undefined);
  });

  it("creates a cookie via POST /me/cookies", async () => {
    const created = {
      id: "c_1",
      user_id: "default",
      name: "bili-main",
      is_default: true,
      status: "unknown",
      created_at: "2026-02-09T00:00:00Z",
      updated_at: "2026-02-09T00:00:00Z",
    };
    mockFetchOk(created);

    await api.createMeCookie({
      name: "bili-main",
      cookie_netscape_text: ".bilibili.com\tTRUE\t/\tTRUE\t4102444800\tSESSDATA\tabc",
      is_default: true,
    });

    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/me/cookies",
      expect.objectContaining({ method: "POST" }),
    );
    const options = (global.fetch as jest.Mock).mock.calls[0][1] as { body: string };
    expect(options.body).toContain("cookie_netscape_text");
  });

  it("updates default cookie via PATCH /me/cookies/{id}", async () => {
    mockFetchOk({
      id: "c_2",
      user_id: "default",
      name: "bili-alt",
      is_default: true,
      status: "unknown",
      created_at: "2026-02-09T00:00:00Z",
      updated_at: "2026-02-09T00:00:00Z",
    });

    await api.patchMeCookie("c_2", { is_default: true });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/me/cookies/c_2",
      expect.objectContaining({ method: "PATCH" }),
    );
    const options = (global.fetch as jest.Mock).mock.calls[0][1] as { body: string };
    expect(options.body).toContain("is_default");
  });

  it("deletes cookie via DELETE /me/cookies/{id}", async () => {
    mockFetchOk({ deleted: true });

    await api.deleteMeCookie("c_3");

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/me/cookies/c_3",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("validates cookie via POST /me/cookies/{id}/validate", async () => {
    mockFetchOk({
      id: "c_3",
      status: "valid",
      last_validated_at: "2026-02-09T01:00:00Z",
      last_error_code: null,
    });

    await api.validateMeCookie("c_3", { source_url: "https://www.bilibili.com" });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/me/cookies/c_3/validate",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("cookie defaults and create-job payload", () => {
  it("selects default cookie id when present", () => {
    const cookies: CookieListItem[] = [
      {
        id: "c_a",
        user_id: "default",
        name: "A",
        is_default: false,
        status: "unknown",
        created_at: "2026-02-09T00:00:00Z",
        updated_at: "2026-02-09T00:00:00Z",
      },
      {
        id: "c_b",
        user_id: "default",
        name: "B",
        is_default: true,
        status: "valid",
        created_at: "2026-02-09T00:00:00Z",
        updated_at: "2026-02-09T00:00:00Z",
      },
    ];

    expect(resolveDefaultCookieId(cookies)).toBe("c_b");
  });

  it("falls back to first cookie when no default exists", () => {
    const cookies: CookieListItem[] = [
      {
        id: "c_first",
        user_id: "default",
        name: "first",
        is_default: false,
        status: "unknown",
        created_at: "2026-02-09T00:00:00Z",
        updated_at: "2026-02-09T00:00:00Z",
      },
    ];

    expect(resolveDefaultCookieId(cookies)).toBe("c_first");
    expect(resolveDefaultCookieId([])).toBe("");
  });

  it("create-job payload includes cookie_id and excludes plaintext cookie fields", () => {
    const request: CreateJobRequest = {
      project_id: "proj-cookie",
      summary_enabled: false,
      ingest: {
        source_url: "https://www.bilibili.com/video/BV1x",
        analysis_asset: { video_format_id: "30080", audio_format_id: "30280" },
        quality_asset: { video_format_id: "30120", audio_format_id: "30290" },
        cookie_id: "c_b",
      },
    };

    const serialized = JSON.stringify(request);
    expect(serialized).toContain("cookie_id");
    expect(serialized).not.toContain("cookie_content");
    expect(serialized).not.toContain("cookie_file_path");
    expect(serialized).not.toContain("cookie_secret_ref");
  });
});
