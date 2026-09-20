"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/I18nProvider";
import {
  EMPTY_JSONL_CURSOR,
  fetchJsonl,
  fetchJsonlDelta,
  JsonlCursor,
} from "@/lib/artifacts/jsonl";
import {
  frameNameToArtifactPath,
  parseIllustratedNotes,
} from "@/lib/artifacts/illustratedNotes";

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

interface SummaryRecord {
  title: string;
  summary: string;
  provider: string;
  model: string;
  source_sections: number;
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
  const [polishedNotes, setPolishedNotes] = useState<string | null>(null);
  const [polishedLoadState, setPolishedLoadState] = useState<LoadState>("idle");
  const [summary, setSummary] = useState<SummaryRecord | null>(null);
  const [summaryLoadState, setSummaryLoadState] = useState<LoadState>("idle");
  const frameCursorRef = useRef<JsonlCursor>(EMPTY_JSONL_CURSOR);
  const frameFetchInFlightRef = useRef(false);

  const refreshFrameSummaries = useCallback(async (complete: boolean) => {
    if (frameFetchInFlightRef.current) return;
    frameFetchInFlightRef.current = true;
    try {
      const result = await fetchJsonlDelta<FrameSummaryRecord>(
        `/api/jobs/${jobId}/artifacts/download/frame_summary/frame_summary.jsonl`,
        frameCursorRef.current,
        { complete },
      );
      if (!result) return;
      frameCursorRef.current = result.cursor;
      if (result.records.length === 0 && !result.reset) return;
      setFrameSummaries((previous) => {
        const next = result.reset ? new Map<string, string>() : new Map(previous);
        for (const record of result.records) {
          if (
            record.description_text &&
            !record.description_text.startsWith("[offline frame summary]")
          ) {
            next.set(record.frame_id, record.description_text);
          }
        }
        return next;
      });
    } catch {
      // Frame descriptions are optional; the transcript remains usable on fetch errors.
    } finally {
      frameFetchInFlightRef.current = false;
    }
  }, [jobId]);

