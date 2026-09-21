import type { CookieListItem } from "../api/types";
import type { Locale, MessageKey } from "../i18n/messages";

const COOKIE_STATUS_KEYS: Record<CookieListItem["status"], MessageKey> = {
  unknown: "cookie.statusUnknown",
  valid: "cookie.statusValid",
  expired: "cookie.statusExpired",
  invalid: "cookie.statusInvalid",
};

export function cookieStatusMessageKey(status: CookieListItem["status"]): MessageKey {
  return COOKIE_STATUS_KEYS[status];
}

export function formatCookieValidationTime(
  value: string | null | undefined,
  locale: Locale,
): string {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(parsed);
}
