import { api } from "../api/client";
import type { ProviderProfile } from "../api/types";
import {
  defaultProfileId,
  isProviderSetupComplete,
  profilesForCapability,
  PROVIDER_TEMPLATES,
  templateForProfile,
} from "./providerSetup";

function profile(overrides: Partial<ProviderProfile>): ProviderProfile {
  return {
    id: "pp_test",
    display_name: "Test",
    capability: "frame_summary",
    protocol: "openai_chat_completions",
    api_root: "https://api.openai.com/v1",
    model: "vision-model",
    auth_mode: "bearer",
    options: {},
    revision: 1,
    is_default: true,
    credential_configured: true,
    ...overrides,
  };
}

describe("provider setup helpers", () => {
  const asr = profile({
    id: "pp_asr",
    capability: "asr",
    protocol: "capswriter_ws",
    api_root: "ws://127.0.0.1:6016",
    model: "",
    auth_mode: "optional_bearer",
    credential_configured: false,
  });
  const frame = profile({ id: "pp_frame" });

  it("requires ASR and a credential-backed frame-summary profile", () => {
    expect(isProviderSetupComplete([asr, frame])).toBe(true);
    expect(isProviderSetupComplete([frame])).toBe(false);
    expect(isProviderSetupComplete([asr])).toBe(false);
    expect(isProviderSetupComplete([asr, { ...frame, credential_configured: false }])).toBe(false);
  });

  it("resolves profiles and defaults per capability", () => {
    const alternate = profile({ id: "pp_frame_2", is_default: false });
    expect(profilesForCapability([asr, alternate, frame], "frame_summary")).toEqual([
      alternate,
      frame,
    ]);
    expect(defaultProfileId([asr, alternate, frame], "frame_summary")).toBe("pp_frame");
  });

  it("provides official protocol templates without a model vendor preset", () => {
    expect(PROVIDER_TEMPLATES.openai_responses).toMatchObject({
      protocol: "openai_responses",
      apiRoot: "https://api.openai.com/v1",
      authMode: "bearer",
    });
    expect(PROVIDER_TEMPLATES.anthropic).toMatchObject({
      protocol: "anthropic_messages",
      apiRoot: "https://api.anthropic.com/v1",
      authMode: "x_api_key",
    });
    expect(PROVIDER_TEMPLATES.openai_chat).not.toHaveProperty("model");
    expect(templateForProfile(frame)).toBe("openai_chat");
  });
});

describe("provider profile client", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("sends write-only credentials when creating a reusable profile", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => profile({}),
      text: async () => "{}",
    });
    (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;

    await api.createProviderProfile({
      display_name: "OpenAI vision",
      capability: "frame_summary",
      protocol: "openai_responses",
      api_root: "https://api.openai.com/v1",
      model: "vision-model",
      credential: "write-only-key",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/provider-profiles",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          display_name: "OpenAI vision",
          capability: "frame_summary",
          protocol: "openai_responses",
          api_root: "https://api.openai.com/v1",
          model: "vision-model",
          credential: "write-only-key",
        }),
      }),
    );
  });

  it("preserves the backend hint in a failed request", async () => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 502,
      text: async () =>
        JSON.stringify({ code: "ingest_failed", message: "request blocked", hint: "use a site cookie" }),
    });

    await expect(api.listProviderProfiles()).rejects.toEqual(
      expect.objectContaining({
        message: expect.stringContaining("建议：use a site cookie"),
      }),
    );
  });
});
