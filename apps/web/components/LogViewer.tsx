import React, { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/I18nProvider";

interface LogViewerProps {
  logs: string[];
  className?: string;
}

type LogLevel = "info" | "warning" | "error" | "unknown";

function parseLogLine(raw: string): { level: LogLevel; message: string } {
  const match = raw.match(/^\[(info|warning|error)\]\s?(.*)$/i);
  if (!match) {
    return { level: "unknown", message: raw };
  }
  const level = match[1].toLowerCase() as Exclude<LogLevel, "unknown">;
  const message = match[2] ?? "";
  return { level, message: message || raw };
}

function levelTone(level: LogLevel): { badge: string; text: string; border: string } {
  if (level === "error") {
    return {
      badge: "bg-red-500/20 text-red-200 border-red-400/40",
      text: "text-red-100",
      border: "border-red-500/30",
    };
  }
  if (level === "warning") {
    return {
      badge: "bg-amber-500/20 text-amber-100 border-amber-300/40",
      text: "text-amber-50",
      border: "border-amber-500/25",
    };
  }
  if (level === "info") {
    return {
      badge: "bg-sky-500/20 text-sky-100 border-sky-300/35",
      text: "text-zinc-100",
      border: "border-zinc-700/50",
    };
  }
  return {
    badge: "bg-zinc-700/40 text-zinc-200 border-zinc-500/30",
    text: "text-zinc-200",
    border: "border-zinc-700/50",
  };
}

function levelLabelKey(level: LogLevel): "logs.level.info" | "logs.level.warning" | "logs.level.error" | "logs.level.unknown" {
  if (level === "error") return "logs.level.error";
  if (level === "warning") return "logs.level.warning";
  if (level === "info") return "logs.level.info";
  return "logs.level.unknown";
}

export function LogViewer({ logs, className }: LogViewerProps) {
  const { t } = useI18n();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div
      className={cn(
        "log-scroll overflow-y-auto rounded-md border border-zinc-700/70 bg-zinc-950/95 p-4 text-sm text-zinc-100",
        className,
      )}
      style={{ fontFamily: 'ui-monospace, "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace' }}
    >
      {logs.length === 0 ? (
        <span className="text-zinc-500 italic">{t("logs.empty")}</span>
      ) : (
        logs.map((log, i) => {
          const parsed = parseLogLine(log);
          const previous = i > 0 ? parseLogLine(logs[i - 1]) : null;
          const isNewGroup = i === 0 || parsed.level !== previous?.level;
          const tone = levelTone(parsed.level);
          const levelLabel = t(levelLabelKey(parsed.level));

          return (
            <div
              key={`${i}-${log}`}
              className={cn(
                "whitespace-pre-wrap break-all border-b pb-1 mb-1 last:border-0",
                tone.border,
                isNewGroup ? "mt-2 first:mt-0" : "mt-0",
              )}
            >
              <div className="flex items-start gap-2">
                <span
                  className={cn(
                    "mt-0.5 inline-flex shrink-0 rounded border px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
                    tone.badge,
                  )}
                >
                  {levelLabel}
                </span>
                <span className={cn("min-w-0", tone.text)}>{parsed.message}</span>
              </div>
            </div>
          );
        })
      )}
      <div ref={endRef} />
    </div>
  );
}
