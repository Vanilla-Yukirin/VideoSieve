export const LEGACY_AUTH_STORAGE_KEYS = [
  "videosieve_session_token",
  "videosieve_guest_session",
  "videosieve_guest_allow_cookie_input",
] as const;

export function clearLegacyAuthStorage(storage: Pick<Storage, "removeItem">): void {
  for (const key of LEGACY_AUTH_STORAGE_KEYS) {
    storage.removeItem(key);
  }
}
