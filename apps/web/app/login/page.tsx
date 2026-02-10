"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiClientError, api } from "@/lib/api/client";
import {
  clearSessionToken,
  getSessionToken,
  setGuestSessionActive,
  setSessionToken,
} from "@/lib/auth/session";
import { canShowGuestEntry } from "@/lib/auth/helpers";
import { Button } from "@/components/Button";
import { useI18n } from "@/lib/i18n/I18nProvider";

export default function LoginPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [guestLoading, setGuestLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [guestModeEnabled, setGuestModeEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const bootstrap = await api.getAuthBootstrapStatus();
        if (bootstrap.bootstrap_required) {
          router.replace("/setup");
          return;
        }

        const token = getSessionToken();
        if (token) {
          try {
            await api.getAuthMe(token);
            router.replace("/");
            return;
          } catch {
            clearSessionToken();
          }
        }

        const flags = await api.getPublicAccessFlags();
        if (!cancelled) {
          setGuestModeEnabled(canShowGuestEntry(flags));
        }
      } catch {
        if (!cancelled) {
          setGuestModeEnabled(false);
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const onLogin = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError(t("login.required"));
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await api.loginAuth({ username: username.trim(), password });
      setGuestSessionActive(false);
      setSessionToken(response.token);
      router.replace("/");
    } catch (unknownError) {
      if (unknownError instanceof ApiClientError && unknownError.code === "invalid_credentials") {
        setError(t("login.invalid"));
      } else if (unknownError instanceof ApiClientError && unknownError.code === "bootstrap_required") {
        setError(t("login.setupFirst"));
        router.replace("/setup");
      } else if (unknownError instanceof Error) {
        setError(unknownError.message);
      } else {
        setError(t("error.loginFailed"));
      }
    } finally {
      setLoading(false);
    }
  };

  const onGuestEnter = async () => {
    setGuestLoading(true);
    setError(null);
    try {
      const flags = await api.getPublicAccessFlags();
      if (!canShowGuestEntry(flags)) {
        setError(t("login.guestDisabled"));
        return;
      }
      clearSessionToken();
      setGuestSessionActive(true);
      router.replace("/");
    } catch (unknownError) {
      if (unknownError instanceof Error) {
        setError(unknownError.message);
      } else {
        setError(t("login.guestEnterFail"));
      }
    } finally {
      setGuestLoading(false);
    }
  };

  return (
    <main className="container mx-auto max-w-lg space-y-6 p-6 md:p-10">
      <div>
        <h1 className="text-2xl font-bold">{t("login.title")}</h1>
        <p className="text-sm text-muted-foreground">{t("login.desc")}</p>
      </div>

      <form className="space-y-4" onSubmit={onLogin}>
        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="login-username">
            {t("login.username")}
          </label>
          <input
            id="login-username"
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={loading || guestLoading}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="login-password">
            {t("login.password")}
          </label>
          <input
            id="login-password"
            type="password"
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading || guestLoading}
          />
        </div>

        {error ? <p className="text-sm text-destructive">{error}</p> : null}

        <div className="flex flex-wrap gap-2">
          <Button type="submit" isLoading={loading}>
            {t("login.submit")}
          </Button>
          {guestModeEnabled ? (
            <Button type="button" variant="outline" onClick={onGuestEnter} isLoading={guestLoading}>
              {t("login.guest")}
            </Button>
          ) : null}
        </div>
      </form>
    </main>
  );
}
