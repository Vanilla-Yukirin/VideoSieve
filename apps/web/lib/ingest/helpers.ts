import { AssetSelection, DualAssetIngestParams } from "../api/types";

/**
 * Build a dual-asset ingest payload from user selections.
 * Returns undefined if sourceUrl is empty/whitespace.
 */
export function buildDualAssetPayload(
  sourceUrl: string,
  analysisVideo: string,
  analysisAudio: string,
  qualityVideo: string,
  qualityAudio: string,
): DualAssetIngestParams | undefined {
  const trimmed = sourceUrl.trim();
  if (!trimmed) return undefined;

  const analysis: AssetSelection = {};
  if (analysisVideo) analysis.video_format_id = analysisVideo;
  if (analysisAudio) analysis.audio_format_id = analysisAudio;

  const quality: AssetSelection = {};
  if (qualityVideo) quality.video_format_id = qualityVideo;
  if (qualityAudio) quality.audio_format_id = qualityAudio;

  return {
    source_url: trimmed,
    analysis_asset: analysis,
    quality_asset: quality,
  };
}

/**
 * Detect whether both asset pairs have identical format selections.
 */
export function isDuplicateConfig(
  analysisVideo: string,
  analysisAudio: string,
  qualityVideo: string,
  qualityAudio: string,
): boolean {
  return analysisVideo === qualityVideo && analysisAudio === qualityAudio;
}
