"""VLM frame summarization service writing ``frame_summary/frame_summary.jsonl``."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from base64 import b64encode
from pathlib import Path

from infra.interfaces import WorkspaceStore

from .providers import FrameSummaryProvider, FrameSummaryResult


class QwenFrameSummaryProvider:
    """Qwen-compatible provider for free-text frame summaries."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
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

    @property
    def adapter_name(self) -> str:
        return "qwen_frame_summary"

    def _build_prompt(self, *, language_hint: str | None) -> str:
        lang = (language_hint or "zh").strip().lower()
        if lang.startswith("zh"):
            return (
                "请直接用自然语言回答，不要JSON。"
                "请对当前画面做一段完整描述，优先覆盖主要内容、上方区域信息、下方区域信息、可见文字和图示关系。"
            )
        return (
            "Respond in plain natural language, not JSON. "
            "Give a complete frame description, including main content, upper area details, "
            "lower area details, visible text, and diagram relationships."
        )

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
        self, project_id: str, job_id: str, *, language_hint: str | None = None
    ) -> list[FrameSummaryResult]:
        self._workspace_store.ensure_job_layout(project_id, job_id)

        keyframes_file = self._workspace_store.keyframes_file(project_id, job_id)
        if not keyframes_file.exists():
            self._write_jsonl(self._workspace_store.frame_summary_file(project_id, job_id), [])
            return []

        results: list[FrameSummaryResult] = []
        with keyframes_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                payload = json.loads(line)
                frame_id = payload["frame_id"]
                image_path = Path(payload["path"])
                results.append(
                    self._provider.summarize_frame(
                        frame_id,
                        image_path,
                        language_hint=language_hint,
                    )
                )

        self._write_jsonl(self._workspace_store.frame_summary_file(project_id, job_id), results)
        return results

    @staticmethod
    def _write_jsonl(path: Path, rows: list[FrameSummaryResult]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row.to_json(), ensure_ascii=False) + "\n")
