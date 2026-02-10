import { DualAssetIngestParams } from "../api/types";

export type LandingRoute = "/" | "/login" | "/setup";

export function resolveLandingRoute(input: {
  bootstrapRequired: boolean;
  hasToken: boolean;
  tokenValid: boolean;
  guestSessionActive: boolean;
}): LandingRoute {
  if (input.bootstrapRequired) return "/setup";
  if (input.hasToken && input.tokenValid) return "/";
  if (input.guestSessionActive) return "/";
  return "/login";
}

export function isGuestCookieInputDisabled(isGuest: boolean, guestAllowCookieInput: boolean): boolean {
  return isGuest && !guestAllowCookieInput;
}

export function sanitizeIngestForSubmit(
  ingest: DualAssetIngestParams | undefined,
  options: { isGuest: boolean; guestAllowCookieInput: boolean },
): DualAssetIngestParams | undefined {
  if (!ingest) return undefined;
  const cookieId = ingest.cookie_id?.trim();
  if (options.isGuest && !options.guestAllowCookieInput) {
    const { cookie_id: _ignored, ...rest } = ingest;
    return rest;
  }
  if (!cookieId) {
    const { cookie_id: _ignored, ...rest } = ingest;
    return rest;
  }
  return { ...ingest, cookie_id: cookieId };
}

export function canShowGuestEntry(flag: { guest_mode_enabled: boolean } | undefined): boolean {
  return Boolean(flag?.guest_mode_enabled);
}

export function isGuestCooldownBlocking(
  isGuest: boolean,
  cooldown: { active: boolean; remaining_seconds: number } | null,
): boolean {
  return Boolean(isGuest && cooldown?.active && cooldown.remaining_seconds > 0);
}
