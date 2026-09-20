"""Strict readers and fingerprints for summary evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class EvidenceValidationError(ValueError):
    """Evidence does not match the persisted timeline/frame contracts."""

    retryable = False

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class EvidenceSection:
    """One validated source section supplied to the summary provider."""

    source_id: str
    source_type: str
    text: str
    start: float | None = None
    end: float | None = None

    def render(self) -> str:
        """Render the exact text sent into hierarchical summarization."""

        if self.source_type == "transcript":
            return (
                f"[TRANSCRIPT {self.source_id} {self.start:.3f}-{self.end:.3f}]\n"
                f"{self.text}"
            )
        return f"[FRAME {self.source_id}]\n{self.text}"


@dataclass(frozen=True)
class TimelineEvidence:
    """Validated timeline payload and its transcript sections."""

    chunks: list[dict[str, object]]
    sections: list[EvidenceSection]


def read_timeline_evidence(
    path: Path,
    *,
    project_id: str,
    job_id: str,
    error_code: str,
) -> TimelineEvidence:
    """Read a timeline without silently dropping malformed chunks."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceValidationError(error_code, f"invalid timeline file: {exc}") from exc
    if not isinstance(payload, dict):
        raise EvidenceValidationError(error_code, "timeline payload must be an object")
    _require_nonempty_string(payload, "schema_version", "timeline", error_code)
    stored_project_id = _require_nonempty_string(payload, "project_id", "timeline", error_code)
    stored_job_id = _require_nonempty_string(payload, "job_id", "timeline", error_code)
    if stored_project_id != project_id or stored_job_id != job_id:
        raise EvidenceValidationError(
            error_code,
            "timeline project_id/job_id does not match the requested job",
        )

    chunks = payload.get("chunks")
    if not isinstance(chunks, list):
        raise EvidenceValidationError(error_code, "timeline chunks must be a list")

    validated_chunks: list[dict[str, object]] = []
    sections: list[EvidenceSection] = []
    source_ids: set[str] = set()
    for index, chunk in enumerate(chunks, start=1):
        context = f"timeline chunk {index}"
        if not isinstance(chunk, dict):
            raise EvidenceValidationError(error_code, f"{context} must be an object")
        chunk_id = _require_nonempty_string(chunk, "chunk_id", context, error_code)
        source_id = f"transcript:{chunk_id}"
        if source_id in source_ids:
            raise EvidenceValidationError(error_code, f"duplicate source id: {source_id}")
        source_ids.add(source_id)
        start = _require_number(chunk, "start", context, error_code)
        end = _require_number(chunk, "end", context, error_code)
        if end < start:
            raise EvidenceValidationError(error_code, f"{context}.end must be >= start")
        text = _require_nonempty_string(chunk, "text", context, error_code)
        for refs_key in ("transcript_refs", "frame_refs", "frame_summary_refs"):
            if refs_key in chunk:
                _require_string_list(chunk[refs_key], f"{context}.{refs_key}", error_code)
        validated_chunks.append(dict(chunk))
        sections.append(
            EvidenceSection(
                source_id=source_id,
                source_type="transcript",
                text=text,
                start=start,
                end=end,
            )
        )
    return TimelineEvidence(chunks=validated_chunks, sections=sections)


def read_frame_summary_evidence(path: Path, *, error_code: str) -> list[EvidenceSection]:
    """Read frame summaries without accepting malformed or duplicate rows."""

    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise EvidenceValidationError(error_code, f"invalid frame summary file: {exc}") from exc

    sections: list[EvidenceSection] = []
    source_ids: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        context = f"frame summary line {line_number}"
        try:
            payload: Any = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvidenceValidationError(error_code, f"{context} is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise EvidenceValidationError(error_code, f"{context} must be an object")
        _require_nonempty_string(payload, "schema_version", context, error_code)
        frame_id = _require_nonempty_string(payload, "frame_id", context, error_code)
        _require_nonempty_string(payload, "lang", context, error_code)
        _require_nonempty_string(payload, "provider", context, error_code)
        text = _require_nonempty_string(payload, "description_text", context, error_code)
        source_id = f"frame:{frame_id}"
        if source_id in source_ids:
            raise EvidenceValidationError(error_code, f"duplicate source id: {source_id}")
        source_ids.add(source_id)
        sections.append(
            EvidenceSection(
                source_id=source_id,
                source_type="frame",
                text=text,
            )
        )
    return sections


def evidence_sha256(sections: list[EvidenceSection]) -> str:
    """Hash the exact ordered evidence strings supplied to the provider."""

    rendered = [section.render() for section in sections]
    return sha256_json(rendered)


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: object) -> str:
    """Hash a stable JSON representation."""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_text(value: str) -> str:
    """Hash one UTF-8 string."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_nonempty_string(
    payload: dict[str, Any],
    key: str,
    context: str,
    error_code: str,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(error_code, f"{context}.{key} must be a non-empty string")
    return value.strip()


def _require_number(
    payload: dict[str, Any],
    key: str,
    context: str,
    error_code: str,
) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EvidenceValidationError(error_code, f"{context}.{key} must be a number")
    return float(value)


def _require_string_list(value: object, context: str, error_code: str) -> None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise EvidenceValidationError(
            error_code,
            f"{context} must be a list of non-empty strings",
        )
