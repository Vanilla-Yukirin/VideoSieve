"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/Card";
import { api } from "@/lib/api/client";
import type { SystemSettingsResponse } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import {
  buildProviderSetupPatch,
  isProviderSetupComplete,
  ProviderSetupValidationError,
  validateProviderSetup,
} from "@/lib/settings/providerSetup";

export default function SetupPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [apiUnavailable, setApiUnavailable] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [asrEndpoint, setAsrEndpoint] = useState("");
  const [asrToken, setAsrToken] = useState("");
  const [asrTokenConfigured, setAsrTokenConfigured] = useState(false);
  const [vlmBaseUrl, setVlmBaseUrl] = useState("");
  const [vlmModel, setVlmModel] = useState("");
  const [vlmApiKey, setVlmApiKey] = useState("");
  const [vlmApiKeyConfigured, setVlmApiKeyConfigured] = useState(false);
  const [summaryEnabled, setSummaryEnabled] = useState(false);
  const [summaryBaseUrl, setSummaryBaseUrl] = useState("");
  const [summaryModel, setSummaryModel] = useState("");
  const [summaryApiKey, setSummaryApiKey] = useState("");
  const [summaryApiKeyConfigured, setSummaryApiKeyConfigured] = useState(false);

  const applySettings = (settings: SystemSettingsResponse) => {
    setAsrEndpoint(settings.asr_endpoint);
    setAsrTokenConfigured(settings.asr_token_configured);
    setVlmBaseUrl(settings.vlm_base_url);
    setVlmModel(settings.vlm_model);
    setVlmApiKeyConfigured(settings.vlm_api_key_configured);
    setSummaryBaseUrl(settings.summary_base_url);
    setSummaryModel(settings.summary_model);
    setSummaryApiKeyConfigured(settings.summary_api_key_configured);
    setSummaryEnabled(settings.summary_api_key_configured);
  };

  const checkSetup = async () => {
    try {
      const settings = await api.getSystemSettings();
      if (isProviderSetupComplete(settings)) {
        router.replace("/");
        return;
      }
      applySettings(settings);
    } catch {
      setApiUnavailable(true);
      setError(t("setup.apiUnavailable"));
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    // The request owns the initial loading state; its state updates occur after API reads.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void checkSetup();
    // The initial status check is intentionally run once. Retry is explicit after failures.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const retrySetup = () => {
    setChecking(true);
    setApiUnavailable(false);
    setError(null);
    void checkSetup();
  };

  const providerValidationMessage = (code: ProviderSetupValidationError): string => {
    switch (code) {
      case "asr_endpoint_required":
        return t("setup.asrEndpointRequired");
      case "vlm_base_url_required":
        return t("setup.vlmBaseUrlRequired");
      case "vlm_model_required":
        return t("setup.vlmModelRequired");
      case "vlm_api_key_required":
        return t("setup.vlmApiKeyRequired");
      case "summary_base_url_required":
        return t("setup.summaryBaseUrlRequired");
      case "summary_model_required":
        return t("setup.summaryModelRequired");
      case "summary_api_key_required":
        return t("setup.summaryApiKeyRequired");
    }
  };

  const onProviderSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const values = {
      asrEndpoint,
      asrToken,
      vlmBaseUrl,
      vlmModel,
      vlmApiKey,
      vlmApiKeyConfigured,
      summaryEnabled,
      summaryBaseUrl,
      summaryModel,
      summaryApiKey,
      summaryApiKeyConfigured,
    };
    const validationError = validateProviderSetup(values);
    if (validationError) {
      setError(providerValidationMessage(validationError));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await api.patchSystemSettings(buildProviderSetupPatch(values));
      router.replace("/");
    } catch (unknownError) {
      setError(unknownError instanceof Error ? unknownError.message : t("settings.save"));
    } finally {
      setLoading(false);
    }
  };

  if (checking) {
    return <main className="container mx-auto p-8 text-sm text-muted-foreground">{t("setup.checking")}</main>;
  }

  if (apiUnavailable) {
    return (
      <main className="container mx-auto max-w-lg space-y-4 p-6 md:p-10">
        <h1 className="text-2xl font-bold">{t("setup.title")}</h1>
        <p className="text-sm text-destructive">{error ?? t("setup.apiUnavailable")}</p>
        <Button type="button" onClick={retrySetup}>
          {t("setup.retry")}
        </Button>
      </main>
    );
  }

  return (
    <main className="container mx-auto max-w-2xl space-y-6 p-6 md:p-10">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t("setup.stepProviders")}
        </p>
        <h1 className="text-2xl font-bold">{t("setup.providerTitle")}</h1>
        <p className="text-sm text-muted-foreground">{t("setup.providerDesc")}</p>
      </div>

      <form className="space-y-6" onSubmit={onProviderSubmit}>
        <Card>
          <CardHeader>
            <CardTitle>{t("settings.asrSection")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1">
              <label className="block text-sm font-medium" htmlFor="setup-asr-endpoint">
                {t("settings.asrEndpoint")}
              </label>
              <input
                id="setup-asr-endpoint"
                className="w-full rounded border border-border bg-background px-3 py-2 text-sm"
                value={asrEndpoint}
                onChange={(event) => setAsrEndpoint(event.target.value)}
                placeholder="ws://127.0.0.1:6016"
                disabled={loading}
              />
              <p className="text-xs text-muted-foreground">{t("settings.asrWebSocketHint")}</p>
            </div>
            <CredentialInput
              id="setup-asr-token"
              label={t("settings.asrToken")}
              value={asrToken}
              onChange={setAsrToken}
              configured={asrTokenConfigured}
              disabled={loading}
              optional
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("settings.vlmSection")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <TextInput id="setup-vlm-base-url" label={t("settings.vlmBaseUrl")} value={vlmBaseUrl} onChange={setVlmBaseUrl} disabled={loading} />
            <TextInput id="setup-vlm-model" label={t("settings.vlmModel")} value={vlmModel} onChange={setVlmModel} disabled={loading} />
            <CredentialInput id="setup-vlm-api-key" label={t("settings.vlmApiKey")} value={vlmApiKey} onChange={setVlmApiKey} configured={vlmApiKeyConfigured} disabled={loading} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("setup.summaryOptional")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={summaryEnabled} onChange={(event) => setSummaryEnabled(event.target.checked)} disabled={loading} />
              {t("setup.summaryEnable")}
            </label>
            {summaryEnabled ? (
              <>
                <TextInput id="setup-summary-base-url" label={t("settings.summaryBaseUrl")} value={summaryBaseUrl} onChange={setSummaryBaseUrl} disabled={loading} />
                <TextInput id="setup-summary-model" label={t("settings.summaryModel")} value={summaryModel} onChange={setSummaryModel} disabled={loading} />
                <CredentialInput id="setup-summary-api-key" label={t("settings.summaryApiKey")} value={summaryApiKey} onChange={setSummaryApiKey} configured={summaryApiKeyConfigured} disabled={loading} />
              </>
            ) : null}
          </CardContent>
        </Card>

        <p className="text-xs text-muted-foreground">{t("setup.savedNotVerified")}</p>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <Button type="submit" isLoading={loading}>{t("setup.finish")}</Button>
      </form>
    </main>
  );
}

function TextInput({ id, label, value, onChange, disabled }: { id: string; label: string; value: string; onChange: (value: string) => void; disabled: boolean }) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium" htmlFor={id}>{label}</label>
      <input id={id} className="w-full rounded border border-border bg-background px-3 py-2 text-sm" value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} />
    </div>
  );
}

function CredentialInput({ id, label, value, onChange, configured, disabled, optional = false }: { id: string; label: string; value: string; onChange: (value: string) => void; configured: boolean; disabled: boolean; optional?: boolean }) {
  const { t } = useI18n();
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-3">
        <label className="block text-sm font-medium" htmlFor={id}>{label}</label>
        <span className="text-xs text-muted-foreground">{configured ? t("settings.credentialConfigured") : t("settings.credentialNotConfigured")}</span>
      </div>
      <input id={id} type="password" autoComplete="new-password" className="w-full rounded border border-border bg-background px-3 py-2 text-sm" value={value} onChange={(event) => onChange(event.target.value)} placeholder={configured ? t("settings.credentialPlaceholder") : undefined} disabled={disabled} />
      <p className="text-xs text-muted-foreground">{optional ? t("settings.asrTokenHint") : t("settings.credentialKeepHint")}</p>
    </div>
  );
}
