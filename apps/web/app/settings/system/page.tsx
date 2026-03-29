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

  // Access control
  const [guestModeEnabled, setGuestModeEnabled] = useState(false);
  const [guestAllowCookieInput, setGuestAllowCookieInput] = useState(false);

  // VLM config (mutable)
  const [vlmBaseUrl, setVlmBaseUrl] = useState("");
  const [vlmModel, setVlmModel] = useState("");
  const [vlmConcurrency, setVlmConcurrency] = useState(5);
  const [vlmRpm, setVlmRpm] = useState(30);
  const [vlmPromptZh, setVlmPromptZh] = useState("");
  const [vlmPromptEn, setVlmPromptEn] = useState("");

  // VLM prompt defaults (read-only, for Reset button)
  const [vlmPromptZhDefault, setVlmPromptZhDefault] = useState("");
  const [vlmPromptEnDefault, setVlmPromptEnDefault] = useState("");

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
          setVlmBaseUrl(settings.vlm_base_url);
          setVlmModel(settings.vlm_model);
          setVlmConcurrency(settings.vlm_concurrency);
          setVlmRpm(settings.vlm_rpm);
          setVlmPromptZh(settings.vlm_frame_prompt_zh);
          setVlmPromptEn(settings.vlm_frame_prompt_en);
          setVlmPromptZhDefault(settings.vlm_frame_prompt_zh_default);
          setVlmPromptEnDefault(settings.vlm_frame_prompt_en_default);
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
        vlm_base_url: vlmBaseUrl,
        vlm_model: vlmModel,
        vlm_concurrency: vlmConcurrency,
        vlm_rpm: vlmRpm,
        vlm_frame_prompt_zh: vlmPromptZh,
        vlm_frame_prompt_en: vlmPromptEn,
      });
      setGuestModeEnabled(settings.guest_mode_enabled);
      setGuestAllowCookieInput(settings.guest_allow_cookie_input);
      setGuestAllowCookieInputCached(settings.guest_allow_cookie_input);
      setVlmBaseUrl(settings.vlm_base_url);
      setVlmModel(settings.vlm_model);
      setVlmConcurrency(settings.vlm_concurrency);
      setVlmRpm(settings.vlm_rpm);
      setVlmPromptZh(settings.vlm_frame_prompt_zh);
      setVlmPromptEn(settings.vlm_frame_prompt_en);
      setVlmPromptZhDefault(settings.vlm_frame_prompt_zh_default);
      setVlmPromptEnDefault(settings.vlm_frame_prompt_en_default);
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

      <form className="space-y-6" onSubmit={onSave}>
        {/* Access Controls */}
        <Card>
          <CardHeader>
            <CardTitle>{t("settings.access")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
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
          </CardContent>
        </Card>

        {/* VLM Config */}
        <Card>
          <CardHeader>
            <CardTitle>{t("settings.vlmSection")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1">
              <label className="block text-sm font-medium">{t("settings.vlmBaseUrl")}</label>
              <input
                type="text"
                className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm"
                value={vlmBaseUrl}
                onChange={(e) => setVlmBaseUrl(e.target.value)}
                disabled={saving}
              />
            </div>

            <div className="space-y-1">
              <label className="block text-sm font-medium">{t("settings.vlmModel")}</label>
              <input
                type="text"
                className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm"
                value={vlmModel}
                onChange={(e) => setVlmModel(e.target.value)}
                disabled={saving}
              />
            </div>

            <p className="text-xs text-muted-foreground">{t("settings.vlmApiKeyHint")}</p>

            <div className="flex gap-4">
              <div className="flex-1 space-y-1">
                <label className="block text-sm font-medium">{t("settings.vlmConcurrency")}</label>
                <input
                  type="number"
                  min={1}
                  className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm"
                  value={vlmConcurrency}
                  onChange={(e) => setVlmConcurrency(Math.max(1, parseInt(e.target.value, 10) || 1))}
                  disabled={saving}
                />
              </div>
              <div className="flex-1 space-y-1">
                <label className="block text-sm font-medium">{t("settings.vlmRpm")}</label>
                <input
                  type="number"
                  min={0}
                  className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm"
                  value={vlmRpm}
                  onChange={(e) => setVlmRpm(Math.max(0, parseInt(e.target.value, 10) || 0))}
                  disabled={saving}
                />
              </div>
            </div>

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="block text-sm font-medium">{t("settings.vlmPromptZh")}</label>
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground underline"
                  onClick={() => setVlmPromptZh(vlmPromptZhDefault)}
                  disabled={saving}
                >
                  {t("settings.vlmPromptReset")}
                </button>
              </div>
              <textarea
                rows={4}
                className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono resize-y"
                value={vlmPromptZh}
                onChange={(e) => setVlmPromptZh(e.target.value)}
                disabled={saving}
              />
            </div>

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="block text-sm font-medium">{t("settings.vlmPromptEn")}</label>
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground underline"
                  onClick={() => setVlmPromptEn(vlmPromptEnDefault)}
                  disabled={saving}
                >
                  {t("settings.vlmPromptReset")}
                </button>
              </div>
              <textarea
                rows={4}
                className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono resize-y"
                value={vlmPromptEn}
                onChange={(e) => setVlmPromptEn(e.target.value)}
                disabled={saving}
              />
            </div>
          </CardContent>
        </Card>

        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        {message ? <p className="text-sm text-green-700">{message}</p> : null}

        <Button type="submit" isLoading={saving}>
          {t("settings.save")}
        </Button>
      </form>
    </main>
  );
}
