# Module: ingest

## Purpose

统一 B 站 URL / 本地视频输入，产出标准媒体与元数据。

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

## Metrics

- download speed and resolution
- failure reason distribution

## Failure & Fallback

- retry with alternative format
- request cookie-based auth when needed
