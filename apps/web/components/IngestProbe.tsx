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
import { Upload, Link2 } from "lucide-react";

function parsePixels(resolution?: string): number {
  if (!resolution) return 0;
  const match = resolution.toLowerCase().match(/(\d{3,5})\s*[x*]\s*(\d{3,5})/);
  if (!match) return 0;
  const width = Number(match[1]);
  const height = Number(match[2]);
  if (!Number.isFinite(width) || !Number.isFinite(height)) return 0;
  return width * height;
}

function isAvcCodec(codec?: string): boolean {
  if (!codec) return false;
  const normalized = codec.toLowerCase();
  return normalized.includes("avc") || normalized.includes("h264");
}

function pickAnalysisVideoFormat(formats: IngestFormatItem[]): string {
  const videoOnly = formats.filter((item) => item.is_video_only);
  if (videoOnly.length === 0) return "";
  const avcOnly = videoOnly.filter((item) => isAvcCodec(item.vcodec));
  const candidates = avcOnly.length > 0 ? avcOnly : videoOnly;
  const sorted = [...candidates].sort((a, b) => {
    const pixelDiff = parsePixels(a.resolution) - parsePixels(b.resolution);
    if (pixelDiff !== 0) return pixelDiff;
    const fpsDiff = (a.fps ?? 0) - (b.fps ?? 0);
    if (fpsDiff !== 0) return fpsDiff;
    const tbrDiff = (a.tbr ?? 0) - (b.tbr ?? 0);
    if (tbrDiff !== 0) return tbrDiff;
    return a.format_id.localeCompare(b.format_id);
  });
  return sorted[0]?.format_id ?? "";
}

function pickQualityVideoFormat(formats: IngestFormatItem[]): string {
  const videoOnly = formats.filter((item) => item.is_video_only);
  if (videoOnly.length === 0) return "";
  const sorted = [...videoOnly].sort((a, b) => {
    const pixelDiff = parsePixels(b.resolution) - parsePixels(a.resolution);
    if (pixelDiff !== 0) return pixelDiff;
    const fpsDiff = (b.fps ?? 0) - (a.fps ?? 0);
    if (fpsDiff !== 0) return fpsDiff;
    const tbrDiff = (b.tbr ?? 0) - (a.tbr ?? 0);
    if (tbrDiff !== 0) return tbrDiff;
    return a.format_id.localeCompare(b.format_id);
  });
  return sorted[0]?.format_id ?? "";
}

function pickAnalysisAudioFormat(formats: IngestFormatItem[]): string {
  const audioOnly = formats.filter((item) => item.is_audio_only);
  if (audioOnly.length === 0) return "";
  const sorted = [...audioOnly].sort((a, b) => {
    const tbrDiff = (a.tbr ?? 0) - (b.tbr ?? 0);
    if (tbrDiff !== 0) return tbrDiff;
    return a.format_id.localeCompare(b.format_id);
  });
  return sorted[0]?.format_id ?? "";
}

function pickQualityAudioFormat(formats: IngestFormatItem[]): string {
  const audioOnly = formats.filter((item) => item.is_audio_only);
  if (audioOnly.length === 0) return "";
  const sorted = [...audioOnly].sort((a, b) => {
    const tbrDiff = (b.tbr ?? 0) - (a.tbr ?? 0);
    if (tbrDiff !== 0) return tbrDiff;
    return a.format_id.localeCompare(b.format_id);
  });
  return sorted[0]?.format_id ?? "";
}

// Re-export helpers for backward compat
export { buildDualAssetPayload, isDuplicateConfig } from "@/lib/ingest/helpers";

// --- Component ---

type IngestProbeProps = {
  onParamsReady: (params: DualAssetIngestParams | undefined) => void;
  onLocalUpload?: (file: File, context: string) => void;
  disabled?: boolean;
  cookieId?: string;
};

export function IngestProbe({ onParamsReady, onLocalUpload, disabled = false, cookieId }: IngestProbeProps) {
  const { t } = useI18n();
  const [mode, setMode] = useState<"url" | "upload">("url");
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [formats, setFormats] = useState<IngestFormatItem[]>([]);

  // Local upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadContext, setUploadContext] = useState("");

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

      const defaultAnalysisVideo = pickAnalysisVideoFormat(response.formats);
      const defaultAnalysisAudio = pickAnalysisAudioFormat(response.formats);
      const defaultQualityVideo = pickQualityVideoFormat(response.formats);
      const defaultQualityAudio = pickQualityAudioFormat(response.formats);

      setAnalysisVideo(defaultAnalysisVideo);
      setAnalysisAudio(defaultAnalysisAudio);
      setQualityVideo(defaultQualityVideo);
      setQualityAudio(defaultQualityAudio);
      emitParams(
        trimmed,
        defaultAnalysisVideo,
        defaultAnalysisAudio,
        defaultQualityVideo,
        defaultQualityAudio,
      );
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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setTitle(file.name);
      if (onLocalUpload) {
        // For upload mode, don't set ingestParams - parent will handle via uploadFile state
        onLocalUpload(file, uploadContext);
      }
    }
  };

  return (
    <div className="space-y-4 rounded-lg border border-border bg-muted/30 p-4">
      {/* Mode toggle */}
      <div className="flex gap-2">
        <Button
          variant={mode === "url" ? "primary" : "outline"}
          size="sm"
          onClick={() => {
            setMode("url");
            setSelectedFile(null);
            setUploadContext("");
            onParamsReady(undefined);
          }}
          disabled={disabled}
          className="flex-1"
        >
          <Link2 className="mr-2 h-4 w-4" />
          网络视频
        </Button>
        <Button
          variant={mode === "upload" ? "primary" : "outline"}
          size="sm"
          onClick={() => {
            setMode("upload");
            setUrl("");
            setFormats([]);
            setTitle(null);
            onParamsReady(undefined);
          }}
          disabled={disabled || !onLocalUpload}
          className="flex-1"
        >
          <Upload className="mr-2 h-4 w-4" />
          本地上传
        </Button>
      </div>

      {/* Network URL mode */}
      {mode === "url" && (
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
      )}

      {/* Local upload mode */}
      {mode === "upload" && (
        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="file-input">
              选择视频文件
            </label>
            <input
              id="file-input"
              type="file"
              accept="video/*"
              onChange={handleFileChange}
              disabled={disabled}
              className="block w-full text-sm text-muted-foreground file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-primary file:text-primary-foreground hover:file:bg-primary/90"
            />
            {selectedFile && (
              <p className="text-xs text-muted-foreground">
                已选择: {selectedFile.name} ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
              </p>
            )}
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="context-input">
              背景信息
              <span className="ml-1 text-xs font-normal text-muted-foreground">
                (可选)
              </span>
            </label>
            <textarea
              id="context-input"
              className="min-h-[100px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              placeholder="粘贴视频简介、评论或其他背景资料..."
              value={uploadContext}
              onChange={(e) => {
                setUploadContext(e.target.value);
                if (selectedFile && onLocalUpload) {
                  onLocalUpload(selectedFile, e.target.value);
                }
              }}
              disabled={disabled}
            />
            <p className="text-xs text-muted-foreground">
              用于弥补本地视频无法自动获取的简介/评论等上下文信息
            </p>
          </div>
        </div>
      )}

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
