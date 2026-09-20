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

type AsrProvider = "unconfigured" | "capswriter";
type AsrTransport = "websocket" | "http";

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

  // External ASR routing. The optional token stays in the server environment.
  const [asrProvider, setAsrProvider] = useState<AsrProvider>("unconfigured");
  const [asrTransport, setAsrTransport] = useState<AsrTransport>("websocket");
  const [asrEndpoint, setAsrEndpoint] = useState("");
  const [asrLanguage, setAsrLanguage] = useState("auto");
  const [asrContext, setAsrContext] = useState("");
  const [asrTimeoutSeconds, setAsrTimeoutSeconds] = useState(900);
  const [asrTokenConfigured, setAsrTokenConfigured] = useState(false);

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

  // Overall summary uses a separate text-model endpoint and credential.
  const [summaryBaseUrl, setSummaryBaseUrl] = useState("");
  const [summaryModel, setSummaryModel] = useState("");
  const [summaryPromptZh, setSummaryPromptZh] = useState("");
  const [summaryPromptEn, setSummaryPromptEn] = useState("");
  const [summaryMaxInputChars, setSummaryMaxInputChars] = useState(24000);
  const [summaryPromptZhDefault, setSummaryPromptZhDefault] = useState("");
  const [summaryPromptEnDefault, setSummaryPromptEnDefault] = useState("");

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
          setAsrProvider(settings.asr_provider);
          setAsrTransport(settings.asr_transport);
          setAsrEndpoint(settings.asr_endpoint);
          setAsrLanguage(settings.asr_language);
          setAsrContext(settings.asr_context);
          setAsrTimeoutSeconds(settings.asr_timeout_seconds);
          setAsrTokenConfigured(settings.asr_token_configured);
          setVlmBaseUrl(settings.vlm_base_url);
          setVlmModel(settings.vlm_model);
          setVlmConcurrency(settings.vlm_concurrency);
          setVlmRpm(settings.vlm_rpm);
          setVlmPromptZh(settings.vlm_frame_prompt_zh);
          setVlmPromptEn(settings.vlm_frame_prompt_en);
          setVlmPromptZhDefault(settings.vlm_frame_prompt_zh_default);
          setVlmPromptEnDefault(settings.vlm_frame_prompt_en_default);
          setSummaryBaseUrl(settings.summary_base_url);
          setSummaryModel(settings.summary_model);
          setSummaryPromptZh(settings.summary_prompt_zh);
          setSummaryPromptEn(settings.summary_prompt_en);
          setSummaryMaxInputChars(settings.summary_max_input_chars);
          setSummaryPromptZhDefault(settings.summary_prompt_zh_default);
          setSummaryPromptEnDefault(settings.summary_prompt_en_default);
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
  }, [router, t]);

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
        asr_provider: asrProvider,
        asr_transport: asrTransport,
        asr_endpoint: asrEndpoint,
        asr_language: asrLanguage,
        asr_context: asrContext,
        asr_timeout_seconds: asrTimeoutSeconds,
        vlm_base_url: vlmBaseUrl,
        vlm_model: vlmModel,
        vlm_concurrency: vlmConcurrency,
        vlm_rpm: vlmRpm,
        vlm_frame_prompt_zh: vlmPromptZh,
        vlm_frame_prompt_en: vlmPromptEn,
        summary_base_url: summaryBaseUrl,
        summary_model: summaryModel,
        summary_prompt_zh: summaryPromptZh,
        summary_prompt_en: summaryPromptEn,
        summary_max_input_chars: summaryMaxInputChars,
      });
      setGuestModeEnabled(settings.guest_mode_enabled);
      setGuestAllowCookieInput(settings.guest_allow_cookie_input);
      setGuestAllowCookieInputCached(settings.guest_allow_cookie_input);
      setAsrProvider(settings.asr_provider);
      setAsrTransport(settings.asr_transport);
      setAsrEndpoint(settings.asr_endpoint);
      setAsrLanguage(settings.asr_language);
      setAsrContext(settings.asr_context);
      setAsrTimeoutSeconds(settings.asr_timeout_seconds);
      setAsrTokenConfigured(settings.asr_token_configured);
      setVlmBaseUrl(settings.vlm_base_url);
      setVlmModel(settings.vlm_model);
      setVlmConcurrency(settings.vlm_concurrency);
      setVlmRpm(settings.vlm_rpm);
      setVlmPromptZh(settings.vlm_frame_prompt_zh);
      setVlmPromptEn(settings.vlm_frame_prompt_en);
      setVlmPromptZhDefault(settings.vlm_frame_prompt_zh_default);
      setVlmPromptEnDefault(settings.vlm_frame_prompt_en_default);
      setSummaryBaseUrl(settings.summary_base_url);
      setSummaryModel(settings.summary_model);
      setSummaryPromptZh(settings.summary_prompt_zh);
      setSummaryPromptEn(settings.summary_prompt_en);
      setSummaryMaxInputChars(settings.summary_max_input_chars);
      setSummaryPromptZhDefault(settings.summary_prompt_zh_default);
      setSummaryPromptEnDefault(settings.summary_prompt_en_default);
      setMessage(t("settings.saved"));
    } catch (unknownError) {
      if (unknownError instanceof ApiClientError && unknownError.code === "auth_required") {
        clearSessionToken();
        router.replace("/login");
        return;
      }
      if (unknownError instanceof ApiClientError && unknownError.code === "guest_cookie_key_required") {
        setError(t("settings.guestCookieKeyRequired"));
      } else if (
        unknownError instanceof ApiClientError &&
        unknownError.code === "asr_endpoint_required"
      ) {
        setError(t("settings.asrEndpointRequired"));
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

        {/* External ASR */}
        <Card>
          <CardHeader>
            <CardTitle>{t("settings.asrSection")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs text-muted-foreground">{t("settings.asrDescription")}</p>

            <div className="space-y-1">
              <label className="block text-sm font-medium">{t("settings.asrProvider")}</label>
              <select
                className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm"
                value={asrProvider}
                onChange={(event) => setAsrProvider(event.target.value as AsrProvider)}
                disabled={saving}
              >
                <option value="unconfigured">{t("settings.asrProviderUnconfigured")}</option>
                <option value="capswriter">{t("settings.asrProviderCapsWriter")}</option>
              </select>
            </div>

            {asrProvider === "capswriter" ? (
              <>
                <div className="space-y-1">
                  <label className="block text-sm font-medium">{t("settings.asrTransport")}</label>
                  <select
                    className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm"
                    value={asrTransport}
                    onChange={(event) => setAsrTransport(event.target.value as AsrTransport)}
                    disabled={saving}
                  >
                    <option value="websocket">{t("settings.asrTransportWebSocket")}</option>
                    <option value="http">{t("settings.asrTransportHttp")}</option>
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="block text-sm font-medium">{t("settings.asrEndpoint")}</label>
                  <input
                    type="text"
                    className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm"
                    value={asrEndpoint}
                    onChange={(event) => setAsrEndpoint(event.target.value)}
                    placeholder={
                      asrTransport === "websocket"
                        ? "ws://capswriter:6016"
                        : "http://capswriter:6018/v1/transcriptions"
                    }
                    disabled={saving}
                  />
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1">
                    <label className="block text-sm font-medium">{t("settings.asrLanguage")}</label>
                    <input
                      type="text"
                      className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm"
                      value={asrLanguage}
                      onChange={(event) => setAsrLanguage(event.target.value)}
                      disabled={saving}
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="block text-sm font-medium">{t("settings.asrTimeout")}</label>
                    <input
                      type="number"
                      min={1}
                      className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm"
                      value={asrTimeoutSeconds}
                      onChange={(event) =>
                        setAsrTimeoutSeconds(Math.max(1, parseInt(event.target.value, 10) || 1))
                      }
                      disabled={saving}
                    />
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="block text-sm font-medium">{t("settings.asrContext")}</label>
                  <textarea
                    rows={3}
                    maxLength={2000}
                    className="w-full resize-y rounded border border-border bg-background px-3 py-1.5 text-sm"
                    value={asrContext}
                    onChange={(event) => setAsrContext(event.target.value)}
                    disabled={saving}
                  />
                </div>

                <p className="text-xs text-muted-foreground">
                  {t("settings.asrTokenHint")} {" "}
                  {asrTokenConfigured
                    ? t("settings.asrTokenConfigured")
                    : t("settings.asrTokenNotConfigured")}
                </p>
              </>
            ) : (
              <p className="text-xs text-muted-foreground">{t("settings.asrUnconfiguredHint")}</p>
            )}
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

        <Card>
          <CardHeader>
            <CardTitle>{t("settings.summarySection")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1">
              <label className="block text-sm font-medium">{t("settings.summaryBaseUrl")}</label>
              <input
                type="text"
                className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm"
                value={summaryBaseUrl}
                onChange={(event) => setSummaryBaseUrl(event.target.value)}
                disabled={saving}
              />
            </div>

            <div className="space-y-1">
              <label className="block text-sm font-medium">{t("settings.summaryModel")}</label>
              <input
                type="text"
                className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm"
                value={summaryModel}
                onChange={(event) => setSummaryModel(event.target.value)}
                disabled={saving}
              />
            </div>

            <p className="text-xs text-muted-foreground">{t("settings.summaryApiKeyHint")}</p>

            <div className="space-y-1">
              <label className="block text-sm font-medium">
                {t("settings.summaryMaxInputChars")}
              </label>
              <input
                type="number"
                min={1000}
                className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm"
                value={summaryMaxInputChars}
                onChange={(event) =>
                  setSummaryMaxInputChars(Math.max(1000, parseInt(event.target.value, 10) || 1000))
                }
                disabled={saving}
              />
            </div>

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="block text-sm font-medium">{t("settings.summaryPromptZh")}</label>
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground underline"
                  onClick={() => setSummaryPromptZh(summaryPromptZhDefault)}
                  disabled={saving}
                >
                  {t("settings.vlmPromptReset")}
                </button>
              </div>
              <textarea
                rows={4}
                className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono resize-y"
                value={summaryPromptZh}
                onChange={(event) => setSummaryPromptZh(event.target.value)}
                disabled={saving}
              />
            </div>

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="block text-sm font-medium">{t("settings.summaryPromptEn")}</label>
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground underline"
                  onClick={() => setSummaryPromptEn(summaryPromptEnDefault)}
                  disabled={saving}
                >
                  {t("settings.vlmPromptReset")}
                </button>
              </div>
              <textarea
                rows={4}
                className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm font-mono resize-y"
                value={summaryPromptEn}
                onChange={(event) => setSummaryPromptEn(event.target.value)}
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
