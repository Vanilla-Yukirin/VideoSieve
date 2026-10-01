from __future__ import annotations

import json
from pathlib import Path

import pytest

from model_api import ModelCallAttempt, ModelCallJournal, read_usage_summary


def _attempt(call_id: str, input_tokens: int) -> ModelCallAttempt:
    return ModelCallAttempt(
        call_id=call_id,
        attempt=1,
        protocol="openai_chat_completions",
        model="本地视觉模型",
        elapsed_ms=10,
        finish_reason="stop",
        usage={"prompt_tokens": input_tokens, "completion_tokens": 2},
        request_id=None,
    )


@pytest.mark.parametrize("utf8_prefix_length", [1, 2])
def test_journal_preserves_history_and_resumes_after_unicode_crash_tail(
    tmp_path: Path, utf8_prefix_length: int
) -> None:
    journal = ModelCallJournal(tmp_path, worker_attempt=1)
    journal.record("frame_summary", _attempt("completed-before-crash", 7))
    path = tmp_path / "meta/model_calls.jsonl"
    complete_history = path.read_bytes()
    pending_row = json.dumps(
        _attempt("interrupted-write", 999).to_json(), ensure_ascii=False
    ).encode("utf-8")
    cut_at = pending_row.index("本".encode()) + utf8_prefix_length
    partial_tail = pending_row[:cut_at]
    with path.open("ab") as handle:
        handle.write(partial_tail)

    before_resume = read_usage_summary(tmp_path)
    assert before_resume["calls"] == 1
    assert before_resume["stages"]["frame_summary"]["input_tokens"] == 7

    resumed = ModelCallJournal(tmp_path, worker_attempt=2)
    after_resume = resumed.record("deliverables", _attempt("completed-after-restart", 11))
    assert after_resume == read_usage_summary(tmp_path)
    assert after_resume["calls"] == 2
    assert after_resume["stages"]["frame_summary"]["input_tokens"] == 7
    assert after_resume["stages"]["deliverables"]["input_tokens"] == 11
    assert path.read_bytes().startswith(complete_history + partial_tail + b"\n")


@pytest.mark.parametrize(
    ("protocol", "details", "expected_reasoning"),
    [
        ("anthropic_messages", {"thinking_tokens": 90}, 90),
        ("anthropic_messages", {"thinking_tokens": 0}, 0),
        ("anthropic_messages", {}, None),
        ("anthropic_messages", {"reasoning_tokens": 90}, 90),
        ("anthropic_messages", {"reasoning_tokens": 0}, 0),
        ("anthropic_messages", {"thinking_tokens": 0, "reasoning_tokens": 90}, 0),
        ("openai_chat_completions", {"reasoning_tokens": 90}, 90),
        ("openai_responses", {"reasoning_tokens": 0}, 0),
        ("openai_chat_completions", {"thinking_tokens": 90}, None),
    ],
)
def test_journal_maps_reported_reasoning_without_changing_inclusive_usage(
    tmp_path: Path,
    protocol: str,
    details: dict[str, int],
    expected_reasoning: int | None,
) -> None:
    usage: dict[str, object]
    if protocol == "openai_chat_completions":
        usage = {
            "prompt_tokens": 20,
            "completion_tokens": 120,
            "total_tokens": 140,
            "completion_tokens_details": details,
        }
    else:
        usage = {
            "input_tokens": 20,
            "output_tokens": 120,
            "output_tokens_details": details,
        }
        if protocol == "openai_responses":
            usage["total_tokens"] = 140
    journal = ModelCallJournal(tmp_path)
    summary = journal.record(
        "deliverables",
        ModelCallAttempt(
            call_id="reported-reasoning",
            attempt=1,
            protocol=protocol,
            model="model",
            elapsed_ms=10,
            finish_reason="end_turn" if protocol == "anthropic_messages" else "stop",
            usage=usage,
            request_id=None,
        ),
    )
    assert summary == read_usage_summary(tmp_path)
    stage = summary["stages"]["deliverables"]
    assert stage["reasoning_tokens"] == expected_reasoning
    assert stage["missing_fields"].get("reasoning_tokens", 0) == int(expected_reasoning is None)
    assert stage["input_tokens"] == 20
    assert stage["output_tokens"] == 120
    assert stage["total_tokens"] == (None if protocol == "anthropic_messages" else 140)
    raw_row = json.loads((tmp_path / "meta/model_calls.jsonl").read_text(encoding="utf-8"))
    assert raw_row["usage"] == usage
