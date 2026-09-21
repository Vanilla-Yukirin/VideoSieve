"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { ApiClientError, api } from "@/lib/api/client";
import { useProjectIndex } from "@/lib/hooks/useProjectIndex";
import { Button } from "@/components/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/Card";
import { Badge } from "@/components/Badge";
import { ArrowLeft, PlayCircle, Clock, Trash2 } from "lucide-react";
import Link from "next/link";
import { IngestProbe } from "@/components/IngestProbe";
import { CookieListItem, DualAssetIngestParams } from "@/lib/api/types";
import { resolveDefaultCookieId } from "@/lib/cookies/helpers";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { ConfirmDialog } from "@/components/ConfirmDialog";

export default function ProjectDetail() {
  const { t } = useI18n();
  const params = useParams();
  const projectId = params.id as string;
  const router = useRouter();
  const { addProject, removeProject } = useProjectIndex();
  const [isCreatingJob, setIsCreatingJob] = useState(false);
  const [ingestParams, setIngestParams] = useState<DualAssetIngestParams | undefined>(undefined);
  const [summaryEnabled, setSummaryEnabled] = useState(false);
  const [selectedCookieId, setSelectedCookieId] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadContext, setUploadContext] = useState<string>("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeletingProject, setIsDeletingProject] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState<{
    forceCancelActive: boolean;
    description: string;
  } | null>(null);
  const { data: project, error: projectError } = useSWR(
    projectId ? `/projects/${projectId}` : null,
    () => api.getProject(projectId)
  );

  const { data: jobs, mutate: refreshJobs } = useSWR(
    projectId ? `/projects/${projectId}/jobs` : null,
    () => api.getProjectJobs(projectId)
  );

  const { data: cookies, error: cookiesError } = useSWR<CookieListItem[]>(
    "/cookies",
    () => api.listCookies()
  );

  const resolvedCookieId = selectedCookieId && (cookies ?? []).some((cookie) => cookie.id === selectedCookieId)
      ? selectedCookieId
      : resolveDefaultCookieId(cookies ?? []);

  // Auto-add to index on visit if valid
  useEffect(() => {
    if (project) addProject(project.project_id);
  }, [project, addProject]);

  useEffect(() => {
    if (
      projectError instanceof ApiClientError &&
      projectError.code === "not_found" &&
      !isDeletingProject
    ) {
      const timeoutId = window.setTimeout(() => {
        router.replace("/");
      }, 300);
      return () => window.clearTimeout(timeoutId);
    }
  }, [projectError, router, isDeletingProject]);

  const handleLocalUpload = (file: File, context: string) => {
    setUploadFile(file);
    setUploadContext(context);
  };

  const handleCreateJob = async () => {
    setIsCreatingJob(true);
    setCreateError(null);
    try {
      // Local upload mode
      if (uploadFile) {
        const formData = new FormData();
        formData.append("video", uploadFile);
        if (uploadContext.trim()) {
          formData.append("context", uploadContext.trim());
        }
        formData.append("summary_enabled", summaryEnabled.toString());

        const { job_id } = await api.uploadLocalVideo(projectId, formData);
        await refreshJobs();
        router.push(`/jobs/${job_id}`);
        return;
      }

      // Network URL mode
      const candidateIngest = ingestParams
        ? {
            ...ingestParams,
            ...(resolvedCookieId.trim() ? { cookie_id: resolvedCookieId.trim() } : {}),
          }
        : undefined;
      const { job_id } = await api.createJob({
        project_id: projectId,
        summary_enabled: summaryEnabled,
        ingest: candidateIngest,
      });
      await refreshJobs();
      router.push(`/jobs/${job_id}`);
    } catch (unknownError) {
      if (unknownError instanceof Error) {
        setCreateError(unknownError.message);
      } else {
        setCreateError(t("control.fail"));
      }
    } finally {
      setIsCreatingJob(false);
    }
  };

  const executeDeleteProject = async (forceCancelActive: boolean) => {
    setIsDeletingProject(true);
    setDeleteError(null);
    try {
      await api.deleteProject(projectId, forceCancelActive);
      try {
        removeProject(projectId);
      } finally {
        router.replace("/");
      }
    } catch (unknownError) {
      if (
        unknownError instanceof ApiClientError &&
        unknownError.code === "project_has_active_jobs" &&
        !forceCancelActive
      ) {
        const activeJobCount = unknownError.details?.active_job_ids?.length ?? 0;
        setDeleteConfirmation({
          forceCancelActive: true,
          description: t("project.confirmDeleteWithActive", { count: activeJobCount }),
        });
        return;
      }
      if (
        unknownError instanceof ApiClientError &&
        unknownError.code === "project_delete_pending_cancel"
      ) {
        setDeleteError(t("project.deletePendingCancel"));
        return;
      }
      if (
        unknownError instanceof ApiClientError &&
        unknownError.code === "project_delete_pending_cleanup"
      ) {
        setDeleteError(t("project.deletePendingCleanup"));
        return;
      }
      if (
        unknownError instanceof ApiClientError &&
        unknownError.code === "project_delete_in_progress"
      ) {
        setDeleteError(t("project.deleteInProgress"));
        return;
      }
      if (unknownError instanceof Error) {
        setDeleteError(unknownError.message);
        return;
      }
      setDeleteError(t("project.deleteFailed"));
    } finally {
      setIsDeletingProject(false);
    }
  };

  const handleDeleteProject = () => {
    if (isDeletingProject) {
      return;
    }
    setDeleteConfirmation({
      forceCancelActive: false,
      description: t("project.confirmDelete"),
    });
  };

  if (projectError) {
    return (
      <div className="container mx-auto p-8 text-center">
        <h1 className="text-2xl font-bold mb-4">{t("project.notFound")}</h1>
        <Link href="/">
            <Button variant="outline">{t("project.goBack")}</Button>
        </Link>
      </div>
    );
  }

  if (!project) {
    return <div className="p-8">{t("settings.load")}</div>;
  }

  return (
    <div className="container mx-auto p-4 md:p-8 space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div>
           <h1 className="text-2xl font-bold tracking-tight">{project.title}</h1>
           <p className="text-muted-foreground text-sm">{project.project_id}</p>
        </div>
        <div className="ml-auto">
             <Button
                variant="destructive"
                size="sm"
                onClick={handleDeleteProject}
                disabled={isDeletingProject}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                {t("project.delete")}
              </Button>
        </div>
        <div>
             <Badge variant={project.status === "running" ? "default" : "secondary"}>
                {project.status}
             </Badge>
        </div>
      </div>
      {deleteError ? <p className="text-sm text-destructive">{deleteError}</p> : null}

      <div className="grid gap-6">
        <Card className="border-2 border-primary/10">
            <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                    <PlayCircle className="h-5 w-5 text-primary" />
                    {t("project.newJob")}
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                <IngestProbe
                  onParamsReady={setIngestParams}
                  onLocalUpload={handleLocalUpload}
                  disabled={isCreatingJob}
                  cookieId={resolvedCookieId}
                />

                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="cookie-select">
                    {t("project.cookie")}
                  </label>
                  <select
                    id="cookie-select"
                    className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    value={resolvedCookieId}
                    onChange={(e) => setSelectedCookieId(e.target.value)}
                    disabled={isCreatingJob || Boolean(cookiesError)}
                  >
                    <option value="">{t("project.cookieNone")}</option>
                    {(cookies ?? []).map((cookie) => (
                      <option key={cookie.id} value={cookie.id}>
                        {cookie.name} ({cookie.status}){cookie.is_default ? t("project.cookieDefaultSuffix") : ""}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-foreground">
                    {t("project.cookieHint")}
                  </p>
                  {cookiesError ? (
                    <p className="text-xs text-amber-300">
                      {t("project.cookieUnavailable")}
                    </p>
                  ) : null}
                </div>

                {/* Summary toggle */}
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={summaryEnabled}
                    onChange={(e) => setSummaryEnabled(e.target.checked)}
                    disabled={isCreatingJob}
                    className="h-4 w-4 rounded border-input"
                  />
                  {t("project.summary")}
                </label>
                
                <div className="flex justify-end">
                    <Button
                        onClick={handleCreateJob}
                        isLoading={isCreatingJob}
                        disabled={(!ingestParams?.source_url && !uploadFile) || isDeletingProject}
                    >
                        {t("project.start")}
                    </Button>
                </div>
                {createError ? <p className="text-sm text-destructive">{createError}</p> : null}
            </CardContent>
        </Card>

        <div>
            <h2 className="text-xl font-semibold mb-4">{t("project.history")}</h2>
            <div className="space-y-4">
                {!jobs || jobs.length === 0 ? (
                    <div className="text-center py-10 text-muted-foreground border rounded-lg bg-muted/20">
                        {t("project.noJobs")}
                    </div>
                ) : (
                    jobs.slice().reverse().map(job => (
                        <Link href={`/jobs/${job.job_id}`} key={job.job_id} className="block group">
                            <Card className="group-hover:border-primary/50 transition-colors">
                                <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                                    <div className="space-y-1">
                                        <div className="flex items-center gap-2">
                                            <span className="font-mono font-medium">{job.job_id}</span>
                                            <Badge variant={
                                                job.status === "succeeded" ? "success" :
                                                job.status === "failed" ? "destructive" :
                                                job.status === "running" ? "default" : "secondary"
                                            }>{job.status}</Badge>
                                        </div>
                                        <div className="flex items-center text-xs text-muted-foreground gap-4">
                                            <span className="flex items-center"><Clock className="mr-1 h-3 w-3"/> {new Date(job.created_at).toLocaleString()}</span>
                                            {job.stage && <span>{t("project.stageLabel")}: {job.stage}</span>}
                                        </div>
                                    </div>
                                    {job.error_message && (
                                        <div className="text-destructive text-sm max-w-md truncate">
                                            {t("project.errorLabel")}: {job.error_message}
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </Link>
                    ))
                )}
            </div>
        </div>
      </div>
      {isDeletingProject ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80">
          <div className="rounded-lg border bg-card px-6 py-4 text-sm font-medium shadow-lg">
            {t("project.deleting")}
          </div>
        </div>
      ) : null}
      <ConfirmDialog
        open={deleteConfirmation !== null}
        title={t("project.delete")}
        description={deleteConfirmation?.description ?? ""}
        confirmLabel={t("project.delete")}
        cancelLabel={t("common.cancel")}
        busy={isDeletingProject}
        onCancel={() => setDeleteConfirmation(null)}
        onConfirm={() => {
          const forceCancelActive = deleteConfirmation?.forceCancelActive ?? false;
          setDeleteConfirmation(null);
          void executeDeleteProject(forceCancelActive);
        }}
      />
    </div>
  );
}
