"""Generate a real model-backed overall summary from all timeline evidence."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from contracts.models import SCHEMA_VERSION
from infra.interfaces import WorkspaceStore

from .evidence import (
    evidence_sha256,
    read_frame_summary_evidence,
    read_timeline_evidence,
    sha256_file,
    sha256_json,
    sha256_text,
)
from .providers import (
    OverallSummaryProvider,
    OverallSummaryProviderError,
    OverallSummaryResult,
    SummaryProviderProvenance,
)

_PROMPT_VERSION = "overall-summary-v1"
_REDUCTION_STRATEGY = "hierarchical-map-reduce-v1"
_MAX_REDUCTION_ROUNDS = 16
_TEMPERATURE = 0.2
_PARTIAL_TASK_ZH = "这是完整材料的一部分。请压缩为保留全部关键信息的中间摘要，供下一轮综合。"
_PARTIAL_TASK_EN = (
    "This is one partition of the full evidence. Preserve every key fact for final synthesis."
)
_FINAL_TASK_ZH = "请基于以下全部材料生成最终摘要。"
_FINAL_TASK_EN = "Create the final summary from all evidence below."


@dataclass(frozen=True)
class _SummaryExecution:
    result: OverallSummaryResult
    provider_calls: int
    reduction_rounds: int


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
        allow_env_fallback: bool = True,
    ) -> None:
        self._base_url = base_url.strip()
        self._model = model.strip()
        key_value = api_key
        if key_value is None and allow_env_fallback:
            key_value = os.getenv("SUMMARY_API_KEY", "")
        self._api_key = (key_value or "").strip()
        self._prompt_zh = (prompt_zh or self.DEFAULT_PROMPT_ZH).strip()
        self._prompt_en = (prompt_en or self.DEFAULT_PROMPT_EN).strip()
        self._timeout_seconds = timeout_seconds

    @property
    def provider_name(self) -> str:
        return "openai_compatible_summary"

    @property
    def model_name(self) -> str:
        return self._model

    def describe_provenance(
        self, *, language_hint: str | None
    ) -> SummaryProviderProvenance:
        """Describe the selected prompt and request parameters without secrets."""

        is_zh = (language_hint or "zh").lower().startswith("zh")
        prompt = self._prompt_zh if is_zh else self._prompt_en
        return SummaryProviderProvenance(
            provider=self.provider_name,
            model=self.model_name,
            prompt_version=_PROMPT_VERSION,
            prompt_sha256=sha256_json(
                {
                    "system": prompt,
                    "partial_task": _PARTIAL_TASK_ZH if is_zh else _PARTIAL_TASK_EN,
                    "final_task": _FINAL_TASK_ZH if is_zh else _FINAL_TASK_EN,
                }
            ),
            endpoint_sha256=sha256_text(self._base_url),
            parameters={
                "temperature": _TEMPERATURE,
                "timeout_seconds": self._timeout_seconds,
                "api": "openai-compatible-chat-completions",
            },
        )

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
            task = _PARTIAL_TASK_ZH if is_zh else _PARTIAL_TASK_EN
        else:
            task = _FINAL_TASK_ZH if is_zh else _FINAL_TASK_EN
        body = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{task}\n\n{source_text}"},
                ],
                "temperature": _TEMPERATURE,
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
        output_path: Path | None = None,
    ) -> Path:
        canonical_output = self._workspace_store.summary_file(project_id, job_id)
        publish_path = output_path or canonical_output
        job_root = self._workspace_store.job_root(project_id, job_id).resolve()
        resolved_output = publish_path.resolve()
        if not resolved_output.is_relative_to(job_root):
            raise ValueError("summary output path escapes the job workspace")
        if publish_path == canonical_output:
            self._workspace_store.deliverables_manifest_file(project_id, job_id).unlink(
                missing_ok=True
            )
        publish_path.unlink(missing_ok=True)
        timeline_path = self._workspace_store.timeline_file(project_id, job_id)
        if not timeline_path.exists():
            raise FileNotFoundError(timeline_path)

        timeline = read_timeline_evidence(
            timeline_path,
            project_id=project_id,
            job_id=job_id,
            error_code="OVERALL_SUMMARY_INPUT_INVALID",
        )
        evidence_sections = list(timeline.sections)
        evidence_sections.extend(
            read_frame_summary_evidence(
                self._workspace_store.frame_summary_file(project_id, job_id),
                error_code="OVERALL_SUMMARY_INPUT_INVALID",
            )
        )
        if not evidence_sections:
            raise OverallSummaryProviderError(
                "OVERALL_SUMMARY_INPUT_EMPTY",
                "timeline and frame summary evidence are empty",
            )

        rendered_sections = [section.render() for section in evidence_sections]
        execution = self._summarize_hierarchically(
            rendered_sections,
            language_hint=language_hint,
        )
        provider_provenance = self._describe_provider(language_hint=language_hint)
        summary_config = {
            "provider": provider_provenance.provider,
            "model": provider_provenance.model,
            "prompt_version": provider_provenance.prompt_version,
            "prompt_sha256": provider_provenance.prompt_sha256,
            "endpoint_sha256": provider_provenance.endpoint_sha256,
            "parameters": provider_provenance.parameters,
            "max_input_chars": self._max_input_chars,
            "reduction_strategy": _REDUCTION_STRATEGY,
            "max_reduction_rounds": _MAX_REDUCTION_ROUNDS,
            "language_hint": language_hint,
        }
        config_path = self._workspace_store.config_snapshot_file(project_id, job_id)
        source_ids = [section.source_id for section in evidence_sections]
        transcript_count = sum(
            section.source_type == "transcript" for section in evidence_sections
        )
        frame_count = len(evidence_sections) - transcript_count
        provenance = {
            "generated_at": datetime.now(UTC).isoformat(),
            "input_sha256": evidence_sha256(evidence_sections),
            "summary_config_sha256": sha256_json(summary_config),
            "job_config_sha256": sha256_file(config_path) if config_path.exists() else None,
            "source_ids": source_ids,
            "coverage": {
                "validated_source_count": len(evidence_sections),
                "summarized_source_count": len(evidence_sections),
                "transcript_section_count": transcript_count,
                "frame_section_count": frame_count,
                "coverage_ratio": 1.0,
            },
            "provider": provider_provenance.provider,
            "model": provider_provenance.model,
            "prompt_version": provider_provenance.prompt_version,
            "prompt_sha256": provider_provenance.prompt_sha256,
            "endpoint_sha256": provider_provenance.endpoint_sha256,
            "parameters": {
                **provider_provenance.parameters,
                "max_input_chars": self._max_input_chars,
                "reduction_strategy": _REDUCTION_STRATEGY,
                "max_reduction_rounds": _MAX_REDUCTION_ROUNDS,
            },
            "execution": {
                "provider_calls": execution.provider_calls,
                "reduction_rounds": execution.reduction_rounds,
            },
        }
        publish_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = publish_path.with_suffix(publish_path.suffix + ".tmp")
        payload = {
            "schema_version": SCHEMA_VERSION,
            "title": f"Summary for {project_id}",
            "summary": execution.result.text,
            "provider": execution.result.provider,
            "model": execution.result.model,
            "source_sections": len(evidence_sections),
            "provenance": provenance,
        }
        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temp_path.replace(publish_path)
        finally:
            temp_path.unlink(missing_ok=True)
        return publish_path

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
    ) -> _SummaryExecution:
        round_sections = sections
        provider_calls = 0
        for round_index in range(1, _MAX_REDUCTION_ROUNDS + 1):
            batches = self._partition(round_sections)
            if len(batches) == 1:
                result = self._provider.summarize(
                    batches[0], language_hint=language_hint, partial=False
                )
                provider_calls += 1
                self._validate_result(result)
                return _SummaryExecution(
                    result=result,
                    provider_calls=provider_calls,
                    reduction_rounds=round_index - 1,
                )

            partials: list[str] = []
            for batch in batches:
                partial_result = self._provider.summarize(
                    batch, language_hint=language_hint, partial=True
                )
                provider_calls += 1
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

    def _validate_result(self, result: OverallSummaryResult) -> None:
        if not result.text.strip() or not result.provider.strip() or not result.model.strip():
            raise OverallSummaryProviderError(
                "OVERALL_SUMMARY_INVALID_RESULT",
                "overall summary provider returned an incomplete result",
            )
        if (
            result.provider != self._provider.provider_name
            or result.model != self._provider.model_name
        ):
            raise OverallSummaryProviderError(
                "OVERALL_SUMMARY_INVALID_RESULT",
                "overall summary result provenance does not match the configured provider",
            )

    def _describe_provider(self, *, language_hint: str | None) -> SummaryProviderProvenance:
        describe = getattr(self._provider, "describe_provenance", None)
        if callable(describe):
            provenance = describe(language_hint=language_hint)
            if isinstance(provenance, SummaryProviderProvenance):
                return provenance
        return SummaryProviderProvenance(
            provider=self._provider.provider_name,
            model=self._provider.model_name,
            prompt_version=None,
            prompt_sha256=None,
            endpoint_sha256=None,
            parameters={},
        )
