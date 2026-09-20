"""Run VideoSieve quality gates without treating skipped work as success."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Status = Literal["PASS", "FAIL", "NOT-RUN"]
ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "apps" / "web"
HARNESS_TEMP = ROOT / "workspaces" / ".harness-temp"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_EVIDENCE_TOKENS = {
    "baseline",
    "dummy",
    "fake",
    "mock",
    "offline",
    "placeholder",
    "test",
}


@dataclass(frozen=True)
class GateResult:
    name: str
    status: Status
    detail: str
    required: bool = True


def _run(
    command: list[str],
    *,
    timeout: int = 600,
    cwd: Path = ROOT,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _tail_output(completed: subprocess.CompletedProcess[str], *, lines: int = 50) -> str:
    output = "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if isinstance(part, str) and part.strip()
    )
    if not output:
        return f"command exited with {completed.returncode}"
    return "\n".join(output.splitlines()[-lines:])


def _command_gate(
    name: str,
    command: list[str],
    *,
    tool: str | None = None,
    cwd: Path = ROOT,
    timeout: int = 600,
) -> GateResult:
    if tool is not None and shutil.which(tool) is None:
        return GateResult(name, "NOT-RUN", f"required executable is unavailable: {tool}")
    try:
        completed = _run(command, cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired:
        return GateResult(name, "FAIL", "command timed out")
    except OSError as exc:
        return GateResult(name, "NOT-RUN", f"command could not start: {exc}")
    if completed.returncode == 0:
        return GateResult(name, "PASS", "command completed successfully")
    return GateResult(name, "FAIL", _tail_output(completed))


def _uv_tool_gate(name: str, tool_name: str, args: list[str]) -> GateResult:
    uv_executable = shutil.which("uv")
    if uv_executable is None:
        return GateResult(name, "NOT-RUN", "required executable is unavailable: uv")
    return _command_gate(name, [uv_executable, "run", tool_name, *args])


def _pytest_gate(name: str, paths: list[str]) -> GateResult:
    uv_executable = shutil.which("uv")
    if uv_executable is None:
        return GateResult(name, "NOT-RUN", "required executable is unavailable: uv")
    HARNESS_TEMP.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="videosieve-pytest-", dir=HARNESS_TEMP) as temp_dir:
        report = Path(temp_dir) / "junit.xml"
        cases = Path(temp_dir) / "cases"
        try:
            completed = _run(
                [
                    uv_executable,
                    "run",
                    "pytest",
                    *paths,
                    "-q",
                    "-ra",
                    f"--junitxml={report}",
                    f"--basetemp={cases}",
                    "-p",
                    "no:cacheprovider",
                ]
            )
        except subprocess.TimeoutExpired:
            return GateResult(name, "FAIL", "pytest timed out")
        except OSError as exc:
            return GateResult(name, "NOT-RUN", f"pytest could not start: {exc}")
        if completed.returncode != 0:
            return GateResult(name, "FAIL", _tail_output(completed))
        if not report.exists():
            return GateResult(name, "FAIL", "pytest passed without producing its JUnit report")
        root = ET.parse(report).getroot()
        skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in root.iter("testsuite"))
        tests = sum(int(suite.attrib.get("tests", "0")) for suite in root.iter("testsuite"))
        if tests == 0:
            return GateResult(name, "FAIL", "pytest collected no tests")
        if skipped:
            return GateResult(name, "FAIL", f"{skipped} of {tests} tests were skipped")
        return GateResult(name, "PASS", f"{tests} tests passed; 0 skipped")


def _node_script_gate(
    name: str,
    relative_script: str,
    args: list[str],
    *,
    timeout: int = 600,
) -> GateResult:
    node_executable = shutil.which("node")
    if node_executable is None:
        return GateResult(name, "NOT-RUN", "required executable is unavailable: node")
    script = WEB_ROOT / relative_script
    if not script.is_file():
        return GateResult(name, "NOT-RUN", f"required frontend tool is unavailable: {script}")
    return _command_gate(
        name,
        [node_executable, str(script), *args],
        cwd=WEB_ROOT,
        timeout=timeout,
    )


def _frontend_unit_gate() -> GateResult:
    node_executable = shutil.which("node")
    jest_script = WEB_ROOT / "node_modules" / "jest" / "bin" / "jest.js"
    if node_executable is None:
        return GateResult("frontend-unit", "NOT-RUN", "required executable is unavailable: node")
    if not jest_script.is_file():
        return GateResult(
            "frontend-unit",
            "NOT-RUN",
            f"required frontend tool is unavailable: {jest_script}",
        )
    HARNESS_TEMP.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="videosieve-jest-", dir=HARNESS_TEMP) as temp_dir:
        report = Path(temp_dir) / "jest.json"
        try:
            completed = _run(
                [
                    node_executable,
                    str(jest_script),
                    "--runInBand",
                    "--json",
                    "--outputFile",
                    str(report),
                ],
                cwd=WEB_ROOT,
            )
        except subprocess.TimeoutExpired:
            return GateResult("frontend-unit", "FAIL", "Jest timed out")
        except OSError as exc:
            return GateResult("frontend-unit", "NOT-RUN", f"Jest could not start: {exc}")
        if completed.returncode != 0:
            return GateResult("frontend-unit", "FAIL", _tail_output(completed))
        if not report.exists():
            return GateResult(
                "frontend-unit",
                "FAIL",
                "Jest passed without producing its JSON report",
            )
        payload = json.loads(report.read_text(encoding="utf-8"))
        skipped = int(payload.get("numPendingTests", 0))
        tests = int(payload.get("numTotalTests", 0))
        if tests == 0:
            return GateResult("frontend-unit", "FAIL", "Jest collected no tests")
        if skipped:
            return GateResult("frontend-unit", "FAIL", f"{skipped} of {tests} tests were skipped")
        return GateResult("frontend-unit", "PASS", f"{tests} tests passed; 0 skipped")


def _read_nonempty(path: Path, label: str) -> str:
    if not path.is_file():
        raise ValueError(f"{label} artifact does not exist: {path}")
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"{label} artifact is empty: {path}")
    lowered = content.lower()
    forbidden = ("[offline frame summary]", "baseline_mock", "placeholder")
    if any(marker in lowered for marker in forbidden):
        raise ValueError(f"{label} artifact contains mock/placeholder output: {path}")
    return content


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_sha256(value: object, *, label: str) -> str:
    digest = str(value or "").strip().lower()
    if SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError(f"{label} must be a 64-character hexadecimal SHA-256")
    return digest


def _positive_finite_float(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise ValueError(f"{label} must be a positive finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive finite number") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return number


def _resolve_evidence_path(value: object, *, evidence_path: Path, label: str) -> Path:
    raw_path = str(value or "").strip()
    if not raw_path:
        raise ValueError(f"{label} path is required")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = evidence_path.parent / path
    return path.resolve()


def _verify_file_hash(path: Path, expected: object, *, label: str) -> str:
    if not path.is_file():
        raise ValueError(f"{label} does not exist: {path}")
    expected_digest = _require_sha256(expected, label=f"{label}.sha256")
    actual_digest = _sha256_file(path)
    if actual_digest != expected_digest:
        raise ValueError(f"{label}.sha256 does not match the file: {path}")
    return actual_digest


def _require_real_identifier(value: object, *, label: str) -> str:
    identifier = str(value or "").strip()
    if not identifier:
        raise ValueError(f"{label} is required")
    tokens = {token for token in re.split(r"[^a-z0-9]+", identifier.lower()) if token}
    forbidden = sorted(tokens & FORBIDDEN_EVIDENCE_TOKENS)
    if forbidden:
        raise ValueError(f"{label} contains forbidden test/mock marker: {forbidden[0]}")
    return identifier


def _probe_media_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise ValueError("ffprobe is required to verify input.duration_seconds")
    completed = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=60,
    )
    if completed.returncode != 0:
        raise ValueError(f"ffprobe could not read input media: {_tail_output(completed)}")
    try:
        duration = float(completed.stdout.strip())
    except ValueError as exc:
        raise ValueError("ffprobe returned an invalid input duration") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("ffprobe returned a non-positive or non-finite input duration")
    return duration


def _tracked_worktree_gate() -> GateResult:
    name = "tracked-worktree-clean"
    try:
        completed = _run(["git", "status", "--porcelain", "--untracked-files=no"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return GateResult(name, "NOT-RUN", f"could not inspect the worktree: {exc}")
    if completed.returncode != 0:
        return GateResult(name, "FAIL", _tail_output(completed))
    dirty = completed.stdout.strip()
    if dirty:
        return GateResult(
            name,
            "FAIL",
            "release requires a clean tracked worktree:\n" + dirty,
        )
    return GateResult(name, "PASS", "tracked files match HEAD")


def _real_model_gate(evidence_path: Path | None, *, required: bool) -> GateResult:
    name = "real-model-acceptance"
    if evidence_path is None:
        return GateResult(
            name,
            "NOT-RUN",
            "provide --real-evidence; a release profile cannot pass without it",
            required=required,
        )
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "1.1":
            raise ValueError("schema_version must be '1.1'")
        revision = str(payload.get("revision", "")).strip()
        if not revision:
            raise ValueError("revision is required")
        head = _run(["git", "rev-parse", "HEAD"])
        if head.returncode != 0 or revision != head.stdout.strip():
            raise ValueError("evidence revision does not match the current HEAD")

        run_id = _require_real_identifier(payload.get("run_id"), label="run_id")

        source = payload.get("input")
        if not isinstance(source, dict):
            raise ValueError("input evidence is required")
        declared_duration = _positive_finite_float(
            source.get("duration_seconds"),
            label="input.duration_seconds",
        )
        source_path = _resolve_evidence_path(
            source.get("artifact"),
            evidence_path=evidence_path,
            label="input.artifact",
        )
        _verify_file_hash(source_path, source.get("sha256"), label="input")
        duration = _probe_media_duration(source_path)
        tolerance = max(1.0, duration * 0.01)
        if abs(declared_duration - duration) > tolerance:
            raise ValueError(
                "input.duration_seconds does not match ffprobe "
                f"({declared_duration} declared, {duration} measured)"
            )

        artifact_paths: set[Path] = set()
        for section_name in ("asr", "frame_summary", "summary"):
            section = payload.get(section_name)
            if not isinstance(section, dict):
                raise ValueError(f"{section_name} evidence is required")
            _require_real_identifier(section.get("provider"), label=f"{section_name}.provider")
            _require_real_identifier(section.get("model"), label=f"{section_name}.model")
            section_run_id = str(section.get("run_id") or "").strip()
            request_id = str(section.get("request_id") or "").strip()
            if not section_run_id and not request_id:
                raise ValueError(f"{section_name}.request_id or run_id is required")
            if section_run_id:
                validated_run_id = _require_real_identifier(
                    section_run_id,
                    label=f"{section_name}.run_id",
                )
                if validated_run_id != run_id:
                    raise ValueError(f"{section_name}.run_id must match the top-level run_id")
            if request_id:
                _require_real_identifier(request_id, label=f"{section_name}.request_id")
            artifact = _resolve_evidence_path(
                section.get("artifact"),
                evidence_path=evidence_path,
                label=f"{section_name}.artifact",
            )
            if artifact == source_path or artifact in artifact_paths:
                raise ValueError(f"{section_name}.artifact must identify a distinct output file")
            artifact_paths.add(artifact)
            _verify_file_hash(artifact, section.get("sha256"), label=section_name)
            _read_nonempty(artifact, section_name)

        asr = payload["asr"]
        summary = payload["summary"]
        asr_coverage = _positive_finite_float(
            asr.get("source_coverage_end_seconds"),
            label="asr.source_coverage_end_seconds",
        )
        summary_coverage = _positive_finite_float(
            summary.get("source_coverage_end_seconds"),
            label="summary.source_coverage_end_seconds",
        )
        if asr_coverage < duration * 0.8:
            raise ValueError("ASR evidence does not cover the final 20% of the input")
        if summary_coverage < duration * 0.8:
            raise ValueError("summary evidence does not cover the final 20% of the input")
        if asr_coverage > duration + tolerance:
            raise ValueError("ASR source coverage exceeds the measured input duration")
        if summary_coverage > duration + tolerance:
            raise ValueError("summary source coverage exceeds the measured input duration")

        reviews = payload.get("human_review")
        required_reviews = (
            "transcript_content_and_timestamps",
            "frame_descriptions",
            "final_summary_fidelity",
        )
        if not isinstance(reviews, dict) or any(
            reviews.get(key) is not True for key in required_reviews
        ):
            raise ValueError("all human_review checks must be true")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return GateResult(name, "FAIL", str(exc), required=required)
    return GateResult(name, "PASS", f"evidence accepted for revision {revision}", required=required)


def _gates(profile: str, evidence_path: Path | None) -> list[Callable[[], GateResult]]:
    gates: list[Callable[[], GateResult]] = []
    if profile == "release":
        gates.append(_tracked_worktree_gate)
    gates.extend(
        [
            lambda: _command_gate("diff-hygiene", ["git", "diff", "--check"], tool="git"),
            lambda: _uv_tool_gate(
                "python-lint",
                "ruff",
                [
                    "check",
                    "apps",
                    "packages",
                    "workers",
                    "tests/unit",
                    "tests/contract",
                    "tests/integration",
                    "scripts/verify.py",
                ],
            ),
            lambda: _uv_tool_gate(
                "python-types",
                "mypy",
                ["apps", "packages", "workers", "scripts/verify.py"],
            ),
            lambda: _node_script_gate(
                "frontend-lint",
                "node_modules/eslint/bin/eslint.js",
                [".", "--max-warnings=0"],
            ),
            lambda: _node_script_gate(
                "frontend-types",
                "node_modules/typescript/bin/tsc",
                ["--noEmit"],
            ),
            lambda: _pytest_gate("python-unit-contract", ["tests/unit", "tests/contract"]),
            _frontend_unit_gate,
        ]
    )
    if profile in {"integration", "release"}:
        gates.append(lambda: _pytest_gate("process-integration", ["tests/integration"]))
        gates.append(
            lambda: _node_script_gate(
                "frontend-build",
                "node_modules/next/dist/bin/next",
                ["build"],
                timeout=900,
            )
        )
    gates.append(lambda: _real_model_gate(evidence_path, required=profile == "release"))
    return gates


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("quick", "integration", "release"),
        default="integration",
        help="release additionally requires real-model acceptance evidence",
    )
    parser.add_argument("--real-evidence", type=Path)
    args = parser.parse_args()

    results = [gate() for gate in _gates(args.profile, args.real_evidence)]
    print(f"VideoSieve verification profile: {args.profile}")
    for result in results:
        requirement = "required" if result.required else "informational"
        print(f"[{result.status}] {result.name} ({requirement})")
        if result.status != "PASS":
            for line in result.detail.splitlines():
                print(f"  {line}")

    blockers = [result for result in results if result.required and result.status != "PASS"]
    if blockers:
        print(f"VERIFICATION FAILED: {len(blockers)} required gate(s) did not pass")
        return 1
    print("VERIFICATION PASSED: every required gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
