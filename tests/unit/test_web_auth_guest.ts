import { ApiClientError, api } from "../../apps/web/lib/api/client";
import {
  canShowGuestEntry,
  isGuestCookieInputDisabled,
  isGuestCooldownBlocking,
  resolveLandingRoute,
  sanitizeIngestForSubmit,
} from "../../apps/web/lib/auth/helpers";
import { DualAssetIngestParams } from "../../apps/web/lib/api/types";

function mockFetchOk(payload: unknown) {
  (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  });
}

describe("auth and guest route branching", () => {
  it("routes to /setup when bootstrap is required", () => {
    expect(
      resolveLandingRoute({
        bootstrapRequired: true,
        hasToken: false,
        tokenValid: false,
        guestSessionActive: false,
      }),
    ).toBe("/setup");
  });

  it("routes to / when token is valid", () => {
    expect(
      resolveLandingRoute({
        bootstrapRequired: false,
        hasToken: true,
        tokenValid: true,
        guestSessionActive: false,
      }),
    ).toBe("/");
  });

  it("routes to /login without token or guest session", () => {
    expect(
      resolveLandingRoute({
        bootstrapRequired: false,
        hasToken: false,
        tokenValid: false,
        guestSessionActive: false,
      }),
    ).toBe("/login");
  });

  it("routes to / for active guest session", () => {
    expect(
      resolveLandingRoute({
        bootstrapRequired: false,
        hasToken: false,
        tokenValid: false,
        guestSessionActive: true,
      }),
    ).toBe("/");
  });
});

describe("guest access flags and cooldown behavior", () => {
  it("shows guest button only when public guest_mode_enabled is true", () => {
    expect(canShowGuestEntry({ guest_mode_enabled: true })).toBe(true);
    expect(canShowGuestEntry({ guest_mode_enabled: false })).toBe(false);
    expect(canShowGuestEntry(undefined)).toBe(false);
  });

  it("disables cookie input for guest when guest cookie input is not allowed", () => {
    expect(isGuestCookieInputDisabled(true, false)).toBe(true);
    expect(isGuestCookieInputDisabled(true, true)).toBe(false);
    expect(isGuestCookieInputDisabled(false, false)).toBe(false);
  });

  it("blocks guest submit when cooldown is active", () => {
    expect(isGuestCooldownBlocking(true, { active: true, remaining_seconds: 12 })).toBe(true);
    expect(isGuestCooldownBlocking(true, { active: true, remaining_seconds: 0 })).toBe(false);
    expect(isGuestCooldownBlocking(false, { active: true, remaining_seconds: 12 })).toBe(false);
  });
});

describe("guest payload safety and cooldown error mapping", () => {
  it("removes cookie_id from ingest for guest when cookie input is disabled", () => {
    const ingest: DualAssetIngestParams = {
      source_url: "https://example.com/video",
      analysis_asset: { video_format_id: "100", audio_format_id: "200" },
      quality_asset: { video_format_id: "100", audio_format_id: "200" },
      cookie_id: "c_demo",
    };

    const sanitized = sanitizeIngestForSubmit(ingest, { isGuest: true, guestAllowCookieInput: false });
    const serialized = JSON.stringify(sanitized);
    expect(serialized).not.toContain("cookie_id");
  });

  it("preserves cookie_id for user mode and forbidden plaintext fields remain absent", () => {
    const ingest: DualAssetIngestParams = {
      source_url: "https://example.com/video",
      analysis_asset: { video_format_id: "100", audio_format_id: "200" },
      quality_asset: { video_format_id: "100", audio_format_id: "200" },
      cookie_id: "c_demo",
    };

    const sanitized = sanitizeIngestForSubmit(ingest, { isGuest: false, guestAllowCookieInput: false });
    const serialized = JSON.stringify(sanitized);
    expect(serialized).toContain("cookie_id");
    expect(serialized).not.toContain("cookie_content");
    expect(serialized).not.toContain("cookie_file_path");
    expect(serialized).not.toContain("cookie_secret_ref");
  });

  it("reads public access flags from /public/access-flags", async () => {
    mockFetchOk({ guest_mode_enabled: true });

    await api.getPublicAccessFlags();

    expect(global.fetch).toHaveBeenCalledWith("/api/public/access-flags", undefined);
  });

  it("surfaces guest_cooldown_active details from create job errors", async () => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 429,
      text: async () =>
        JSON.stringify({
          code: "guest_cooldown_active",
          message: "guest cooldown is active",
          remaining_seconds: 15,
        }),
    });

    await expect(api.createJob({ project_id: "p1" })).rejects.toMatchObject({
      code: "guest_cooldown_active",
      details: expect.objectContaining({ remaining_seconds: 15 }),
    });
  });

  it("maps create job auth_required errors for guest mode restrictions", async () => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: async () =>
        JSON.stringify({
          code: "auth_required",
          message: "authentication required",
        }),
    });

    try {
      await api.createJob({ project_id: "p2" });
      throw new Error("expected createJob to throw");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiClientError);
      const apiError = error as ApiClientError;
      expect(apiError.code).toBe("auth_required");
    }
  });
});
