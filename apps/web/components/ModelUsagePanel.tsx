"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/Card";
import type { ModelUsageSummary } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";

export function ModelUsagePanel({ usage }: { usage?: ModelUsageSummary | null }) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader><CardTitle>{t("usage.title")}</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs text-muted-foreground">{t("usage.hint")}</p>
        {!usage?.calls ? <p>{t("usage.empty")}</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead><tr>
                {(["stage", "calls", "failed", "input", "output", "cached", "reasoning", "time"] as const).map((key) => <th key={key} className="p-2">{t(`usage.${key}`)}</th>)}
              </tr></thead>
              <tbody>{Object.entries(usage.stages).map(([stage, row]) => (
                <tr key={stage} className="border-t border-border">
                  <td className="p-2">{stage === "frame_summary" ? t("providers.capabilityFrame") : stage === "deliverables" ? t("providers.capabilityOverall") : stage}</td>
                  <td className="p-2">{row.calls}</td><td className="p-2">{row.failed_calls}</td>
                  {(["input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens"] as const).map((key) => <td key={key} className="p-2">{row[key] === null ? t("usage.unknown") : `${row[key].toLocaleString()}${row.missing_fields[key] ? " *" : ""}`}</td>)}
                  <td className="p-2">{(row.elapsed_ms / 1000).toFixed(2)} s</td>
                </tr>
              ))}</tbody>
            </table>
            <p className="mt-2 text-muted-foreground">{t("usage.partialHint")}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
