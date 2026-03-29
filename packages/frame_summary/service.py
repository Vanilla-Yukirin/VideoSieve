"""VLM frame summarization service writing ``frame_summary/frame_summary.jsonl``."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from infra.interfaces import WorkspaceStore

from .providers import FrameSummaryProvider, FrameSummaryResult


class _RpmLimiter:
    """Sliding-window rate limiter: at most ``rpm`` calls per 60 seconds.

    Pass ``rpm <= 0`` to disable rate limiting entirely.
    """

    def __init__(self, rpm: int) -> None:
        self._rpm = rpm
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> None:
        if self._rpm <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                cutoff = now - 60.0
                self._timestamps = [t for t in self._timestamps if t > cutoff]
                if len(self._timestamps) < self._rpm:
                    self._timestamps.append(now)
                    return
                wait_until = self._timestamps[0] + 60.0
                wait = wait_until - now
            if wait > 0:
                time.sleep(wait + 0.05)


class QwenFrameSummaryProvider:
    """Qwen-compatible provider for free-text frame summaries."""

    # Built-in default prompts — also used as fallback when DB value is empty
    DEFAULT_PROMPT_ZH = (
        "请直接用自然语言回答，不要JSON。"
        "请对当前画面做一段完整描述，优先覆盖主要内容、上方区域信息、下方区域信息、可见文字和图示关系。"
    )
    DEFAULT_PROMPT_EN = (
        "Respond in plain natural language, not JSON. "
        "Give a complete frame description, including main content, upper area details, "
        "lower area details, visible text, and diagram relationships."
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        prompt_zh: str | None = None,
        prompt_en: str | None = None,
    ) -> None:
        self._api_key = (api_key or os.getenv("QWEN_API_KEY") or "").strip()
        self._endpoint = (
            endpoint
            or os.getenv("QWEN_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        )
        self._model = model or os.getenv("VLM_MODEL") or "qwen3.5-plus"
        raw_timeout = timeout_seconds or float(os.getenv("VLM_TIMEOUT_SECONDS", "60"))
        self._timeout_seconds = max(5.0, raw_timeout)
        self._prompt_zh = prompt_zh or None
        self._prompt_en = prompt_en or None

    @property
    def adapter_name(self) -> str:
        return "qwen_frame_summary"

    def _build_prompt(self, *, language_hint: str | None) -> str:
        lang = (language_hint or "zh").strip().lower()
        if lang.startswith("zh"):
            return self._prompt_zh or self.DEFAULT_PROMPT_ZH
        return self._prompt_en or self.DEFAULT_PROMPT_EN

    @staticmethod
    def _image_data_url(image_path: Path) -> str:
        mime = "image/jpeg"
        suffix = image_path.suffix.lower()
        if suffix == ".png":
            mime = "image/png"
        encoded = b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    def _offline_text(self, frame_id: str, image_path: Path) -> str:
        label = image_path.stem or frame_id
        return f"[offline frame summary] frame {label}. No remote model response is available."

    def summarize_frame(
        self,
        frame_id: str,
        image_path: Path,
        *,
        language_hint: str | None = None,
    ) -> FrameSummaryResult:
        lang = language_hint or "und"
        if not self._api_key:
            text = self._offline_text(frame_id, image_path)
            return FrameSummaryResult(
                frame_id=frame_id,
                lang=lang,
                provider=self.adapter_name,
                description_text=text,
            )

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self._build_prompt(language_hint=language_hint),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": self._image_data_url(image_path)},
                        },
                    ],
                }
            ],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError):
            text = self._offline_text(frame_id, image_path)
            return FrameSummaryResult(
                frame_id=frame_id,
                lang=lang,
                provider=self.adapter_name,
                description_text=text,
            )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        text = _extract_message_text(parsed).strip() or self._offline_text(frame_id, image_path)
        return FrameSummaryResult(
            frame_id=frame_id,
            lang=lang,
            provider=self.adapter_name,
            description_text=text,
        )


def _extract_message_text(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks)
    return ""


class FrameSummaryService:
    """Read keyframes and output ``frame_summary/frame_summary.jsonl``."""

    def __init__(self, workspace_store: WorkspaceStore, provider: FrameSummaryProvider) -> None:
        self._workspace_store = workspace_store
        self._provider = provider

    def run(
        self,
        project_id: str,
        job_id: str,
        *,
        language_hint: str | None = None,
        concurrency: int = 5,
        rpm: int = 30,
    ) -> list[FrameSummaryResult]:
        self._workspace_store.ensure_job_layout(project_id, job_id)

        keyframes_file = self._workspace_store.keyframes_file(project_id, job_id)
        out_path = self._workspace_store.frame_summary_file(project_id, job_id)

        if not keyframes_file.exists():
            self._write_jsonl(out_path, [])
            return []

        keyframes: list[dict[str, object]] = []
        with keyframes_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    keyframes.append(json.loads(line))

        if not keyframes:
            self._write_jsonl(out_path, [])
            return []

        limiter = _RpmLimiter(rpm)
        file_lock = threading.Lock()
        results: list[FrameSummaryResult] = []

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("", encoding="utf-8")  # create / clear before streaming

        with out_path.open("a", encoding="utf-8") as outfile:

            def _process_and_write(kf_payload: dict) -> FrameSummaryResult:
                frame_id = str(kf_payload["frame_id"])
                image_path = Path(str(kf_payload["path"]))
                limiter.acquire()
                record = self._provider.summarize_frame(
                    frame_id, image_path, language_hint=language_hint
                )
                with file_lock:
                    outfile.write(json.dumps(record.to_json(), ensure_ascii=False) + "\n")
                    outfile.flush()
                return record

            with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
                futures = [pool.submit(_process_and_write, kf) for kf in keyframes]
                for fut in as_completed(futures):
                    results.append(fut.result())

        return results

    @staticmethod
    def _write_jsonl(path: Path, rows: list[FrameSummaryResult]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row.to_json(), ensure_ascii=False) + "\n")
