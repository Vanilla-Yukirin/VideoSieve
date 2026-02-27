"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api/client";
import { useProjectIndex } from "@/lib/hooks/useProjectIndex";
import { Button } from "@/components/Button";
import { ProjectCard } from "@/components/ProjectCard";
import { LogOut, PlusCircle } from "lucide-react";
import {
  clearSessionToken,
  getSessionToken,
  isGuestSessionActive,
  setGuestSessionActive,
} from "@/lib/auth/session";
import { resolveLandingRoute } from "@/lib/auth/helpers";
import { ApiClientError } from "@/lib/api/client";
import { useI18n } from "@/lib/i18n/I18nProvider";

export default function Home() {
  const { t } = useI18n();
  const router = useRouter();
  const { projectIds, addProject, removeProject, isLoaded } = useProjectIndex();
  const [isCreating, setIsCreating] = useState(false);
  const [isCheckingAccess, setIsCheckingAccess] = useState(true);
  const [isGuest, setIsGuest] = useState(false);
  const runtimeMode = api.getRuntimeMode();

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const bootstrap = await api.getAuthBootstrapStatus();
        const token = getSessionToken();
        const hasToken = Boolean(token);
        let tokenValid = false;

        if (hasToken) {
          try {
            await api.getAuthMe(token);
            tokenValid = true;
            setGuestSessionActive(false);
          } catch {
            clearSessionToken();
            tokenValid = false;
          }
        }

        const target = resolveLandingRoute({
          bootstrapRequired: bootstrap.bootstrap_required,
          hasToken,
          tokenValid,
          guestSessionActive: isGuestSessionActive(),
        });

        if (target !== "/") {
          router.replace(target);
          return;
        }

        if (!cancelled) {
          setIsGuest(!tokenValid);
        }
      } catch {
        router.replace("/login");
        return;
      } finally {
        if (!cancelled) {
          setIsCheckingAccess(false);
        }
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const handleCreate = async () => {
    setIsCreating(true);
    try {
      const { project_id } = await api.createProject({
        title: `${t("home.newProjectTitlePrefix")} ${new Date().toISOString()}`,
      });
      addProject(project_id);
    } catch (e) {
      alert(t("error.createProject"));
      console.error(e);
    } finally {
      setIsCreating(false);
    }
  };

  const handleLeaveGuest = () => {
    setGuestSessionActive(false);
    router.replace("/login");
  };

  const handleLogout = async () => {
    const token = getSessionToken();
    try {
      await api.logoutAuth(token);
    } catch (unknownError) {
      if (!(unknownError instanceof ApiClientError) || unknownError.code !== "auth_required") {
        console.error(unknownError);
      }
    } finally {
      clearSessionToken();
      setGuestSessionActive(false);
      router.replace("/login");
    }
  };

  if (!isLoaded || isCheckingAccess) {
    return <main className="container mx-auto p-8 text-sm text-muted-foreground">{t("setup.checking")}</main>;
  }

  return (
    <main className="space-y-8 px-2 md:px-4">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight md:text-4xl">{t("home.title")}</h1>
          <p className="text-muted-foreground mt-1">
            {isGuest
              ? t("home.subtitle.guest")
              : t("home.subtitle.user")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={handleCreate} isLoading={isCreating}>
            <PlusCircle className="mr-2 h-4 w-4" /> {t("home.newProject")}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={isGuest ? handleLeaveGuest : handleLogout}
          >
            <LogOut className="mr-2 h-4 w-4" /> {isGuest ? t("home.leaveGuest") : t("home.logout")}
          </Button>
        </div>
      </div>

      <div className="rounded-md border bg-muted/20 p-3 text-sm">
        {t("home.cookieHint")}
      </div>

      {runtimeMode === "mock" ? (
        <div className="rounded-lg border border-amber-400/50 bg-amber-400/12 p-3 text-sm text-amber-200">
          {t("home.mockMode")}
        </div>
      ) : null}

      {projectIds.length === 0 ? (
        <div className="text-center py-20 border-2 border-dashed rounded-lg">
          <p className="text-muted-foreground mb-4">{t("home.empty")}</p>
          <Button onClick={handleCreate} isLoading={isCreating}>{t("home.createFirst")}</Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {projectIds.map(id => (
                <ProjectCard key={id} projectId={id} onRemove={removeProject} />
            ))}
        </div>
      )}
    </main>
  );
}
