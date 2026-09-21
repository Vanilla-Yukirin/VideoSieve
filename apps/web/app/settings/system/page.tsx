"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { Button } from "@/components/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/Card";
import { ProviderProfilesManager } from "@/components/ProviderProfilesManager";
import { api } from "@/lib/api/client";
import type { ProviderProfile, SystemSettingsPatchRequest } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

export default function SystemSettingsPage() {
  const { t } = useI18n();
  const [profiles, setProfiles] = useState<ProviderProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [vlmConcurrency, setVlmConcurrency] = useState(5);
  const [vlmRpm, setVlmRpm] = useState(30);
  const [vlmPromptZh, setVlmPromptZh] = useState("");
  const [vlmPromptEn, setVlmPromptEn] = useState("");
  const [vlmPromptZhDefault, setVlmPromptZhDefault] = useState("");
  const [vlmPromptEnDefault, setVlmPromptEnDefault] = useState("");
  const [summaryPromptZh, setSummaryPromptZh] = useState("");
  const [summaryPromptEn, setSummaryPromptEn] = useState("");
  const [summaryMaxInputChars, setSummaryMaxInputChars] = useState(24000);
  const [summaryPromptZhDefault, setSummaryPromptZhDefault] = useState("");
  const [summaryPromptEnDefault, setSummaryPromptEnDefault] = useState("");

  const loadProfiles = useCallback(async () => {
    setProfiles(await api.listProviderProfiles());
  }, []);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const [nextProfiles, settings] = await Promise.all([
          api.listProviderProfiles(),
          api.getSystemSettings(),
        ]);
        if (cancelled) return;
        setProfiles(nextProfiles);
        setVlmConcurrency(settings.vlm_concurrency);
        setVlmRpm(settings.vlm_rpm);
        setVlmPromptZh(settings.vlm_frame_prompt_zh);
        setVlmPromptEn(settings.vlm_frame_prompt_en);
        setVlmPromptZhDefault(settings.vlm_frame_prompt_zh_default);
        setVlmPromptEnDefault(settings.vlm_frame_prompt_en_default);
        setSummaryPromptZh(settings.summary_prompt_zh);
        setSummaryPromptEn(settings.summary_prompt_en);
        setSummaryMaxInputChars(settings.summary_max_input_chars);
        setSummaryPromptZhDefault(settings.summary_prompt_zh_default);
        setSummaryPromptEnDefault(settings.summary_prompt_en_default);
      } catch (unknownError) {
        if (!cancelled) setError(unknownError instanceof Error ? unknownError.message : t("settings.load"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [t]);

  const saveProcessingSettings = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);
    const patch: SystemSettingsPatchRequest = {
      vlm_concurrency: vlmConcurrency,
      vlm_rpm: vlmRpm,
      vlm_frame_prompt_zh: vlmPromptZh,
      vlm_frame_prompt_en: vlmPromptEn,
      summary_prompt_zh: summaryPromptZh,
      summary_prompt_en: summaryPromptEn,
      summary_max_input_chars: summaryMaxInputChars,
    };
    try {
      await api.patchSystemSettings(patch);
      setMessage(t("settings.saved"));
    } catch (unknownError) {
      setError(unknownError instanceof Error ? unknownError.message : t("settings.save"));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <main className="container mx-auto p-8 text-sm text-muted-foreground">{t("settings.load")}</main>;
  }

  return (
    <main className="container mx-auto max-w-3xl space-y-8 p-4 md:p-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{t("settings.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("settings.desc")}</p>
        </div>
        <Link href="/"><Button variant="outline">{t("settings.back")}</Button></Link>
      </div>

      <section className="space-y-3">
        <div>
          <h2 className="text-xl font-semibold">{t("providers.sectionTitle")}</h2>
          <p className="text-sm text-muted-foreground">{t("providers.sectionDescription")}</p>
        </div>
        <ProviderProfilesManager profiles={profiles} onProfilesChange={loadProfiles} />
      </section>

      <form className="space-y-6" onSubmit={saveProcessingSettings}>
        <div>
          <h2 className="text-xl font-semibold">{t("settings.processingTitle")}</h2>
          <p className="text-sm text-muted-foreground">{t("settings.processingDescription")}</p>
        </div>

        <Card>
          <CardHeader><CardTitle>{t("settings.vlmSection")}</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <NumberField label={t("settings.vlmConcurrency")} value={vlmConcurrency} min={1} onChange={setVlmConcurrency} disabled={saving} />
              <NumberField label={t("settings.vlmRpm")} value={vlmRpm} min={0} onChange={setVlmRpm} disabled={saving} />
            </div>
            <PromptField label={t("settings.vlmPromptZh")} value={vlmPromptZh} onChange={setVlmPromptZh} onReset={() => setVlmPromptZh(vlmPromptZhDefault)} resetLabel={t("settings.vlmPromptReset")} disabled={saving} />
            <PromptField label={t("settings.vlmPromptEn")} value={vlmPromptEn} onChange={setVlmPromptEn} onReset={() => setVlmPromptEn(vlmPromptEnDefault)} resetLabel={t("settings.vlmPromptReset")} disabled={saving} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>{t("settings.summarySection")}</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <NumberField label={t("settings.summaryMaxInputChars")} value={summaryMaxInputChars} min={1000} onChange={setSummaryMaxInputChars} disabled={saving} />
            <PromptField label={t("settings.summaryPromptZh")} value={summaryPromptZh} onChange={setSummaryPromptZh} onReset={() => setSummaryPromptZh(summaryPromptZhDefault)} resetLabel={t("settings.vlmPromptReset")} disabled={saving} />
            <PromptField label={t("settings.summaryPromptEn")} value={summaryPromptEn} onChange={setSummaryPromptEn} onReset={() => setSummaryPromptEn(summaryPromptEnDefault)} resetLabel={t("settings.vlmPromptReset")} disabled={saving} />
          </CardContent>
        </Card>

        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        {message ? <p className="text-sm text-emerald-300">{message}</p> : null}
        <Button type="submit" isLoading={saving}>{t("settings.save")}</Button>
      </form>
    </main>
  );
}

function NumberField({ label, value, min, onChange, disabled }: { label: string; value: number; min: number; onChange: (value: number) => void; disabled: boolean }) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium">{label}</label>
      <input type="number" min={min} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={value} onChange={(event) => onChange(Math.max(min, Number(event.target.value) || min))} disabled={disabled} />
    </div>
  );
}

function PromptField({ label, value, onChange, onReset, resetLabel, disabled }: { label: string; value: string; onChange: (value: string) => void; onReset: () => void; resetLabel: string; disabled: boolean }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-3">
        <label className="text-sm font-medium">{label}</label>
        <button type="button" className="text-xs text-muted-foreground underline hover:text-foreground" onClick={onReset} disabled={disabled}>{resetLabel}</button>
      </div>
      <textarea rows={4} className="w-full resize-y rounded-md border border-input bg-background px-3 py-2 font-mono text-sm" value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} />
    </div>
  );
}
