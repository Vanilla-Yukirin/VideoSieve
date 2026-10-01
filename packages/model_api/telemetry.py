"""Persist provider-reported usage and measured request time without model text."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelCallAttempt:
    call_id: str
    attempt: int
    protocol: str
    model: str
    elapsed_ms: int
    finish_reason: str | None
    usage: dict[str, Any] | None
    request_id: str | None
    error_code: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def empty_usage_summary() -> dict[str, Any]:
    return {"calls": 0, "failed_calls": 0, "elapsed_ms": 0, "stages": {}}


def read_usage_summary(job_root: Path) -> dict[str, Any]:
    """Reconstruct from complete journal lines; a crash may leave a trailing partial line."""
    path = job_root / "meta" / "model_calls.jsonl"
    if not path.exists():
        return empty_usage_summary()
    result = empty_usage_summary()
    # Decode each row independently: a crash can cut a model alias's UTF-8
    # sequence, and decoding the whole stream would hide even complete rows.
    with path.open("rb") as handle:
        for line in handle:
            try:
                row = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(row, dict):
                _add_usage(result, row)
    return result


def _number(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _add_usage(summary: dict[str, Any], row: dict[str, Any]) -> None:
    summary["calls"] += 1
    summary["failed_calls"] += int(row.get("error_code") is not None)
    summary["elapsed_ms"] += _number(row.get("elapsed_ms")) or 0
    stage = summary["stages"].setdefault(
        str(row.get("stage", "unknown")),
        {
            "calls": 0,
            "failed_calls": 0,
            "elapsed_ms": 0,
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "cached_tokens": None,
            "reasoning_tokens": None,
            "usage_missing_calls": 0,
            "missing_fields": {},
        },
    )
    stage["calls"] += 1
    stage["failed_calls"] += int(row.get("error_code") is not None)
    stage["elapsed_ms"] += _number(row.get("elapsed_ms")) or 0
    usage = row.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    if not usage:
        stage["usage_missing_calls"] += 1
    input_details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    output_details = (
        usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
    )
    reasoning_tokens = (
        output_details.get("reasoning_tokens") if isinstance(output_details, dict) else None
    )
    if row.get("protocol") == "anthropic_messages":
        anthropic_details = usage.get("output_tokens_details")
        if isinstance(anthropic_details, dict):
            # Anthropic's thinking count is already included in output_tokens.
            thinking_tokens = _number(anthropic_details.get("thinking_tokens"))
            if thinking_tokens is not None:
                reasoning_tokens = thinking_tokens
    fields = {
        "input_tokens": usage.get("input_tokens", usage.get("prompt_tokens")),
        "output_tokens": usage.get("output_tokens", usage.get("completion_tokens")),
        "total_tokens": usage.get("total_tokens"),
        "cached_tokens": usage.get(
            "cache_read_input_tokens",
            usage.get(
                "prompt_cache_hit_tokens",
                input_details.get("cached_tokens") if isinstance(input_details, dict) else None,
            ),
        ),
        "reasoning_tokens": reasoning_tokens,
    }
    for key, value in fields.items():
        value = _number(value)
        if value is None:
            stage["missing_fields"][key] = stage["missing_fields"].get(key, 0) + 1
        else:
            stage[key] = (stage[key] or 0) + value


class ModelCallJournal:
    """One job journal shared across concurrent frame requests and stages."""

    def __init__(self, job_root: Path, worker_attempt: int | None = None) -> None:
        self._root = job_root
        self._worker_attempt = worker_attempt
        self._lock = threading.Lock()
        self._summary = read_usage_summary(job_root)

    def record(self, stage: str, attempt: ModelCallAttempt) -> dict[str, Any]:
        row = attempt.to_json() | {"stage": stage, "worker_attempt": self._worker_attempt}
        with self._lock:
            path = self._root / "meta" / "model_calls.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_size:
                with path.open("rb+") as handle:
                    handle.seek(-1, 2)
                    if handle.read(1) != b"\n":
                        # Isolate a crash's partial tail from the next valid row.
                        handle.seek(0, 2)
                        handle.write(b"\n")
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            _add_usage(self._summary, row)
            # Return an independent snapshot for the event bus.
            return json.loads(json.dumps(self._summary))  # type: ignore[no-any-return]
