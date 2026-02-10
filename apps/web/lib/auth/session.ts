const SESSION_TOKEN_KEY = "videosieve_session_token";
const GUEST_SESSION_KEY = "videosieve_guest_session";
const GUEST_ALLOW_COOKIE_INPUT_KEY = "videosieve_guest_allow_cookie_input";

function hasWindow(): boolean {
  return typeof window !== "undefined";
}

export function getSessionToken(): string | null {
  if (!hasWindow()) return null;
  const token = window.localStorage.getItem(SESSION_TOKEN_KEY);
  const trimmed = token?.trim();
  return trimmed ? trimmed : null;
}

export function setSessionToken(token: string): void {
  if (!hasWindow()) return;
  const trimmed = token.trim();
  if (!trimmed) return;
  window.localStorage.setItem(SESSION_TOKEN_KEY, trimmed);
}

export function clearSessionToken(): void {
  if (!hasWindow()) return;
  window.localStorage.removeItem(SESSION_TOKEN_KEY);
}

export function setGuestSessionActive(active: boolean): void {
  if (!hasWindow()) return;
  if (active) {
    window.localStorage.setItem(GUEST_SESSION_KEY, "1");
    return;
  }
  window.localStorage.removeItem(GUEST_SESSION_KEY);
}

export function isGuestSessionActive(): boolean {
  if (!hasWindow()) return false;
  return window.localStorage.getItem(GUEST_SESSION_KEY) === "1";
}

export function setGuestAllowCookieInputCached(enabled: boolean): void {
  if (!hasWindow()) return;
  window.localStorage.setItem(GUEST_ALLOW_COOKIE_INPUT_KEY, enabled ? "1" : "0");
}

export function getGuestAllowCookieInputCached(): boolean {
  if (!hasWindow()) return false;
  return window.localStorage.getItem(GUEST_ALLOW_COOKIE_INPUT_KEY) === "1";
}

export function withAuthHeaders(token: string | null, headers: Record<string, string> = {}): Record<string, string> {
  const merged: Record<string, string> = { ...headers };
  const trimmed = token?.trim();
  if (trimmed) {
    merged.Authorization = `Bearer ${trimmed}`;
  }
  return merged;
}