  // When the job transitions to succeeded, reset so Tab 0 re-fetches
  useEffect(() => {
    if (jobStatus === "succeeded" && (loadState === "not_found" || loadState === "error")) {
      const timer = window.setTimeout(() => setLoadState("idle"), 0);
      return () => window.clearTimeout(timer);
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

    const loadTimeline = async () => {
      setLoadState("loading");
      try {
        const [segments, keyframes] = await Promise.all([
          fetchJsonl<TranscriptSegment>(
            `/api/jobs/${jobId}/artifacts/download/asr/transcript.jsonl`,
          ),
          fetchJsonl<KeyframeRecord>(
            `/api/jobs/${jobId}/artifacts/download/frames/keyframes.jsonl`,
          ),
        ]);
        if (!segments) {
          // transcript not found yet → treat as not ready
          setLoadState("not_found");
          return;
        }
        const items = buildTimeline(segments, keyframes ?? [], jobId);
        setTimeline(items);
        setLoadState("ok");
      } catch {
        setLoadState("error");
      }
    };
    void loadTimeline();
  }, [activeTab, jobId, loadState]);

  // Fetch frame_summary.jsonl once, then request only appended byte ranges.
  useEffect(() => {
    if (loadState !== "ok") return;
    void refreshFrameSummaries(jobStatus !== "running");
  }, [jobStatus, loadState, refreshFrameSummaries]);

  // While job is running, poll frame_summary.jsonl every 4 s to pick up new descriptions
  useEffect(() => {
    if (loadState !== "ok") return;
    if (jobStatus !== "running") return;

    const interval = setInterval(() => {
      void refreshFrameSummaries(false);
    }, 4000);

    return () => clearInterval(interval);
  }, [loadState, jobStatus, refreshFrameSummaries]);

  useEffect(() => {
    if (activeTab !== 1 || polishedLoadState !== "idle") return;
    const loadPolishedNotes = async () => {
      setPolishedLoadState("loading");
      try {
        const response = await fetch(
          `/api/jobs/${jobId}/artifacts/download/outputs/illustrated_notes.md`,
        );
        if (response.status === 404) {
          setPolishedLoadState("not_found");
          return;
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        setPolishedNotes(await response.text());
        setPolishedLoadState("ok");
      } catch {
        setPolishedLoadState("error");
      }
    };
    void loadPolishedNotes();
  }, [activeTab, jobId, polishedLoadState]);

  useEffect(() => {
    if (
      jobStatus === "succeeded" &&
      (polishedLoadState === "not_found" || polishedLoadState === "error")
    ) {
      const timer = window.setTimeout(() => setPolishedLoadState("idle"), 0);
      return () => window.clearTimeout(timer);
    }
  }, [jobStatus, polishedLoadState]);

  useEffect(() => {
    if (activeTab !== 2 || summaryLoadState !== "idle") return;
    const loadSummary = async () => {
      setSummaryLoadState("loading");
      try {
        const response = await fetch(`/api/jobs/${jobId}/artifacts/download/outputs/summary.json`);
        if (response.status === 404) {
          setSummaryLoadState("not_found");
          return;
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = (await response.json()) as SummaryRecord;
        if (!payload.summary || !payload.provider || !payload.model) {
          throw new Error("invalid summary artifact");
        }
        setSummary(payload);
        setSummaryLoadState("ok");
      } catch {
        setSummaryLoadState("error");
      }
    };
    void loadSummary();
  }, [activeTab, jobId, summaryLoadState]);

  useEffect(() => {
    if (jobStatus === "succeeded" && summaryLoadState === "not_found") {
      const timer = window.setTimeout(() => setSummaryLoadState("idle"), 0);
      return () => window.clearTimeout(timer);
    }
  }, [jobStatus, summaryLoadState]);

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
        {activeTab === 1 && (
          <PolishedNotesPanel
            jobId={jobId}
            markdown={polishedNotes}
            loadState={polishedLoadState}
          />
        )}
        {activeTab === 2 && (
          <SummaryPanel summary={summary} loadState={summaryLoadState} />
        )}
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
        <Image
          src={item.imageUrl}
          alt={item.id}
          width={832}
          height={468}
          unoptimized
          className="w-full aspect-video object-cover rounded border border-border/40"
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

// ── Tab 1: Published illustrated notes ────────────────────────────────────────

function PolishedNotesPanel({
  jobId,
  markdown,
  loadState,
}: {
  jobId: string;
  markdown: string | null;
  loadState: LoadState;
}) {
  const { t } = useI18n();
  if (loadState === "idle" || loadState === "loading") {
    return <StatusMessage>{t("common.loading")}</StatusMessage>;
  }
  if (loadState === "not_found") {
    return <StatusMessage>{t("deliverables.notAvailable")}</StatusMessage>;
  }
  if (loadState === "error" || markdown === null) {
    return <StatusMessage className="text-destructive">{t("deliverables.error")}</StatusMessage>;
  }

  const blocks = parseIllustratedNotes(markdown);
  if (blocks.length === 0) {
    return <StatusMessage>{t("deliverables.emptyPolished")}</StatusMessage>;
  }

  return (
    <article className="max-h-[640px] space-y-4 overflow-y-auto rounded-lg border border-border p-4">
      {blocks.map((block, index) => {
        if (block.kind === "frame") {
          const artifactPath = frameNameToArtifactPath(block.name);
          const imageUrl = `/api/jobs/${jobId}/artifacts/download/${encodeArtifactPath(artifactPath)}`;
          return (
            <figure key={`${block.name}-${index}`} className="overflow-hidden rounded-lg border border-primary/20 bg-primary/5">
              <Image
                src={imageUrl}
                alt={block.name}
                width={1280}
                height={720}
                unoptimized
                className="aspect-video w-full object-contain"
              />
            </figure>
          );
        }
        if (block.kind === "heading") {
          const headingClass = block.level === 1 ? "text-xl" : block.level === 2 ? "text-lg" : "text-base";
          return (
            <h3 key={`heading-${index}`} className={cn("font-semibold tracking-tight", headingClass)}>
              {block.text}
            </h3>
          );
        }
        return (
          <p key={`paragraph-${index}`} className="whitespace-pre-wrap text-sm leading-relaxed">
            {block.text}
          </p>
        );
      })}
    </article>
  );
}

// ── Tab 2: Model summary ──────────────────────────────────────────────────────

function SummaryPanel({
  summary,
  loadState,
}: {
  summary: SummaryRecord | null;
  loadState: LoadState;
}) {
  const { t } = useI18n();
  if (loadState === "idle" || loadState === "loading") {
    return <StatusMessage>{t("common.loading")}</StatusMessage>;
  }
  if (loadState === "not_found") {
    return <StatusMessage>{t("deliverables.notAvailable")}</StatusMessage>;
  }
  if (loadState === "error" || summary === null) {
    return <StatusMessage className="text-destructive">{t("deliverables.error")}</StatusMessage>;
  }
  return (
    <article className="space-y-3 rounded-lg border border-border p-4">
      <h3 className="font-semibold">{summary.title}</h3>
      <p className="whitespace-pre-wrap text-sm leading-relaxed">{summary.summary}</p>
      <p className="text-xs text-muted-foreground">
        {summary.provider} / {summary.model} · {summary.source_sections}
      </p>
    </article>
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
