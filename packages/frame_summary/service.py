"""VLM frame summarization service writing ``frame_summary/frame_summary.jsonl``."""

from __future__ import annotations

import json
import os
import threading
import time
from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from infra.interfaces import WorkspaceStore
from model_api import ModelApiError, request_model_text

from .providers import FrameSummaryProvider, FrameSummaryProviderError, FrameSummaryResult


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
    """Protocol-selectable provider for free-text frame summaries.

    The historical class name remains as a compatibility alias for callers and
    stored provenance. New profiles select an explicit wire protocol.
    """

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
        protocol: str = "openai_chat_completions",
        auth_mode: str | None = None,
        timeout_seconds: float | None = None,
        prompt_zh: str | None = None,
        prompt_en: str | None = None,
        allow_env_fallback: bool = True,
    ) -> None:
        key_value = api_key
        if key_value is None and allow_env_fallback:
            key_value = os.getenv("QWEN_API_KEY")
        self._api_key = (key_value or "").strip()
        self._endpoint = (
            endpoint
            or os.getenv("QWEN_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        )
        self._model = model or os.getenv("VLM_MODEL") or "qwen3.5-plus"
        self._protocol = protocol
        self._auth_mode = auth_mode
        raw_timeout = timeout_seconds or float(os.getenv("VLM_TIMEOUT_SECONDS", "60"))
        self._timeout_seconds = max(5.0, raw_timeout)
        self._prompt_zh = prompt_zh or None
        self._prompt_en = prompt_en or None

    @property
    def adapter_name(self) -> str:
        return f"model_frame_summary:{self._protocol}"

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

    def summarize_frame(
        self,
        frame_id: str,
        image_path: Path,
        *,
        language_hint: str | None = None,
    ) -> FrameSummaryResult:
        lang = language_hint or "und"
        if not self._api_key:
            raise FrameSummaryProviderError(
                "FRAME_SUMMARY_CONFIG_MISSING",
                "an API key is required for frame summary generation",
                retryable=False,
            )

        try:
            text = request_model_text(
                protocol=self._protocol,
                api_root=self._endpoint,
                model=self._model,
                api_key=self._api_key,
                system_prompt=(
                    "Describe only what is visible in the supplied video frame. "
                    "Do not invent missing context."
                ),
                user_text=self._build_prompt(language_hint=language_hint),
                image_data_url=self._image_data_url(image_path),
                timeout_seconds=self._timeout_seconds,
                auth_mode=self._auth_mode,
            )
        except (ModelApiError, ValueError) as exc:
            code = {
                "MODEL_CONFIG_MISSING": "FRAME_SUMMARY_CONFIG_MISSING",
                "MODEL_PROVIDER_HTTP_ERROR": "FRAME_SUMMARY_PROVIDER_HTTP_ERROR",
                "MODEL_PROVIDER_UNAVAILABLE": "FRAME_SUMMARY_PROVIDER_UNAVAILABLE",
                "MODEL_INVALID_RESPONSE": "FRAME_SUMMARY_INVALID_RESPONSE",
                "MODEL_EMPTY_RESPONSE": "FRAME_SUMMARY_EMPTY_RESPONSE",
            }.get(getattr(exc, "code", ""), "FRAME_SUMMARY_CONFIG_INVALID")
            raise FrameSummaryProviderError(
                code,
                str(exc),
                retryable=(
                    bool(getattr(exc, "retryable", False))
                    or code
                    in {
                        "FRAME_SUMMARY_INVALID_RESPONSE",
                        "FRAME_SUMMARY_EMPTY_RESPONSE",
                    }
                ),
            ) from exc
        return FrameSummaryResult(
            frame_id=frame_id,
            lang=lang,
            provider=self.adapter_name,
            description_text=text,
        )
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
        out_path.unlink(missing_ok=True)
        out_path.with_suffix(f"{out_path.suffix}.tmp").unlink(missing_ok=True)

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
        results_by_frame_id: dict[str, FrameSummaryResult] = {}

        def _process(kf_payload: dict[str, object]) -> FrameSummaryResult:
            frame_id = str(kf_payload["frame_id"])
            image_path = Path(str(kf_payload["path"]))
            limiter.acquire()
            return self._provider.summarize_frame(
                frame_id, image_path, language_hint=language_hint
            )

        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            futures = [pool.submit(_process, kf) for kf in keyframes]
            for future in as_completed(futures):
                result = future.result()
                results_by_frame_id[result.frame_id] = result

        results = [
            results_by_frame_id[str(keyframe["frame_id"])]
            for keyframe in keyframes
            if str(keyframe["frame_id"]) in results_by_frame_id
        ]
        self._write_jsonl_atomic(out_path, results)
        return results

    @staticmethod
    def _write_jsonl(path: Path, rows: list[FrameSummaryResult]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row.to_json(), ensure_ascii=False) + "\n")

    @classmethod
    def _write_jsonl_atomic(cls, path: Path, rows: list[FrameSummaryResult]) -> None:
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        try:
            cls._write_jsonl(temp_path, rows)
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)
