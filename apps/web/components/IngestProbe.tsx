"use client";

import { useMemo, useState } from "react";

import { api } from "@/lib/api/client";
import { IngestFormatItem, IngestParams } from "@/lib/api/types";

import { Button } from "./Button";
import { Card, CardContent } from "./Card";

type IngestProbeProps = {
  onParamsReady: (params: IngestParams | undefined) => void;
  disabled?: boolean;
};

export function IngestProbe({ onParamsReady, disabled = false }: IngestProbeProps) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [formats, setFormats] = useState<IngestFormatItem[]>([]);
  const [selectedVideo, setSelectedVideo] = useState("");
  const [selectedAudio, setSelectedAudio] = useState("");

  const videoOptions = useMemo(() => formats.filter((f) => f.is_video_only), [formats]);
  const audioOptions = useMemo(() => formats.filter((f) => f.is_audio_only), [formats]);

  const emitParams = (sourceUrl: string, videoFormatId: string, audioFormatId: string) => {
    const trimmed = sourceUrl.trim();
    if (!trimmed) {
      onParamsReady(undefined);
      return;
    }

    const payload: IngestParams = {
      source_url: trimmed,
    };
    if (videoFormatId) {
      payload.video_format_id = videoFormatId;
    }
    if (audioFormatId) {
      payload.audio_format_id = audioFormatId;
    }
    onParamsReady(payload);
  };

  const onProbe = async () => {
    const trimmed = url.trim();
    if (!trimmed) {
      return;
    }

    setLoading(true);
    setError(null);
    setTitle(null);
    setFormats([]);
    setSelectedVideo("");
    setSelectedAudio("");
    onParamsReady(undefined);

    try {
      const response = await api.probeIngestFormats(trimmed);
      setTitle(response.title);
      setFormats(response.formats);

      const defaultVideo = response.formats.find((f) => f.is_video_only)?.format_id ?? "";
      const defaultAudio = response.formats.find((f) => f.is_audio_only)?.format_id ?? "";

      setSelectedVideo(defaultVideo);
      setSelectedAudio(defaultAudio);
      emitParams(trimmed, defaultVideo, defaultAudio);
    } catch (unknownError) {
      const message = unknownError instanceof Error ? unknownError.message : "Probe failed";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4 rounded-lg border border-border bg-muted/30 p-4">
      <div className="space-y-2">
        <label className="text-sm font-medium" htmlFor="source-url-input">
          Source URL
        </label>
        <div className="flex gap-2">
          <input
            id="source-url-input"
            type="text"
            className="h-10 flex-1 rounded-md border border-input bg-background px-3 text-sm"
            placeholder="https://www.bilibili.com/video/BV..."
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            disabled={loading || disabled}
          />
          <Button
            onClick={onProbe}
            disabled={loading || disabled || !url.trim()}
            variant="secondary"
          >
            {loading ? "Probing..." : "Probe"}
          </Button>
        </div>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
      </div>

      {title ? <div className="border-l-4 border-primary pl-3 text-sm font-medium">{title}</div> : null}

      {formats.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Card>
            <CardContent className="space-y-2 p-3">
              <div className="text-sm font-medium">Video</div>
              <select
                className="h-9 w-full rounded-md border bg-background px-3 text-sm"
                value={selectedVideo}
                onChange={(event) => {
                  const value = event.target.value;
                  setSelectedVideo(value);
                  emitParams(url, value, selectedAudio);
                }}
                disabled={disabled}
              >
                <option value="">Auto</option>
                {videoOptions.map((format) => (
                  <option key={format.format_id} value={format.format_id}>
                    {format.format_id} | {format.resolution ?? "unknown"} | {format.vcodec ?? "-"}
                  </option>
                ))}
              </select>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-2 p-3">
              <div className="text-sm font-medium">Audio</div>
              <select
                className="h-9 w-full rounded-md border bg-background px-3 text-sm"
                value={selectedAudio}
                onChange={(event) => {
                  const value = event.target.value;
                  setSelectedAudio(value);
                  emitParams(url, selectedVideo, value);
                }}
                disabled={disabled}
              >
                <option value="">Auto</option>
                {audioOptions.map((format) => (
                  <option key={format.format_id} value={format.format_id}>
                    {format.format_id} | {format.acodec ?? "audio"} | {format.tbr?.toFixed(0) ?? "-"}k
                  </option>
                ))}
              </select>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
