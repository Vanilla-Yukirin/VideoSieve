import type { SystemSettingsPatchRequest, SystemSettingsResponse } from "../api/types";

type ProviderSetupStatus = Pick<
  SystemSettingsResponse,
  "asr_provider" | "asr_endpoint" | "vlm_base_url" | "vlm_model" | "vlm_api_key_configured"
>;

export function isProviderSetupComplete(settings: ProviderSetupStatus): boolean {
  return (
    settings.asr_provider === "capswriter" &&
    Boolean(settings.asr_endpoint.trim()) &&
    Boolean(settings.vlm_base_url.trim()) &&
    Boolean(settings.vlm_model.trim()) &&
    settings.vlm_api_key_configured
  );
}

export interface ProviderSetupValues {
  asrEndpoint: string;
  asrToken: string;
  vlmBaseUrl: string;
  vlmModel: string;
  vlmApiKey: string;
  vlmApiKeyConfigured: boolean;
  summaryEnabled: boolean;
  summaryBaseUrl: string;
  summaryModel: string;
  summaryApiKey: string;
  summaryApiKeyConfigured: boolean;
}

export type ProviderSetupValidationError =
  | "asr_endpoint_required"
  | "vlm_base_url_required"
  | "vlm_model_required"
  | "vlm_api_key_required"
  | "summary_base_url_required"
  | "summary_model_required"
  | "summary_api_key_required";

export function validateProviderSetup(
  values: ProviderSetupValues,
): ProviderSetupValidationError | null {
  if (!values.asrEndpoint.trim()) return "asr_endpoint_required";
  if (!values.vlmBaseUrl.trim()) return "vlm_base_url_required";
  if (!values.vlmModel.trim()) return "vlm_model_required";
  if (!values.vlmApiKey.trim() && !values.vlmApiKeyConfigured) {
    return "vlm_api_key_required";
  }
  if (!values.summaryEnabled) return null;
  if (!values.summaryBaseUrl.trim()) return "summary_base_url_required";
  if (!values.summaryModel.trim()) return "summary_model_required";
  if (!values.summaryApiKey.trim() && !values.summaryApiKeyConfigured) {
    return "summary_api_key_required";
  }
  return null;
}

export function buildProviderSetupPatch(values: ProviderSetupValues): SystemSettingsPatchRequest {
  const patch: SystemSettingsPatchRequest = {
    asr_provider: "capswriter",
    asr_endpoint: values.asrEndpoint.trim(),
    vlm_base_url: values.vlmBaseUrl.trim(),
    vlm_model: values.vlmModel.trim(),
  };

  const asrToken = values.asrToken.trim();
  if (asrToken) patch.asr_token = asrToken;

  const vlmApiKey = values.vlmApiKey.trim();
  if (vlmApiKey) patch.vlm_api_key = vlmApiKey;

  if (values.summaryEnabled) {
    patch.summary_base_url = values.summaryBaseUrl.trim();
    patch.summary_model = values.summaryModel.trim();
    const summaryApiKey = values.summaryApiKey.trim();
    if (summaryApiKey) patch.summary_api_key = summaryApiKey;
  }

  return patch;
}
