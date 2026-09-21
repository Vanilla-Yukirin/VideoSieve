"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/Button";
import { ProviderProfilesManager } from "@/components/ProviderProfilesManager";
import { api } from "@/lib/api/client";
import type { ProviderProfile } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { isProviderSetupComplete } from "@/lib/settings/providerSetup";

export default function SetupPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [profiles, setProfiles] = useState<ProviderProfile[]>([]);
  const [checking, setChecking] = useState(true);
  const [apiUnavailable, setApiUnavailable] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadProfiles = useCallback(async () => {
    const nextProfiles = await api.listProviderProfiles();
    setProfiles(nextProfiles);
  }, []);

  const checkSetup = useCallback(async () => {
    setChecking(true);
    setApiUnavailable(false);
    setError(null);
    try {
      const nextProfiles = await api.listProviderProfiles();
      setProfiles(nextProfiles);
      if (isProviderSetupComplete(nextProfiles)) {
        router.replace("/");
      }
    } catch {
      setApiUnavailable(true);
      setError(t("setup.apiUnavailable"));
    } finally {
      setChecking(false);
    }
  }, [router, t]);

  useEffect(() => {
    // The initial API read owns the loading state and completes asynchronously.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void checkSetup();
  }, [checkSetup]);

  if (checking) {
    return <main className="container mx-auto p-8 text-sm text-muted-foreground">{t("setup.checking")}</main>;
  }

  if (apiUnavailable) {
    return (
      <main className="container mx-auto max-w-lg space-y-4 p-6 md:p-10">
        <h1 className="text-2xl font-bold">{t("setup.title")}</h1>
        <p className="text-sm text-destructive">{error ?? t("setup.apiUnavailable")}</p>
        <Button type="button" onClick={() => void checkSetup()}>{t("setup.retry")}</Button>
      </main>
    );
  }

  const complete = isProviderSetupComplete(profiles);

  return (
    <main className="container mx-auto max-w-3xl space-y-6 p-6 md:p-10">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("setup.stepProviders")}</p>
        <h1 className="text-2xl font-bold">{t("setup.providerTitle")}</h1>
        <p className="text-sm text-muted-foreground">{t("setup.providerDesc")}</p>
      </div>

      <div className="rounded-md border border-border bg-muted/20 p-4 text-sm text-muted-foreground">
        <p>{t("setup.profileRequirement")}</p>
        <p className="mt-1">{t("setup.summaryOptional")}</p>
      </div>

      <ProviderProfilesManager profiles={profiles} onProfilesChange={loadProfiles} />

      <div className="sticky bottom-4 flex items-center justify-between gap-4 rounded-lg border border-border bg-background/95 p-4 shadow-lg backdrop-blur">
        <p className="text-sm text-muted-foreground">
          {complete ? t("setup.ready") : t("setup.missingProfiles")}
        </p>
        <Button type="button" disabled={!complete} onClick={() => router.replace("/")}>
          {t("setup.finish")}
        </Button>
      </div>
    </main>
  );
}
