# Module: ingest

## Purpose

统一 B 站 URL / 本地视频输入，产出标准媒体与元数据。

Recommended flow:
- Probe -> Select -> Download
- Probe stage only resolves selectable formats; download starts after user confirms.

## Inputs

- source url or local file
- optional metadata and language hint

## Outputs

- `media/source.mp4`
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
- `video_format_id`, `audio_format_id` (default path)
- `ytdlp_format`, `ytdlp_sort` (advanced path)
- `cookie_file_path`, `cookie_secret_ref`

## Metrics

- download speed and resolution
- failure reason distribution

## Failure & Fallback

- retry with alternative format
- request cookie-based auth when needed

Security:
- Web/API should not pass raw `cookie_content` from UI; use secret reference or mounted cookie file.
