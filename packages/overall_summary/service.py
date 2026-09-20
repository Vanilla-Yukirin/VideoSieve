"""Generate a real model-backed overall summary from all timeline evidence."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from contracts.models import SCHEMA_VERSION
from infra.interfaces import WorkspaceStore

from .providers import OverallSummaryProvider, OverallSummaryProviderError, OverallSummaryResult


class OpenAICompatibleSummaryProvider:
    """OpenAI-compatible chat-completions adapter for overall summaries."""

    DEFAULT_PROMPT_ZH = (
        "你是视频内容摘要助手。仅依据给定的完整转写和画面证据，输出准确、连贯的中文摘要。"
        "覆盖核心主题、关键观点、重要结论和必要的上下文；不要编造证据中没有的信息。"
    )
    DEFAULT_PROMPT_EN = (
        "Summarize the complete transcript and visual evidence accurately and coherently. "
        "Cover the main topic, key points, conclusions, and necessary context. "
        "Do not invent information that is absent from the evidence."
    )

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        prompt_zh: str | None = None,
        prompt_en: str | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._base_url = base_url.strip()
        self._model = model.strip()
        key_value = api_key if api_key is not None else os.getenv("SUMMARY_API_KEY", "")
        self._api_key = key_value.strip()
        self._prompt_zh = (prompt_zh or self.DEFAULT_PROMPT_ZH).strip()
        self._prompt_en = (prompt_en or self.DEFAULT_PROMPT_EN).strip()
        self._timeout_seconds = timeout_seconds

    @property
    def provider_name(self) -> str:
        return "openai_compatible_summary"

    @property
    def model_name(self) -> str:
        return self._model

    def summarize(
        self,
        source_text: str,
        *,
        language_hint: str | None,
        partial: bool,
    ) -> OverallSummaryResult:
        if not self._api_key:
            raise OverallSummaryProviderError(
                "OVERALL_SUMMARY_CONFIG_MISSING",
                "SUMMARY_API_KEY is required for overall summary generation",
            )
        if not self._base_url or not self._model:
            raise OverallSummaryProviderError(
                "OVERALL_SUMMARY_CONFIG_MISSING",
                "summary base URL and model are required",
            )
        if not source_text.strip():
            raise OverallSummaryProviderError(
                "OVERALL_SUMMARY_INPUT_EMPTY",
                "overall summary evidence is empty",
            )

        is_zh = (language_hint or "zh").lower().startswith("zh")
        system_prompt = self._prompt_zh if is_zh else self._prompt_en
        if partial:
            task = (
                "这是完整材料的一部分。请压缩为保留全部关键信息的中间摘要，供下一轮综合。"
                if is_zh
                else (
                    "This is one partition of the full evidence. "
                    "Preserve every key fact for final synthesis."
                )
            )
        else:
            task = (
                "请基于以下全部材料生成最终摘要。"
                if is_zh
                else "Create the final summary from all evidence below."
            )
        body = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{task}\n\n{source_text}"},
                ],
                "temperature": 0.2,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self._base_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise OverallSummaryProviderError(
                "OVERALL_SUMMARY_PROVIDER_HTTP_ERROR",
                f"overall summary provider returned HTTP {exc.code}",
                retryable=exc.code == 429 or exc.code >= 500,
            ) from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            raise OverallSummaryProviderError(
                "OVERALL_SUMMARY_PROVIDER_UNAVAILABLE",
                "overall summary provider request failed",
                retryable=True,
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OverallSummaryProviderError(
                "OVERALL_SUMMARY_INVALID_RESPONSE",
                "overall summary provider returned invalid JSON",
            ) from exc

        content = self._extract_content(payload)
        if not content:
            raise OverallSummaryProviderError(
                "OVERALL_SUMMARY_EMPTY_RESPONSE",
                "overall summary provider returned empty content",
            )
        return OverallSummaryResult(
            text=content,
            provider=self.provider_name,
            model=self.model_name,
        )

    @staticmethod
    def _extract_content(payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return ""
        message = choices[0].get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        return content.strip() if isinstance(content, str) else ""


class OverallSummaryService:
    """Collect every text/visual evidence row and synthesize a final summary."""

    def __init__(
        self,
        workspace_store: WorkspaceStore,
        provider: OverallSummaryProvider,
        *,
        max_input_chars: int = 24_000,
    ) -> None:
        if max_input_chars < 1_000:
            raise ValueError("max_input_chars must be at least 1000")
        self._workspace_store = workspace_store
        self._provider = provider
        self._max_input_chars = max_input_chars

    def run(
        self,
        project_id: str,
        *,
        job_id: str,
        language_hint: str | None = None,
    ) -> Path:
        output_path: Path = self._workspace_store.summary_file(project_id, job_id)
        output_path.unlink(missing_ok=True)
        timeline_path = self._workspace_store.timeline_file(project_id, job_id)
        if not timeline_path.exists():
            raise FileNotFoundError(timeline_path)

        sections = self._read_timeline_sections(timeline_path)
        sections.extend(
            self._read_frame_summary_sections(
                self._workspace_store.frame_summary_file(project_id, job_id)
            )
        )
        if not sections:
            raise OverallSummaryProviderError(
                "OVERALL_SUMMARY_INPUT_EMPTY",
                "timeline and frame summary evidence are empty",
            )

        result = self._summarize_hierarchically(sections, language_hint=language_hint)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        payload = {
            "schema_version": SCHEMA_VERSION,
            "title": f"Summary for {project_id}",
            "summary": result.text,
            "provider": result.provider,
            "model": result.model,
            "source_sections": len(sections),
        }
        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temp_path.replace(output_path)
        finally:
            temp_path.unlink(missing_ok=True)
        return output_path

    def _partition(self, sections: list[str]) -> list[str]:
        batches: list[str] = []
        current: list[str] = []
        current_length = 0
        for section in sections:
            for piece in self._split_section(section):
                separator_length = 2 if current else 0
                next_length = current_length + separator_length + len(piece)
                if current and next_length > self._max_input_chars:
                    batches.append("\n\n".join(current))
                    current = []
                    current_length = 0
                    separator_length = 0
                current.append(piece)
                current_length += separator_length + len(piece)
        if current:
            batches.append("\n\n".join(current))
        return batches

    def _summarize_hierarchically(
        self,
        sections: list[str],
        *,
        language_hint: str | None,
    ) -> OverallSummaryResult:
        round_sections = sections
        for round_index in range(1, 17):
            batches = self._partition(round_sections)
            if len(batches) == 1:
                result = self._provider.summarize(
                    batches[0], language_hint=language_hint, partial=False
                )
                self._validate_result(result)
                return result

            partials: list[str] = []
            for batch in batches:
                partial_result = self._provider.summarize(
                    batch, language_hint=language_hint, partial=True
                )
                self._validate_result(partial_result)
                partials.append(partial_result.text)
            next_sections = [
                f"[REDUCTION ROUND {round_index} PART {index}]\n{text}"
                for index, text in enumerate(partials, start=1)
            ]
            if len(self._partition(next_sections)) >= len(batches):
                raise OverallSummaryProviderError(
                    "OVERALL_SUMMARY_CONTEXT_NOT_REDUCED",
                    "partial summaries did not reduce the evidence enough for final synthesis",
                )
            round_sections = next_sections

        raise OverallSummaryProviderError(
            "OVERALL_SUMMARY_REDUCTION_LIMIT",
            "overall summary exceeded the maximum hierarchical reduction rounds",
        )

    def _split_section(self, section: str) -> list[str]:
        if len(section) <= self._max_input_chars:
            return [section]
        marker_budget = 48
        content_budget = self._max_input_chars - marker_budget
        if content_budget <= 0:
            raise ValueError("max_input_chars is too small for section markers")
        pieces = [
            section[offset : offset + content_budget]
            for offset in range(0, len(section), content_budget)
        ]
        return [
            f"[SECTION CONTINUATION {index}/{len(pieces)}]\n{piece}"
            for index, piece in enumerate(pieces, start=1)
        ]

    @staticmethod
    def _validate_result(result: OverallSummaryResult) -> None:
        if not result.text.strip() or not result.provider.strip() or not result.model.strip():
            raise OverallSummaryProviderError(
                "OVERALL_SUMMARY_INVALID_RESULT",
                "overall summary provider returned an incomplete result",
            )

    @staticmethod
    def _read_timeline_sections(path: Path) -> list[str]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        chunks = payload.get("chunks") if isinstance(payload, dict) else None
        if not isinstance(chunks, list):
            raise ValueError("timeline chunks must be a list")
        sections: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            if not isinstance(chunk, dict):
                continue
            text = str(chunk.get("text") or "").strip()
            if text:
                sections.append(f"[TRANSCRIPT {index}]\n{text}")
        return sections

    @staticmethod
    def _read_frame_summary_sections(path: Path) -> list[str]:
        if not path.exists():
            return []
        sections: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                continue
            text = str(payload.get("description_text") or "").strip()
            frame_id = str(payload.get("frame_id") or "unknown")
            if text:
                sections.append(f"[FRAME {frame_id}]\n{text}")
        return sections
