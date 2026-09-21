import type {
  ProviderAuthMode,
  ProviderCapability,
  ProviderProfile,
  ProviderProtocol,
} from "../api/types";

export type ProviderTemplateId =
  | "capswriter"
  | "openai_chat"
  | "openai_responses"
  | "anthropic"
  | "custom";

export interface ProviderTemplate {
  id: ProviderTemplateId;
  protocol: ProviderProtocol;
  apiRoot: string;
  authMode: ProviderAuthMode;
}

export const PROVIDER_TEMPLATES: Record<ProviderTemplateId, ProviderTemplate> = {
  capswriter: {
    id: "capswriter",
    protocol: "capswriter_ws",
    apiRoot: "ws://127.0.0.1:6016",
    authMode: "optional_bearer",
  },
  openai_chat: {
    id: "openai_chat",
    protocol: "openai_chat_completions",
    apiRoot: "https://api.openai.com/v1",
    authMode: "bearer",
  },
  openai_responses: {
    id: "openai_responses",
    protocol: "openai_responses",
    apiRoot: "https://api.openai.com/v1",
    authMode: "bearer",
  },
  anthropic: {
    id: "anthropic",
    protocol: "anthropic_messages",
    apiRoot: "https://api.anthropic.com/v1",
    authMode: "x_api_key",
  },
  custom: {
    id: "custom",
    protocol: "openai_chat_completions",
    apiRoot: "",
    authMode: "bearer",
  },
};

export function isProviderSetupComplete(profiles: ProviderProfile[]): boolean {
  return (
    profiles.some((profile) => profile.capability === "asr") &&
    profiles.some(
      (profile) => profile.capability === "frame_summary" && profile.credential_configured,
    )
  );
}

export function profilesForCapability(
  profiles: ProviderProfile[],
  capability: ProviderCapability,
): ProviderProfile[] {
  return profiles.filter((profile) => profile.capability === capability);
}

export function defaultProfileId(
  profiles: ProviderProfile[],
  capability: ProviderCapability,
): string {
  const candidates = profilesForCapability(profiles, capability);
  return candidates.find((profile) => profile.is_default)?.id ?? candidates[0]?.id ?? "";
}

export function templateForProfile(profile: ProviderProfile): ProviderTemplateId {
  if (profile.protocol === "capswriter_ws") return "capswriter";
  if (
    profile.protocol === "openai_chat_completions" &&
    profile.api_root === PROVIDER_TEMPLATES.openai_chat.apiRoot
  ) {
    return "openai_chat";
  }
  if (
    profile.protocol === "openai_responses" &&
    profile.api_root === PROVIDER_TEMPLATES.openai_responses.apiRoot
  ) {
    return "openai_responses";
  }
  if (
    profile.protocol === "anthropic_messages" &&
    profile.api_root === PROVIDER_TEMPLATES.anthropic.apiRoot
  ) {
    return "anthropic";
  }
  return "custom";
}
