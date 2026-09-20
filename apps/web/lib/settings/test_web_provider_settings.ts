import {
  buildProviderSetupPatch,
  isProviderSetupComplete,
  ProviderSetupValues,
  validateProviderSetup,
} from "./providerSetup";
import { api } from "../api/client";
import { resolveLandingRoute } from "../auth/helpers";

const validValues: ProviderSetupValues = {
  asrEndpoint: " ws://127.0.0.1:6016 ",
  asrToken: "",
  vlmBaseUrl: " https://example.test/v1/chat/completions ",
  vlmModel: " vision-model ",
  vlmApiKey: "new-vlm-key",
  vlmApiKeyConfigured: false,
  summaryEnabled: false,
  summaryBaseUrl: "",
  summaryModel: "",
  summaryApiKey: "",
  summaryApiKeyConfigured: false,
};

describe("provider setup helpers", () => {
  const completeSettings = {
    asr_provider: "capswriter" as const,
    asr_endpoint: "ws://127.0.0.1:6016",
    vlm_base_url: "https://example.test/v1/chat/completions",
    vlm_model: "vision-model",
    vlm_api_key_configured: true,
  };

  it("requires CapsWriter and a configured VLM credential before setup is complete", () => {
    expect(isProviderSetupComplete(completeSettings)).toBe(true);
    expect(isProviderSetupComplete({ ...completeSettings, asr_provider: "unconfigured" })).toBe(
      false,
    );
    expect(isProviderSetupComplete({ ...completeSettings, asr_endpoint: "  " })).toBe(false);
    expect(isProviderSetupComplete({ ...completeSettings, vlm_base_url: "" })).toBe(false);
    expect(isProviderSetupComplete({ ...completeSettings, vlm_model: "" })).toBe(false);
    expect(isProviderSetupComplete({ ...completeSettings, vlm_api_key_configured: false })).toBe(
      false,
    );
  });

  it("routes incomplete admins to setup while leaving guest routing unchanged", () => {
    expect(
      resolveLandingRoute({
        bootstrapRequired: false,
        hasToken: true,
        tokenValid: true,
        guestSessionActive: false,
        providerSetupComplete: false,
      }),
    ).toBe("/setup");
    expect(
      resolveLandingRoute({
        bootstrapRequired: false,
        hasToken: false,
        tokenValid: false,
        guestSessionActive: true,
        providerSetupComplete: false,
      }),
    ).toBe("/");
  });

  it("requires the mandatory ASR and VLM fields", () => {
    expect(validateProviderSetup({ ...validValues, asrEndpoint: "" })).toBe(
      "asr_endpoint_required",
    );
    expect(validateProviderSetup({ ...validValues, vlmApiKey: "" })).toBe(
      "vlm_api_key_required",
    );
  });

  it("allows keeping an existing write-only VLM key", () => {
    expect(
      validateProviderSetup({
        ...validValues,
        vlmApiKey: "",
        vlmApiKeyConfigured: true,
      }),
    ).toBeNull();
  });

  it("requires summary configuration only when summary is enabled", () => {
    expect(validateProviderSetup(validValues)).toBeNull();
    expect(validateProviderSetup({ ...validValues, summaryEnabled: true })).toBe(
      "summary_base_url_required",
    );
  });

  it("omits blank write-only credentials so existing secrets are retained", () => {
    expect(
      buildProviderSetupPatch({
        ...validValues,
        vlmApiKey: "",
        vlmApiKeyConfigured: true,
      }),
    ).toEqual({
      asr_provider: "capswriter",
      asr_endpoint: "ws://127.0.0.1:6016",
      vlm_base_url: "https://example.test/v1/chat/completions",
      vlm_model: "vision-model",
    });
  });
});

describe("system settings credential client", () => {
  it("sends write-only credentials and explicit clear flags in the PATCH body", async () => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
      text: async () => "{}",
    });

    await api.patchSystemSettings("session-token", {
      vlm_api_key: "replacement-key",
      clear_summary_api_key: true,
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/settings/system",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          vlm_api_key: "replacement-key",
          clear_summary_api_key: true,
        }),
      }),
    );
  });
});
