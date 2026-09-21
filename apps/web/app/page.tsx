"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PlusCircle } from "lucide-react";

import { Button } from "@/components/Button";
import { ProjectCard } from "@/components/ProjectCard";
import { api } from "@/lib/api/client";
import { useProjectIndex } from "@/lib/hooks/useProjectIndex";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { isProviderSetupComplete } from "@/lib/settings/providerSetup";
import { useToast } from "@/lib/toast/ToastProvider";

export default function Home() {
  const { t } = useI18n();
  const { pushToast } = useToast();
  const router = useRouter();
  const { projectIds, addProject, removeProject, isLoaded, loadError } = useProjectIndex();
  const [isCreating, setIsCreating] = useState(false);
  const [isCheckingSetup, setIsCheckingSetup] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const profiles = await api.listProviderProfiles();
        if (!isProviderSetupComplete(profiles)) {
          router.replace("/setup");
          return;
        }
      } catch {
        router.replace("/setup");
        return;
      } finally {
        if (!cancelled) {
          setIsCheckingSetup(false);
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
      router.push(`/projects/${project_id}`);
    } catch (error) {
      pushToast({ level: "error", message: t("error.createProject") });
      console.error(error);
    } finally {
      setIsCreating(false);
    }
  };

  if (!isLoaded || isCheckingSetup) {
    return <main className="container mx-auto p-8 text-sm text-muted-foreground">{t("setup.checking")}</main>;
  }

  return (
    <main className="space-y-8 px-2 md:px-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight md:text-4xl">{t("home.title")}</h1>
          <p className="mt-1 text-muted-foreground">{t("home.subtitle")}</p>
        </div>
        <Button onClick={handleCreate} isLoading={isCreating}>
          <PlusCircle className="mr-2 h-4 w-4" /> {t("home.newProject")}
        </Button>
      </div>

      <div className="rounded-md border bg-muted/20 p-3 text-sm">{t("home.cookieHint")}</div>

      {loadError ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {t("home.projectListLoadFailed")}
        </div>
      ) : null}

      {projectIds.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed py-20 text-center">
          <p className="mb-4 text-muted-foreground">{t("home.empty")}</p>
          <Button onClick={handleCreate} isLoading={isCreating}>{t("home.createFirst")}</Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {projectIds.map((id) => (
            <ProjectCard key={id} projectId={id} onRemove={removeProject} />
          ))}
        </div>
      )}
    </main>
  );
}
