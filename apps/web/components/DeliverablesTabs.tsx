"use client";

import React, { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/I18nProvider";

// ── Types ────────────────────────────────────────────────────────────────────

interface TimelineChunk {
  chunk_id: string;
  start: number;
  end: number;
  text: string;
  transcript_refs: string[];
  frame_refs: string[];
  frame_summary_refs: string[];
}

interface Timeline {
  schema_version: string;
  project_id: string;
  job_id: string;
  chunks: TimelineChunk[];
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** frame_000001 → frames/images/slide_000001.jpg */
function frameRefToArtifactPath(frameRef: string): string {
  const num = frameRef.replace(/^frame_/, "");
  return `frames/images/slide_${num}.jpg`;
}

function encodeArtifactPath(path: string): string {
  return path
    .split("/")
    .map((seg) => encodeURIComponent(seg))
    .join("/");
}

// ── Main component ────────────────────────────────────────────────────────────

interface DeliverableTabsProps {
  jobId: string;
}

export function DeliverablesTabs({ jobId }: DeliverableTabsProps) {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState(0);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "ok" | "not_found" | "error">(
    "idle",
  );

  // Fetch timeline.json when Tab 0 is first activated
  useEffect(() => {
    if (activeTab !== 0) return;
    if (loadState !== "idle") return;

    setLoadState("loading");

    fetch(`/api/jobs/${jobId}/artifacts/download/fusion/timeline.json`)
      .then(async (res) => {
        if (!res.ok) {
          setLoadState(res.status === 404 ? "not_found" : "error");
          return;
        }
        const data: Timeline = await res.json();
        setTimeline(data);
        setLoadState("ok");
      })
      .catch(() => setLoadState("error"));
  }, [activeTab, jobId, loadState]);

  const tabs: string[] = [
    t("deliverables.tabRaw"),
    t("deliverables.tabPolished"),
    t("deliverables.tabSummary"),
  ];

  return (
    <div className="space-y-0">
      {/* Tab bar */}
      <div className="flex border-b border-border">
        {tabs.map((label, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setActiveTab(i)}
            className={cn(
              "px-5 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px",
              activeTab === i
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground hover:border-border",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab panels */}
      <div className="pt-4">
        {activeTab === 0 && (
          <RawTranscriptPanel jobId={jobId} timeline={timeline} loadState={loadState} />
        )}
        {activeTab === 1 && <PlaceholderPanel message={t("deliverables.polishedPlaceholder")} />}
        {activeTab === 2 && <PlaceholderPanel message={t("deliverables.summaryPlaceholder")} />}
      </div>
    </div>
  );
}

// ── Tab 1: Raw transcript with interleaved keyframes ─────────────────────────

type LoadState = "idle" | "loading" | "ok" | "not_found" | "error";

function RawTranscriptPanel({
  jobId,
  timeline,
  loadState,
}: {
  jobId: string;
  timeline: Timeline | null;
  loadState: LoadState;
}) {
  const { t } = useI18n();

  if (loadState === "idle" || loadState === "loading") {
    return <StatusMessage>{t("common.loading")}</StatusMessage>;
  }

  if (loadState === "not_found") {
    return <StatusMessage>{t("deliverables.notAvailable")}</StatusMessage>;
  }

  if (loadState === "error") {
    return <StatusMessage className="text-destructive">{t("deliverables.error")}</StatusMessage>;
  }

  const chunks = timeline?.chunks ?? [];

  if (chunks.length === 0) {
    return <StatusMessage>{t("deliverables.emptyTimeline")}</StatusMessage>;
  }

  return (
    <div className="space-y-3 max-h-[640px] overflow-y-auto pr-1">
      {chunks.map((chunk) => {
        const imageRef = chunk.frame_refs?.[0] ?? null;
        const imageUrl = imageRef
          ? `/api/jobs/${jobId}/artifacts/download/${encodeArtifactPath(frameRefToArtifactPath(imageRef))}`
          : null;

        return (
          <div
            key={chunk.chunk_id}
            className="flex gap-4 p-3 rounded-lg border border-border/60 bg-card/60 hover:bg-accent/10 transition-colors"
          >
            {/* Keyframe image */}
            {imageUrl ? (
              <div className="shrink-0 w-36 md:w-44">
                <img
                  src={imageUrl}
                  alt={imageRef ?? "keyframe"}
                  className="w-full aspect-video object-cover rounded border border-border/40"
                  loading="lazy"
                />
              </div>
            ) : null}

            {/* Text + timestamp */}
            <div className="flex-1 min-w-0 space-y-1.5">
              <span className="block text-xs text-muted-foreground font-mono tabular-nums">
                {formatTime(chunk.start)} – {formatTime(chunk.end)}
              </span>
              <p className="text-sm leading-relaxed break-words">{chunk.text}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Tab 2 & 3: Placeholders ───────────────────────────────────────────────────

function PlaceholderPanel({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center h-40 rounded-lg border border-dashed border-border text-sm text-muted-foreground">
      {message}
    </div>
  );
}

// ── Shared helpers ────────────────────────────────────────────────────────────

function StatusMessage({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-center h-40 text-sm text-muted-foreground",
        className,
      )}
    >
      {children}
    </div>
  );
}
