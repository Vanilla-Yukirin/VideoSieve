"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { ApiClientError, api } from "@/lib/api/client";
import { useProjectIndex } from "@/lib/hooks/useProjectIndex";
import { Button } from "@/components/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/Card";
import { Badge } from "@/components/Badge";
import { ArrowLeft, PlayCircle, Clock } from "lucide-react";
import Link from "next/link";
import { IngestProbe } from "@/components/IngestProbe";
import { CookieListItem, DualAssetIngestParams, GuestCooldownResponse } from "@/lib/api/types";
import { resolveDefaultCookieId } from "@/lib/cookies/helpers";
import {
  isGuestCookieInputDisabled,
  isGuestCooldownBlocking,
  sanitizeIngestForSubmit,
} from "@/lib/auth/helpers";
import {
  getGuestAllowCookieInputCached,
  getSessionToken,
  setGuestAllowCookieInputCached,
} from "@/lib/auth/session";
import { useI18n } from "@/lib/i18n/I18nProvider";

export default function ProjectDetail() {
  const { t } = useI18n();
  const params = useParams();
  const projectId = params.id as string;
  const router = useRouter();
  const { addProject } = useProjectIndex();
  const [isCreatingJob, setIsCreatingJob] = useState(false);
  const [ingestParams, setIngestParams] = useState<DualAssetIngestParams | undefined>(undefined);
  const [summaryEnabled, setSummaryEnabled] = useState(false);
  const [selectedCookieId, setSelectedCookieId] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [guestCooldown, setGuestCooldown] = useState<GuestCooldownResponse | null>(null);
  const [guestAllowCookieInput, setGuestAllowCookieInput] = useState<boolean>(
    getGuestAllowCookieInputCached(),
  );

  const sessionToken = getSessionToken();
  const isGuest = !sessionToken;
  const guestCookieDisabled = isGuestCookieInputDisabled(isGuest, guestAllowCookieInput);

  const { data: project, error: projectError } = useSWR(
    projectId ? `/projects/${projectId}` : null,
    () => api.getProject(projectId)
  );

  const { data: jobs, mutate: refreshJobs } = useSWR(
    projectId ? `/projects/${projectId}/jobs` : null,
    () => api.getProjectJobs(projectId)
  );

  const { data: cookies, error: cookiesError } = useSWR<CookieListItem[]>(
    guestCookieDisabled ? null : "/me/cookies",
    () => api.listMeCookies()
  );

  useEffect(() => {
    let cancelled = false;
    const loadPolicy = async () => {
      if (!sessionToken) {
        setGuestAllowCookieInput(getGuestAllowCookieInputCached());
        return;
      }
      try {
        const settings = await api.getSystemSettings(sessionToken);
        if (!cancelled) {
          setGuestAllowCookieInput(settings.guest_allow_cookie_input);
          setGuestAllowCookieInputCached(settings.guest_allow_cookie_input);
        }
      } catch (unknownError) {
        if (
          unknownError instanceof ApiClientError &&
          unknownError.code === "auth_required"
        ) {
          router.replace("/login");
          return;
        }
        if (!cancelled) {
          setGuestAllowCookieInput(getGuestAllowCookieInputCached());
        }
      }
    };

    void loadPolicy();
    return () => {
      cancelled = true;
    };
  }, [sessionToken, router]);

  useEffect(() => {
    if (guestCookieDisabled) {
      setSelectedCookieId("");
      return;
    }
    if (!cookies || cookies.length === 0) {
      setSelectedCookieId("");
      return;
    }
    const hasSelected = cookies.some((cookie) => cookie.id === selectedCookieId);
    if (!selectedCookieId || !hasSelected) {
      setSelectedCookieId(resolveDefaultCookieId(cookies));
    }
  }, [cookies, selectedCookieId, guestCookieDisabled]);

  useEffect(() => {
    if (!isGuest) {
      setGuestCooldown(null);
      return;
    }

    let cancelled = false;
    const refreshCooldown = async () => {
      try {
        const result = await api.getGuestCooldown();
        if (!cancelled) {
          setGuestCooldown(result);
        }
      } catch {
        if (!cancelled) {
          setGuestCooldown(null);
        }
      }
    };

    void refreshCooldown();
    const intervalId = setInterval(() => {
      void refreshCooldown();
    }, 1000);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [isGuest]);

  // Auto-add to index on visit if valid
  useEffect(() => {
    if (project) addProject(project.project_id);
  }, [project, addProject]);

  const handleCreateJob = async () => {
    setIsCreatingJob(true);
    setCreateError(null);
    try {
      const candidateIngest = ingestParams
        ? {
            ...ingestParams,
            ...(selectedCookieId.trim() ? { cookie_id: selectedCookieId.trim() } : {}),
          }
        : undefined;
      const ingestWithCookie = sanitizeIngestForSubmit(candidateIngest, {
        isGuest,
        guestAllowCookieInput,
      });

      const { job_id } = await api.createJob({
        project_id: projectId,
        summary_enabled: summaryEnabled,
        ingest: ingestWithCookie,
      }, sessionToken);
      await refreshJobs();
      router.push(`/jobs/${job_id}`);
    } catch (unknownError) {
      if (unknownError instanceof ApiClientError && unknownError.code === "auth_required") {
        setCreateError(t("project.authRequired"));
        router.replace("/login");
      } else if (
        unknownError instanceof ApiClientError &&
        unknownError.code === "guest_cooldown_active"
      ) {
        const remaining = unknownError.details?.remaining_seconds ?? guestCooldown?.remaining_seconds ?? 0;
        setCreateError(t("project.cooldownActive", { seconds: remaining }));
        setGuestCooldown({
          active: true,
          remaining_seconds: remaining,
          cooldown_seconds: guestCooldown?.cooldown_seconds ?? remaining,
        });
      } else if (unknownError instanceof Error) {
        setCreateError(unknownError.message);
      } else {
        setCreateError(t("control.fail"));
      }
    } finally {
      setIsCreatingJob(false);
    }
  };

  const isGuestCooldownActive = isGuestCooldownBlocking(isGuest, guestCooldown);

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
             <Badge variant={project.status === "running" ? "default" : "secondary"}>
                {project.status}
            </Badge>
        </div>
      </div>

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
                  disabled={isCreatingJob}
                  cookieId={guestCookieDisabled ? undefined : selectedCookieId}
                />

                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="cookie-select">
                    {t("project.cookie")}
                  </label>
                  <select
                    id="cookie-select"
                    className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    value={selectedCookieId}
                    onChange={(e) => setSelectedCookieId(e.target.value)}
                    disabled={isCreatingJob || Boolean(cookiesError) || guestCookieDisabled}
                  >
                    <option value="">{t("project.cookieNone")}</option>
                    {(cookies ?? []).map((cookie) => (
                      <option key={cookie.id} value={cookie.id}>
                        {cookie.name} ({cookie.status}){cookie.is_default ? t("project.cookieDefaultSuffix") : ""}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-foreground">
                    {t("project.cookieNeedLogin")}
                  </p>
                  {guestCookieDisabled ? (
                    <p className="text-xs text-amber-700">
                      {t("project.cookieDisabled")}
                    </p>
                  ) : null}
                  {cookiesError ? (
                    <p className="text-xs text-amber-700">
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
                        disabled={!ingestParams?.source_url || isGuestCooldownActive}
                    >
                        {isGuestCooldownActive
                          ? t("project.cooldown", { seconds: guestCooldown?.remaining_seconds ?? 0 })
                          : t("project.start")}
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
    </div>
  );
}
