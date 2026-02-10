"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ApiClientError, api } from "@/lib/api/client";
import {
  clearSessionToken,
  getSessionToken,
  setGuestAllowCookieInputCached,
} from "@/lib/auth/session";
import { Button } from "@/components/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/Card";
import { useI18n } from "@/lib/i18n/I18nProvider";

export default function SystemSettingsPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [guestModeEnabled, setGuestModeEnabled] = useState(false);
  const [guestAllowCookieInput, setGuestAllowCookieInput] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      const token = getSessionToken();
      if (!token) {
        router.replace("/login");
        return;
      }

      try {
        const settings = await api.getSystemSettings(token);
        if (!cancelled) {
          setGuestModeEnabled(settings.guest_mode_enabled);
          setGuestAllowCookieInput(settings.guest_allow_cookie_input);
          setGuestAllowCookieInputCached(settings.guest_allow_cookie_input);
        }
      } catch (unknownError) {
        if (unknownError instanceof ApiClientError && unknownError.code === "auth_required") {
          clearSessionToken();
          router.replace("/login");
          return;
        }
        if (!cancelled) {
          setError(unknownError instanceof Error ? unknownError.message : t("settings.load"));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const onSave = async (event: FormEvent) => {
    event.preventDefault();
    const token = getSessionToken();
    if (!token) {
      router.replace("/login");
      return;
    }

    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const settings = await api.patchSystemSettings(token, {
        guest_mode_enabled: guestModeEnabled,
        guest_allow_cookie_input: guestAllowCookieInput,
      });
      setGuestModeEnabled(settings.guest_mode_enabled);
      setGuestAllowCookieInput(settings.guest_allow_cookie_input);
      setGuestAllowCookieInputCached(settings.guest_allow_cookie_input);
      setMessage(t("settings.saved"));
    } catch (unknownError) {
      if (unknownError instanceof ApiClientError && unknownError.code === "auth_required") {
        clearSessionToken();
        router.replace("/login");
        return;
      }
      if (unknownError instanceof ApiClientError && unknownError.code === "guest_cookie_key_required") {
        setError(t("settings.guestCookieKeyRequired"));
      } else {
        setError(unknownError instanceof Error ? unknownError.message : t("settings.save"));
      }
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <main className="container mx-auto p-8 text-sm text-muted-foreground">{t("settings.load")}</main>;
  }

  return (
    <main className="container mx-auto max-w-2xl space-y-6 p-4 md:p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t("settings.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("settings.desc")}</p>
        </div>
        <Link href="/">
          <Button variant="outline">{t("settings.back")}</Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("settings.access")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={onSave}>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={guestModeEnabled}
                onChange={(e) => setGuestModeEnabled(e.target.checked)}
                disabled={saving}
              />
              {t("settings.guestMode")}
            </label>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={guestAllowCookieInput}
                onChange={(e) => setGuestAllowCookieInput(e.target.checked)}
                disabled={saving}
              />
              {t("settings.guestCookie")}
            </label>

            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            {message ? <p className="text-sm text-green-700">{message}</p> : null}

            <Button type="submit" isLoading={saving}>
              {t("settings.save")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
