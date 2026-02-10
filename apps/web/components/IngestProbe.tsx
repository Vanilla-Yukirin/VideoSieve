"use client";

import { useMemo, useState } from "react";

import { api } from "@/lib/api/client";
import {
  DualAssetIngestParams,
  IngestFormatItem,
} from "@/lib/api/types";
import { buildDualAssetPayload, isDuplicateConfig } from "@/lib/ingest/helpers";

import { Button } from "./Button";
import { Card, CardContent } from "./Card";
import { useI18n } from "@/lib/i18n/I18nProvider";

// Re-export helpers for backward compat
export { buildDualAssetPayload, isDuplicateConfig } from "@/lib/ingest/helpers";

// --- Component ---

type IngestProbeProps = {
  onParamsReady: (params: DualAssetIngestParams | undefined) => void;
  disabled?: boolean;
  cookieId?: string;
};

export function IngestProbe({ onParamsReady, disabled = false, cookieId }: IngestProbeProps) {
  const { t } = useI18n();
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [formats, setFormats] = useState<IngestFormatItem[]>([]);

  // Analysis asset selections
  const [analysisVideo, setAnalysisVideo] = useState("");
  const [analysisAudio, setAnalysisAudio] = useState("");

  // Quality asset selections
  const [qualityVideo, setQualityVideo] = useState("");
  const [qualityAudio, setQualityAudio] = useState("");

  const videoOptions = useMemo(() => formats.filter((f) => f.is_video_only), [formats]);
  const audioOptions = useMemo(() => formats.filter((f) => f.is_audio_only), [formats]);

  const duplicateConfig = useMemo(
    () =>
      formats.length > 0 &&
      isDuplicateConfig(analysisVideo, analysisAudio, qualityVideo, qualityAudio),
    [formats.length, analysisVideo, analysisAudio, qualityVideo, qualityAudio],
  );

  const emitParams = (
    sourceUrl: string,
    aVideo: string,
    aAudio: string,
    qVideo: string,
    qAudio: string,
  ) => {
    const payload = buildDualAssetPayload(sourceUrl, aVideo, aAudio, qVideo, qAudio);
    onParamsReady(payload);
  };

  const onProbe = async () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    const trimmedCookieId = cookieId?.trim();

    setLoading(true);
    setError(null);
    setTitle(null);
    setFormats([]);
    setAnalysisVideo("");
    setAnalysisAudio("");
    setQualityVideo("");
    setQualityAudio("");
    onParamsReady(undefined);

    try {
      const response = await api.probeIngestFormats(
        trimmedCookieId ? { source_url: trimmed, cookie_id: trimmedCookieId } : { source_url: trimmed },
      );
      setTitle(response.title);
      setFormats(response.formats);

      // Default selection: first video + first audio for both
      const defaultVideo = response.formats.find((f) => f.is_video_only)?.format_id ?? "";
      const defaultAudio = response.formats.find((f) => f.is_audio_only)?.format_id ?? "";

      setAnalysisVideo(defaultVideo);
      setAnalysisAudio(defaultAudio);
      setQualityVideo(defaultVideo);
      setQualityAudio(defaultAudio);
      emitParams(trimmed, defaultVideo, defaultAudio, defaultVideo, defaultAudio);
    } catch (unknownError) {
      const message = unknownError instanceof Error ? unknownError.message : t("error.probeFailed");
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  // --- Format selector sub-component ---
  const FormatSelector = ({
    label,
    hint,
    selectedVideo: selVid,
    selectedAudio: selAud,
    onVideoChange,
    onAudioChange,
  }: {
    label: string;
    hint?: string;
    selectedVideo: string;
    selectedAudio: string;
    onVideoChange: (value: string) => void;
    onAudioChange: (value: string) => void;
  }) => (
    <Card>
      <CardContent className="space-y-3 p-3">
        <div>
          <div className="text-sm font-semibold">{label}</div>
          {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
        </div>

        <div className="space-y-2">
          <label className="text-xs font-medium">{t("ingest.video")}</label>
          <select
            className="h-9 w-full rounded-md border bg-background px-3 text-sm"
            value={selVid}
            onChange={(e) => onVideoChange(e.target.value)}
            disabled={disabled}
          >
            <option value="">{t("ingest.auto")}</option>
            {videoOptions.map((f) => (
              <option key={f.format_id} value={f.format_id}>
                {f.format_id} | {f.resolution ?? "?"} | {f.fps ?? "-"}fps | {f.vcodec ?? "-"}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <label className="text-xs font-medium">{t("ingest.audio")}</label>
          <select
            className="h-9 w-full rounded-md border bg-background px-3 text-sm"
            value={selAud}
            onChange={(e) => onAudioChange(e.target.value)}
            disabled={disabled}
          >
            <option value="">{t("ingest.auto")}</option>
            {audioOptions.map((f) => (
              <option key={f.format_id} value={f.format_id}>
                {f.format_id} | {f.acodec ?? "audio"} | {f.tbr?.toFixed(0) ?? "-"}k
              </option>
            ))}
          </select>
        </div>
      </CardContent>
    </Card>
  );

  return (
    <div className="space-y-4 rounded-lg border border-border bg-muted/30 p-4">
      {/* URL input + Probe button */}
      <div className="space-y-2">
        <label className="text-sm font-medium" htmlFor="source-url-input">
          {t("ingest.sourceUrl")}
        </label>
        <div className="flex gap-2">
          <input
            id="source-url-input"
            type="text"
            className="h-10 flex-1 rounded-md border border-input bg-background px-3 text-sm"
            placeholder={t("ingest.urlPlaceholder")}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={loading || disabled}
          />
          <Button
            onClick={onProbe}
            disabled={loading || disabled || !url.trim()}
            variant="secondary"
          >
            {loading ? t("ingest.probing") : t("ingest.probe")}
          </Button>
        </div>
        {!cookieId?.trim() ? (
          <p className="text-xs text-amber-700">
            {t("ingest.noCookieHint")}
          </p>
        ) : null}
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>

      {/* Title */}
      {title && (
        <div className="border-l-4 border-primary pl-3 text-sm font-medium">{title}</div>
      )}

      {/* Format table */}
      {formats.length > 0 && (
        <details className="rounded-md border border-border p-3">
          <summary className="cursor-pointer text-sm font-medium">
            {t("ingest.availableFormats", { count: formats.length })}
          </summary>
          <div className="mt-2 max-h-48 overflow-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-1 pr-2">{t("ingest.table.id")}</th>
                  <th className="py-1 pr-2">{t("ingest.table.res")}</th>
                  <th className="py-1 pr-2">{t("ingest.table.fps")}</th>
                  <th className="py-1 pr-2">{t("ingest.table.vcodec")}</th>
                  <th className="py-1 pr-2">{t("ingest.table.acodec")}</th>
                  <th className="py-1 pr-2">{t("ingest.table.type")}</th>
                </tr>
              </thead>
              <tbody>
                {formats.map((f) => (
                  <tr key={f.format_id} className="border-b border-border/50">
                    <td className="py-1 pr-2 font-mono">{f.format_id}</td>
                    <td className="py-1 pr-2">{f.resolution ?? "-"}</td>
                    <td className="py-1 pr-2">{f.fps ?? "-"}</td>
                    <td className="py-1 pr-2">{f.vcodec ?? "-"}</td>
                    <td className="py-1 pr-2">{f.acodec ?? "-"}</td>
                    <td className="py-1 pr-2">
                      {f.is_video_only
                        ? t("ingest.type.video")
                        : f.is_audio_only
                          ? t("ingest.type.audio")
                          : t("ingest.type.muxed")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {/* Dual-asset selectors */}
      {formats.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormatSelector
            label={t("ingest.analysis")}
            hint={t("ingest.analysisHint")}
            selectedVideo={analysisVideo}
            selectedAudio={analysisAudio}
            onVideoChange={(v) => {
              setAnalysisVideo(v);
              emitParams(url, v, analysisAudio, qualityVideo, qualityAudio);
            }}
            onAudioChange={(v) => {
              setAnalysisAudio(v);
              emitParams(url, analysisVideo, v, qualityVideo, qualityAudio);
            }}
          />

          <FormatSelector
            label={t("ingest.quality")}
            hint={t("ingest.qualityHint")}
            selectedVideo={qualityVideo}
            selectedAudio={qualityAudio}
            onVideoChange={(v) => {
              setQualityVideo(v);
              emitParams(url, analysisVideo, analysisAudio, v, qualityAudio);
            }}
            onAudioChange={(v) => {
              setQualityAudio(v);
              emitParams(url, analysisVideo, analysisAudio, qualityVideo, v);
            }}
          />
        </div>
      )}

      {/* Dedupe hint */}
      {duplicateConfig && (
        <div className="rounded-md border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-sm text-yellow-700 dark:text-yellow-400">
          {t("ingest.duplicate")}
        </div>
      )}
    </div>
  );
}
