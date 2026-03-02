"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useJobRealtime } from "@/lib/hooks/useJobRealtime";
import { LogViewer } from "@/components/LogViewer";
import { ControlPanel } from "@/components/ControlPanel";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/Card";
import {
  ArrowLeft,
  Wifi,
  WifiOff,
  FileText,
  Download,
  Image as ImageIcon,
  Copy,
  X,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { ApiClientError, api } from "@/lib/api/client";
import { useToast } from "@/lib/toast/ToastProvider";

function encodeArtifactPath(path: string): string {
  return path
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

export default function JobDetail() {
  const { t } = useI18n();
  const { pushToast } = useToast();
  const router = useRouter();
  const params = useParams();
  const jobId = params.id as string;
  const state = useJobRealtime(jobId);

  // Calculate generic progress bar color
  const progressColor = 
     state.status === "failed" ? "bg-red-500" :
     state.status === "succeeded" ? "bg-green-500" :
     "bg-primary";
  const sourceVideoUrl = `/api/jobs/${jobId}/source-video`;
  const workspaceHint = state.project_id ? `runtime/api/workspaces/${state.project_id}` : "-";
  const hasSourceVideo = state.artifacts.some(
    (artifact) => artifact.path === "media/source.mp4" || artifact.path.endsWith("/source.mp4"),
  );
  const keyframeImages = state.artifacts.filter((artifact) => {
    const lower = artifact.path.toLowerCase();
    return lower.startsWith("frames/images/") && (lower.endsWith(".jpg") || lower.endsWith(".jpeg"));
  });
  const nonImageArtifacts = state.artifacts.filter((artifact) => {
    const lower = artifact.path.toLowerCase();
    if (lower === "frames/images.zip") return false;
    return !(lower.startsWith("frames/images/") && (lower.endsWith(".jpg") || lower.endsWith(".jpeg")));
  });
  const keyframesZipUrl = `/api/jobs/${jobId}/artifacts/keyframes-zip`;
  const [copyStatus, setCopyStatus] = useState<"idle" | "ok" | "fail">("idle");
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  const [deleteIntent, setDeleteIntent] = useState(false);
  const [deleteRetryCount, setDeleteRetryCount] = useState(0);
  const [deleteRetryStopped, setDeleteRetryStopped] = useState(false);

  useEffect(() => {
    if (!state.isMissing) return;
    if (state.project_id) {
      router.replace(`/projects/${state.project_id}`);
      return;
    }
    router.replace("/");
  }, [state.isMissing, state.project_id, router]);

  useEffect(() => {
    if (previewIndex === null) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPreviewIndex(null);
        return;
      }
      if (event.key === "ArrowRight") {
        setPreviewIndex((current) => {
          if (current === null || keyframeImages.length === 0) return current;
          return (current + 1) % keyframeImages.length;
        });
      }
      if (event.key === "ArrowLeft") {
        setPreviewIndex((current) => {
          if (current === null || keyframeImages.length === 0) return current;
          return (current - 1 + keyframeImages.length) % keyframeImages.length;
        });
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [previewIndex, keyframeImages.length]);

  const copyWorkspaceHint = async () => {
    if (!state.project_id) return;
    try {
      await navigator.clipboard.writeText(workspaceHint);
      setCopyStatus("ok");
    } catch {
      setCopyStatus("fail");
    }
    setTimeout(() => setCopyStatus("idle"), 1500);
  };

  const handleDownloadKeyframesZip = async () => {
    try {
      const response = await fetch(keyframesZipUrl, { method: "HEAD" });
      if (!response.ok) {
        if (response.status === 404) {
          alert(t("job.keyframesZipNotFound"));
        } else {
          alert(t("job.keyframesZipDownloadFailed"));
        }
        return;
      }
      window.location.assign(keyframesZipUrl);
    } catch {
      alert(t("job.keyframesZipDownloadFailed"));
    }
  };

  const openPreview = (index: number) => setPreviewIndex(index);
  const closePreview = () => setPreviewIndex(null);
  const handleDeleted = useCallback(() => {
    setDeleteIntent(false);
    setDeleteRetryCount(0);
    setDeleteRetryStopped(false);
    pushToast({ level: "success", message: t("control.deleteDone") });
    if (state.project_id) {
      router.replace(`/projects/${state.project_id}`);
      return;
    }
    router.replace("/");
  }, [pushToast, router, state.project_id, t]);

  const handleDeletePending = useCallback(() => {
    setDeleteIntent(true);
    setDeleteRetryCount(0);
    setDeleteRetryStopped(false);
  }, []);

  useEffect(() => {
    if (!deleteIntent) return;

    if (state.isMissing) {
      setDeleteIntent(false);
      return;
    }

    if (deleteRetryCount >= 20) {
      setDeleteIntent(false);
      setDeleteRetryStopped(true);
      pushToast({ level: "warning", message: t("control.deleteRetryMaxed") });
      return;
    }

    const delayMs = deleteRetryCount < 3 ? 500 : deleteRetryCount < 8 ? 1000 : 2000;
    const timer = window.setTimeout(async () => {
      try {
        const ack = await api.controlJob(jobId, "delete");
        if (ack.reason === "job deleted") {
          handleDeleted();
          return;
        }
      } catch (error) {
        if (error instanceof ApiClientError && error.code === "not_found") {
          handleDeleted();
          return;
        }
      }
      setDeleteRetryCount((count) => count + 1);
    }, delayMs);

    return () => window.clearTimeout(timer);
  }, [
    deleteIntent,
    deleteRetryCount,
    state.isMissing,
    jobId,
    pushToast,
    t,
    handleDeleted,
  ]);
  const showPrev = () => {
    setPreviewIndex((current) => {
      if (current === null || keyframeImages.length === 0) return current;
      return (current - 1 + keyframeImages.length) % keyframeImages.length;
    });
  };
  const showNext = () => {
    setPreviewIndex((current) => {
      if (current === null || keyframeImages.length === 0) return current;
      return (current + 1) % keyframeImages.length;
    });
  };

  const activePreviewArtifact = previewIndex === null ? null : keyframeImages[previewIndex] ?? null;
  const activePreviewUrl = activePreviewArtifact
    ? `/api/jobs/${jobId}/artifacts/download/${encodeArtifactPath(activePreviewArtifact.path)}`
    : null;

  return (
    <div className="container mx-auto p-4 md:p-8 space-y-6 max-w-6xl">
       {/* Header */}
       <div className="flex items-center justify-between">
         <div className="flex items-center gap-4">
            <Link href={state.project_id ? `/projects/${state.project_id}` : "/"}>
                <Button variant="ghost" size="icon">
                    <ArrowLeft className="h-5 w-5" />
                </Button>
            </Link>
             <div>
                <h1 className="text-2xl font-bold tracking-tight font-mono">{jobId}</h1>
                <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
                    <span>{t("job.status")}:</span>
                    <Badge variant={
                        state.status === "succeeded" ? "success" :
                        state.status === "failed" ? "destructive" :
                        state.status === "running" ? "default" : "secondary"
                    }>{state.status}</Badge>
                    
                    {state.isConnected ? (
                         <span className="flex items-center text-green-600 ml-2" title={t("job.live")}>
                            <Wifi className="h-3 w-3 mr-1" /> {t("job.live")}
                         </span>
                    ) : (
                        <span className="flex items-center text-yellow-600 ml-2" title={t("job.offline")}>
                            <WifiOff className="h-3 w-3 mr-1" /> {t("job.offline")}
                         </span>
                    )}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  <span className="mr-3">{t("job.projectLabel")}: <span className="font-mono">{state.project_id || "-"}</span></span>
                  <span>{t("job.workspaceLabel")}: <span className="font-mono">{workspaceHint}</span></span>
                  <button
                    className="ml-2 inline-flex items-center text-muted-foreground hover:text-foreground"
                    onClick={copyWorkspaceHint}
                    type="button"
                    title={t("job.copyWorkspace")}
                    aria-label={t("job.copyWorkspace")}
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </button>
                  {copyStatus === "ok" ? <span className="ml-2 text-green-600">{t("job.copyWorkspaceOk")}</span> : null}
                  {copyStatus === "fail" ? <span className="ml-2 text-amber-600">{t("job.copyWorkspaceFail")}</span> : null}
                </div>
            </div>
         </div>
          <div className="space-y-1 text-right">
            <ControlPanel
              jobId={jobId}
              status={state.status}
              onDeleted={handleDeleted}
              onDeletePending={handleDeletePending}
            />
            {deleteIntent ? (
              <p className="text-xs text-muted-foreground">
                {t("control.deleteRetrying", { count: deleteRetryCount + 1 })}
              </p>
            ) : null}
            {deleteRetryStopped ? (
              <p className="text-xs text-amber-600">{t("control.deleteRetryMaxed")}</p>
            ) : null}
          </div>
         </div>

       {/* Progress Section */}
       <Card>
           <CardContent className="p-6 space-y-4">
                <div className="flex justify-between text-sm font-medium">
                    <span>{t("job.stage")}: {state.current_stage || t("job.initializing")}</span>
                    <span>{state.progress.toFixed(1)}%</span>
                </div>
                <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
                    <div 
                        className={cn("h-full transition-all duration-500 ease-out", progressColor)}
                        style={{ width: `${state.progress}%` }}
                    />
                </div>
           </CardContent>
       </Card>

       {hasSourceVideo ? (
         <Card>
           <CardHeader>
             <CardTitle className="text-lg">source.mp4</CardTitle>
           </CardHeader>
           <CardContent>
             <video className="w-full rounded-md border bg-black" controls preload="metadata" src={sourceVideoUrl} />
           </CardContent>
         </Card>
        ) : null}

       {keyframeImages.length > 0 ? (
         <Card>
            <CardHeader>
              <CardTitle className="text-lg">{t("job.keyframesTitle", { count: keyframeImages.length })}</CardTitle>
            </CardHeader>
            <CardContent className="max-h-[420px] overflow-y-auto">
              <div
                className="grid min-h-[280px] grid-cols-2 gap-3 md:grid-cols-4"
                style={{ overflowAnchor: "none" }}
              >
                {keyframeImages.map((artifact, index) => {
                  const imageUrl = `/api/jobs/${jobId}/artifacts/download/${encodeArtifactPath(artifact.path)}`;
                  return (
                     <button
                      key={artifact.path}
                      type="button"
                      onClick={() => openPreview(index)}
                      className="group block overflow-hidden rounded border border-border/70 bg-muted/20"
                     >
                       <img src={imageUrl} alt={artifact.path.split("/").pop() || t("job.keyframeAlt")} className="aspect-video w-full object-cover transition-transform group-hover:scale-[1.02]" loading="lazy" />
                     </button>
                   );
                 })}
              </div>
            </CardContent>
          </Card>
       ) : null}

       <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
           {/* Logs - Takes up 2 cols */}
           <div className="lg:col-span-2 flex flex-col gap-4">
               <h3 className="text-lg font-semibold">{t("job.logs")}</h3>
               <LogViewer logs={state.latest_logs} className="h-[500px]" />
           </div>

           {/* Sidebar: Artifacts & Info */}
            <div className="space-y-6">
                <Card>
                    <CardHeader>
                         <CardTitle className="text-lg">{t("job.artifacts")}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <details className="group" style={{ overflowAnchor: "none" }}>
                        <summary className="cursor-pointer text-sm text-muted-foreground">
                          {t("job.artifacts")}
                        </summary>
                        <div className="mt-3 max-h-[340px] overflow-y-auto">
                          {nonImageArtifacts.length === 0 && keyframeImages.length === 0 ? (
                            <p className="text-sm text-muted-foreground italic">{t("job.noArtifacts")}</p>
                          ) : (
                            <ul className="space-y-2">
                              {keyframeImages.length > 0 ? (
                                <li className="flex items-center justify-between text-sm p-2 rounded hover:bg-accent group">
                                  <div className="flex items-center truncate">
                                    <ImageIcon className="h-4 w-4 mr-2 text-muted-foreground" />
                                    <span className="truncate max-w-[170px]" title={t("job.keyframesZipLabel")}>{t("job.keyframesZipLabel", { count: keyframeImages.length })}</span>
                                  </div>
                                  <button
                                    type="button"
                                    onClick={handleDownloadKeyframesZip}
                                    className="opacity-70 group-hover:opacity-100 transition-opacity"
                                    aria-label={t("job.keyframesZipLabel", { count: keyframeImages.length })}
                                  >
                                    <Download className="h-4 w-4" />
                                  </button>
                                </li>
                              ) : null}
                              {nonImageArtifacts.map((art) => (
                                <li key={art.path} className="flex items-center justify-between text-sm p-2 rounded hover:bg-accent group">
                                  <div className="flex items-center truncate">
                                    <FileText className="h-4 w-4 mr-2 text-muted-foreground" />
                                    <span className="truncate max-w-[170px]" title={art.path}>{art.path.split('/').pop()}</span>
                                  </div>
                                  <a
                                    href={art.path.endsWith("source.mp4") ? sourceVideoUrl : `/api/jobs/${jobId}/artifacts/download/${encodeArtifactPath(art.path)}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="opacity-0 group-hover:opacity-100 transition-opacity"
                                  >
                                    <Download className="h-4 w-4" />
                                  </a>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </details>
                    </CardContent>
                </Card>
            </div>
        </div>

      {activePreviewArtifact && activePreviewUrl ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          role="dialog"
          aria-modal="true"
          onClick={closePreview}
        >
          <div
            className="relative w-full max-w-5xl"
            onClick={(event) => event.stopPropagation()}
          >
            <img
              src={activePreviewUrl}
              alt={activePreviewArtifact.path.split("/").pop() || t("job.keyframeAlt")}
              className="max-h-[82vh] w-full rounded-md object-contain"
            />
            <button
              type="button"
              className="absolute right-2 top-2 rounded bg-black/50 p-2 text-white"
              onClick={closePreview}
              aria-label="Close preview"
            >
              <X className="h-5 w-5" />
            </button>
            <button
              type="button"
              className="absolute left-2 top-1/2 -translate-y-1/2 rounded bg-black/50 p-2 text-white"
              onClick={showPrev}
              aria-label="Previous image"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <button
              type="button"
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded bg-black/50 p-2 text-white"
              onClick={showNext}
              aria-label="Next image"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
            <a
              href={activePreviewUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="absolute bottom-2 right-2 rounded bg-black/50 p-2 text-white"
              aria-label="Download image"
            >
              <Download className="h-5 w-5" />
            </a>
          </div>
        </div>
      ) : null}
     </div>
  );
}
