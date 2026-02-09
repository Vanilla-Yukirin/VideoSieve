import { CookieListItem } from "../api/types";

export function resolveDefaultCookieId(cookies: CookieListItem[]): string {
  if (!cookies.length) {
    return "";
  }
  const defaultCookie = cookies.find((cookie) => cookie.is_default);
  return defaultCookie?.id ?? cookies[0].id;
}
