"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiClientError, api } from "@/lib/api/client";
import { clearSessionToken, setGuestSessionActive, setSessionToken } from "@/lib/auth/session";
import { Button } from "@/components/Button";
import { useI18n } from "@/lib/i18n/I18nProvider";

export default function SetupPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [checking, setChecking] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const status = await api.getAuthBootstrapStatus();
        if (!status.bootstrap_required) {
          router.replace("/login");
          return;
        }
      } catch {
        // Keep setup form visible when backend is temporarily unavailable.
      } finally {
        if (!cancelled) setChecking(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError(t("setup.required"));
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api.bootstrapAuth({ username: username.trim(), password });
      clearSessionToken();
      setGuestSessionActive(false);
      setSessionToken(result.token);
      router.replace("/");
    } catch (unknownError) {
      if (unknownError instanceof ApiClientError && unknownError.code === "bootstrap_required") {
        setError(t("setup.already"));
        router.replace("/login");
      } else if (unknownError instanceof Error) {
        setError(unknownError.message);
      } else {
        setError(t("error.setupFailed"));
      }
    } finally {
      setLoading(false);
    }
  };

  if (checking) {
    return <main className="container mx-auto p-8 text-sm text-muted-foreground">{t("setup.checking")}</main>;
  }

  return (
    <main className="container mx-auto max-w-lg space-y-6 p-6 md:p-10">
      <div>
        <h1 className="text-2xl font-bold">{t("setup.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("setup.desc")}</p>
      </div>

      <form className="space-y-4" onSubmit={onSubmit}>
        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="setup-username">
            {t("setup.username")}
          </label>
          <input
            id="setup-username"
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={loading}
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="setup-password">
            {t("setup.password")}
          </label>
          <input
            id="setup-password"
            type="password"
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
          />
          <p className="text-xs text-muted-foreground">{t("setup.passwordHint")}</p>
        </div>

        {error ? <p className="text-sm text-destructive">{error}</p> : null}

        <Button type="submit" isLoading={loading}>
          {t("setup.submit")}
        </Button>
      </form>
    </main>
  );
}
