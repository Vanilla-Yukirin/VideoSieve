# Module: ingest

## Purpose

统一 B 站 URL / 本地视频输入，产出标准媒体与元数据。

Recommended flow:
- Probe -> Select -> Download
- Probe stage only resolves selectable formats; download starts after user confirms.
- UI exposes `format_id` selection only; free-form ytdlp format strings are not part of normal flow.

## Inputs

- source url or local file
- optional metadata and language hint

## Outputs

- `media/source.mp4`
- `media/source.analysis.mp4` (optional, only when analysis and quality plans differ)
- `media/audio.wav`
- `meta/meta.json`

## Options

- A: yt-dlp download
- B: local upload import

## Params

- format selection
- retry count
- audio extraction spec

Current ingest keys (job snapshot):
- `source_url`
- `video_format_id`, `audio_format_id` (legacy single-asset path)
- `analysis_asset.video_format_id`, `analysis_asset.audio_format_id`
- `quality_asset.video_format_id`, `quality_asset.audio_format_id`
- `ytdlp_sort`
- `cookie_file_path`, `cookie_secret_ref`

Dual-asset download planning:
- analysis pair == quality pair -> one download (`dedupe_applied=true`)
- analysis pair != quality pair -> two downloads (`dedupe_applied=false`)

## Metrics

- download speed and resolution
- failure reason distribution

## Failure & Fallback

- retry with alternative format
- request cookie-based auth when needed

Security:
- Web/API should not pass raw `cookie_content` from UI; use secret reference or mounted cookie file.
