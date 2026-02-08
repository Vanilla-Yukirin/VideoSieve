"""Manual demo: ingest one Bilibili URL into workspace.

Usage examples:

  python scripts/demo_ingest_bilibili.py \
    --url "https://www.bilibili.com/video/BV1xxxxxx" \
    --cookie-file "D:/secrets/bilibili.cookies.txt"

  set BILIBILI_COOKIE_CONTENT=# Netscape cookie content...
  python scripts/demo_ingest_bilibili.py --url "https://www.bilibili.com/video/BV1xxxxxx"

Notes:
- Use only for content you are authorized to access.
- This script does not bypass DRM or platform restrictions.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
from pathlib import Path

from infra import FileSystemWorkspaceStore
from ingest import IngestError, IngestRequest, probe_url_formats, run_ingest


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo Bilibili URL ingest")
    parser.add_argument("--url", required=True, help="Bilibili video URL")
    parser.add_argument(
        "--list-formats",
        action="store_true",
        help="Probe URL and print available format options without downloading",
    )
    parser.add_argument(
        "--video-format-id", default=None, help="Specific video format id (e.g. 30116)"
    )
    parser.add_argument(
        "--audio-format-id", default=None, help="Specific audio format id (e.g. 30280)"
    )
    parser.add_argument(
        "--format-selector",
        default=None,
        help="Raw yt-dlp format selector, e.g. '30116+30280' or 'bv*+ba/b'",
    )
    parser.add_argument(
        "--format-sort",
        default=None,
        help="yt-dlp sort expression, e.g. 'res,fps,vcodec,acodec'",
    )
    parser.add_argument("--workspace-root", default="workspaces", help="Workspace root directory")
    parser.add_argument("--project-id", default=None, help="Optional fixed project id")
    parser.add_argument("--job-id", default=None, help="Optional fixed job id")
    parser.add_argument("--title", default=None, help="Optional title override")
    parser.add_argument("--description", default="", help="Optional description")
    parser.add_argument("--tag", action="append", dest="tags", default=[], help="Repeatable tag")
    parser.add_argument("--language-hint", default=None, help="Optional language hint, e.g. zh")
    parser.add_argument("--retries", type=int, default=2, help="Download retries")
    parser.add_argument("--cookie-file", default=None, help="Path to Netscape cookie file")
    parser.add_argument(
        "--cookie-env",
        default="BILIBILI_COOKIE_CONTENT",
        help="Env var containing Netscape cookie content",
    )
    args = parser.parse_args()

    project_id = args.project_id or _gen_id("p_demo")
    job_id = args.job_id or _gen_id("j_demo")

    cookie_content = None
    if args.cookie_env:
        cookie_content = os.environ.get(args.cookie_env)

    workspace = FileSystemWorkspaceStore(Path(args.workspace_root))
    request = IngestRequest(
        project_id=project_id,
        job_id=job_id,
        source_url=args.url,
        title=args.title,
        description=args.description,
        tags=args.tags,
        language_hint=args.language_hint,
        download_retries=args.retries,
        cookie_content=cookie_content,
        cookie_file_path=args.cookie_file,
        ytdlp_format=args.format_selector,
        ytdlp_sort=args.format_sort,
        video_format_id=args.video_format_id,
        audio_format_id=args.audio_format_id,
    )

    if args.list_formats:
        try:
            probe = probe_url_formats(request)
        except IngestError as exc:
            print("[demo] format probe failed")
            print(f"  code: {exc.code}")
            print(f"  message: {exc.message}")
            if exc.hint:
                print(f"  hint: {exc.hint}")
            return 1

        print("[demo] available formats")
        print(f"  title: {probe.title}")
        print(f"  uploader: {probe.uploader}")
        print(f"  duration_seconds: {probe.duration_seconds}")
        print("  format_id | resolution | fps | tbr | vcodec | acodec | audio_only | video_only")
        for item in probe.formats:
            print(
                "  "
                f"{item.format_id:>8} | {item.resolution or '-':>10} | "
                f"{(item.fps or 0):>4.0f} | {(item.tbr or 0):>6.0f} | "
                f"{(item.vcodec or '-'):>10} | {(item.acodec or '-'):>10} | "
                f"{str(item.is_audio_only):>10} | {str(item.is_video_only):>10}"
            )
        return 0

    print("[demo] starting ingest")
    print(f"[demo] project_id={project_id} job_id={job_id}")

    try:
        result = run_ingest(workspace, request)
    except IngestError as exc:
        print("[demo] ingest failed")
        print(f"  code: {exc.code}")
        print(f"  message: {exc.message}")
        if exc.hint:
            print(f"  hint: {exc.hint}")
        if exc.context:
            print(f"  context: {json.dumps(exc.context, ensure_ascii=False)}")
        return 1

    print("[demo] ingest succeeded")
    print(f"  source_video_path: {result.source_video_path}")
    print(f"  meta_path: {result.meta_path}")
    print(f"  retry_count: {result.retry_count}")
    print(f"  title: {result.meta.title}")
    print(f"  uploader: {result.meta.uploader}")
    print(f"  duration_seconds: {result.meta.duration_seconds}")
    print(f"  selected_format: {result.meta.selected_format}")
    print(f"  selected_video_format_id: {result.meta.selected_video_format_id}")
    print(f"  selected_audio_format_id: {result.meta.selected_audio_format_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
