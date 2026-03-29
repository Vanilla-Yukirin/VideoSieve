"use client";

import React, { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/I18nProvider";

// ── Raw data types (from JSONL files) ────────────────────────────────────────

interface FrameSummaryRecord {
  frame_id: string;
  description_text: string;
}

interface TranscriptSegment {
  segment_id: string;
  start: number;
  end: number;
  text: string;
  lang?: string;
  conf?: number;
}

interface KeyframeRecord {
  frame_id: string;
  ts: number;
  path: string;
  hash: string;
  score: number;
  reason: string;
}

// ── Merged timeline item types ───────────────────────────────────────────────

type SegmentItem = {
  kind: "segment";
  id: string;
  start: number;
  end: number;
  text: string;
  conf?: number;
};

type FrameItem = {
  kind: "frame";
  id: string;
  ts: number;
  imageUrl: string;
  description?: string; // VLM output — populated later
};

type TimelineItem = SegmentItem | FrameItem;

// ── Load state ───────────────────────────────────────────────────────────────

type LoadState = "idle" | "loading" | "ok" | "not_found" | "error";

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** frame_000001 → frames/images/slide_000001.jpg */
function frameIdToArtifactPath(frameId: string): string {
  const num = frameId.replace(/^frame_/, "");
  return `frames/images/slide_${num}.jpg`;
}

function encodeArtifactPath(path: string): string {
  return path
    .split("/")
    .map((seg) => encodeURIComponent(seg))
    .join("/");
}

async function fetchJsonl<T>(url: string): Promise<T[] | null> {
  const res = await fetch(url);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const text = await res.text();
  return text
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as T);
}

function buildTimeline(
  segments: TranscriptSegment[],
  keyframes: KeyframeRecord[],
  jobId: string,
): TimelineItem[] {
  const items: TimelineItem[] = [
    ...segments.map(
      (seg): SegmentItem => ({
        kind: "segment",
        id: seg.segment_id,
        start: seg.start,
        end: seg.end,
        text: seg.text,
        conf: seg.conf,
      }),
    ),
    ...keyframes.map(
      (kf): FrameItem => ({
        kind: "frame",
        id: kf.frame_id,
        ts: kf.ts,
        imageUrl: `/api/jobs/${jobId}/artifacts/download/${encodeArtifactPath(frameIdToArtifactPath(kf.frame_id))}`,
      }),
    ),
  ];

  // Sort by primary timestamp
  items.sort((a, b) => {
    const ta = a.kind === "segment" ? a.start : a.ts;
    const tb = b.kind === "segment" ? b.start : b.ts;
    return ta - tb;
  });

  return items;
}

// ── Main component ────────────────────────────────────────────────────────────

interface DeliverableTabsProps {
  jobId: string;
  jobStatus: string;
}

export function DeliverablesTabs({ jobId, jobStatus }: DeliverableTabsProps) {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState(0);
  const [timeline, setTimeline] = useState<TimelineItem[] | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [frameSummaries, setFrameSummaries] = useState<Map<string, string>>(new Map());

  // When the job transitions to succeeded, reset so Tab 0 re-fetches
  useEffect(() => {
    if (jobStatus === "succeeded" && (loadState === "not_found" || loadState === "error")) {
      setLoadState("idle");
    }
  }, [jobStatus, loadState]);

  // While job is running and transcript not yet available, retry every 5 s
  useEffect(() => {
    if (loadState !== "not_found") return;
    if (jobStatus !== "running") return;
    const timer = setTimeout(() => setLoadState("idle"), 5000);
    return () => clearTimeout(timer);
  }, [loadState, jobStatus]);

  // Fetch transcript + keyframes when Tab 0 is first activated
  useEffect(() => {
    if (activeTab !== 0) return;
    if (loadState !== "idle") return;

    setLoadState("loading");

    Promise.all([
      fetchJsonl<TranscriptSegment>(
        `/api/jobs/${jobId}/artifacts/download/asr/transcript.jsonl`,
      ),
      fetchJsonl<KeyframeRecord>(
        `/api/jobs/${jobId}/artifacts/download/frames/keyframes.jsonl`,
      ),
    ])
      .then(([segments, keyframes]) => {
        if (!segments) {
          // transcript not found yet → treat as not ready
          setLoadState("not_found");
          return;
        }
        const items = buildTimeline(segments, keyframes ?? [], jobId);
        setTimeline(items);
        setLoadState("ok");
      })
      .catch(() => setLoadState("error"));
  }, [activeTab, jobId, loadState]);

  // Fetch frame_summary.jsonl once the primary timeline is loaded
  useEffect(() => {
    if (loadState !== "ok") return;

    fetchJsonl<FrameSummaryRecord>(
      `/api/jobs/${jobId}/artifacts/download/frame_summary/frame_summary.jsonl`,
    )
      .then((records) => {
        if (!records) return; // 404 = no VLM run, silently skip
        const map = new Map<string, string>();
        for (const r of records) {
          if (r.description_text && !r.description_text.startsWith("[offline frame summary]")) {
            map.set(r.frame_id, r.description_text);
          }
        }
        setFrameSummaries(map);
      })
      .catch(() => {
        // Non-critical — silently ignore errors
      });
  }, [jobId, loadState]);

  // While job is running, poll frame_summary.jsonl every 4 s to pick up new descriptions
  useEffect(() => {
    if (loadState !== "ok") return;
    if (jobStatus !== "running") return;

    const interval = setInterval(() => {
      fetchJsonl<FrameSummaryRecord>(
        `/api/jobs/${jobId}/artifacts/download/frame_summary/frame_summary.jsonl`,
      )
        .then((records) => {
          if (!records) return;
          setFrameSummaries((prev) => {
            const next = new Map(prev);
            for (const r of records) {
              if (r.description_text && !r.description_text.startsWith("[offline frame summary]")) {
                next.set(r.frame_id, r.description_text);
              }
            }
            return next;
          });
        })
        .catch(() => {});
    }, 4000);

    return () => clearInterval(interval);
  }, [jobId, loadState, jobStatus]);

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
          <RawTranscriptPanel timeline={timeline} loadState={loadState} frameSummaries={frameSummaries} />
        )}
        {activeTab === 1 && <PlaceholderPanel message={t("deliverables.polishedPlaceholder")} />}
        {activeTab === 2 && <PlaceholderPanel message={t("deliverables.summaryPlaceholder")} />}
      </div>
    </div>
  );
}

