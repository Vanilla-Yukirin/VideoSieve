export const DEFAULT_VALIDATE_SOURCE_URL = "https://www.bilibili.com/video/BV1xx411c7mD";
export const VALIDATE_SOURCE_URL_STORAGE_KEY = "videosieve_cookie_validate_source_url";

export function resolveInitialValidateSourceUrl(storedValue: string | null | undefined): string {
  const trimmed = storedValue?.trim();
  return trimmed ? trimmed : DEFAULT_VALIDATE_SOURCE_URL;
}

export type ValidateSourceCheckResult =
  | { ok: true; source_url: string }
  | { ok: false; errorKey: "cookie.validateSourceRequired" };

export function validateSourceUrlInput(rawValue: string): ValidateSourceCheckResult {
  const trimmed = rawValue.trim();
  if (!trimmed) {
    return { ok: false, errorKey: "cookie.validateSourceRequired" };
  }
  return { ok: true, source_url: trimmed };
}
