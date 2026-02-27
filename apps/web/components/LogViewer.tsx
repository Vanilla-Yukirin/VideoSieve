import React, { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/I18nProvider";

interface LogViewerProps {
  logs: string[];
  className?: string;
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
        logs.map((log, i) => (
          <div key={i} className="whitespace-pre-wrap break-all border-b border-zinc-800/50 pb-0.5 mb-0.5 last:border-0">
            {log}
          </div>
        ))
      )}
      <div ref={endRef} />
    </div>
  );
}