// ── Tab 0: Interleaved timeline ───────────────────────────────────────────────

function RawTranscriptPanel({
  timeline,
  loadState,
  frameSummaries,
}: {
  timeline: TimelineItem[] | null;
  loadState: LoadState;
  frameSummaries: Map<string, string>;
}) {
  const { t } = useI18n();

  if (loadState === "idle" || loadState === "loading") {
    return <StatusMessage>{t("common.loading")}</StatusMessage>;
  }
  if (loadState === "not_found") {
    return <StatusMessage>{t("deliverables.notAvailable")}</StatusMessage>;
  }
  if (loadState === "error") {
    return (
      <StatusMessage className="text-destructive">{t("deliverables.error")}</StatusMessage>
    );
  }

  const items = timeline ?? [];
  if (items.length === 0) {
    return <StatusMessage>{t("deliverables.emptyTimeline")}</StatusMessage>;
  }

  return (
    <div className="space-y-2 max-h-[640px] overflow-y-auto pr-1">
      {items.map((item) =>
        item.kind === "frame" ? (
          <FrameCard
            key={`frame-${item.id}`}
            item={{ ...item, description: frameSummaries.get(item.id) }}
          />
        ) : (
          <SegmentCard key={`seg-${item.id}`} item={item} />
        ),
      )}
    </div>
  );
}

// ── Keyframe card ─────────────────────────────────────────────────────────────

function FrameCard({ item }: { item: FrameItem }) {
  const { t } = useI18n();
  return (
    <div className="flex gap-4 p-3 rounded-lg border border-primary/20 bg-primary/5 hover:bg-primary/10 transition-colors">
      {/* Image */}
      <div className="shrink-0 w-40 md:w-52">
        <img
          src={item.imageUrl}
          alt={item.id}
          className="w-full aspect-video object-cover rounded border border-border/40"
          loading="lazy"
        />
      </div>

      {/* Right: timestamp + VLM description placeholder */}
      <div className="flex-1 min-w-0 space-y-2 py-1">
        <span className="block text-xs text-muted-foreground font-mono tabular-nums">
          {formatTime(item.ts)}
        </span>
        {item.description ? (
          <p className="text-sm leading-relaxed text-foreground">{item.description}</p>
        ) : (
          <p className="text-xs text-muted-foreground/60 italic">
            {t("deliverables.frameNoDesc")}
          </p>
        )}
      </div>
    </div>
  );
}

// ── ASR segment card ──────────────────────────────────────────────────────────

function SegmentCard({ item }: { item: SegmentItem }) {
  return (
    <div className="flex items-baseline gap-4 px-3 py-2.5 rounded-md hover:bg-accent/10 transition-colors">
      {/* Timestamp column */}
      <span className="shrink-0 w-24 text-xs text-muted-foreground font-mono tabular-nums text-right">
        {formatTime(item.start)}–{formatTime(item.end)}
      </span>

      {/* Text */}
      <p className="flex-1 text-sm leading-relaxed break-words">{item.text}</p>

      {/* Confidence badge (optional) */}
      {item.conf !== undefined ? (
        <span className="shrink-0 text-xs text-muted-foreground/70 font-mono tabular-nums">
          {(item.conf * 100).toFixed(0)}%
        </span>
      ) : null}
    </div>
  );
}

// ── Tab 1 & 2: Placeholders ───────────────────────────────────────────────────

function PlaceholderPanel({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center h-40 rounded-lg border border-dashed border-border text-sm text-muted-foreground">
      {message}
    </div>
  );
}

// ── Shared ────────────────────────────────────────────────────────────────────

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
