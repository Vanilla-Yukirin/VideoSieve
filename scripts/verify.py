"""Run VideoSieve quality gates without treating skipped work as success."""

from __future__ import annotations

import argparse
import json
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
        if payload.get("schema_version") != "1.0":
            raise ValueError("schema_version must be '1.0'")
        revision = str(payload.get("revision", "")).strip()
        if not revision:
            raise ValueError("revision is required")
        head = _run(["git", "rev-parse", "HEAD"])
        if head.returncode != 0 or revision != head.stdout.strip():
            raise ValueError("evidence revision does not match the current HEAD")

        source = payload.get("input")
        if not isinstance(source, dict) or float(source.get("duration_seconds", 0)) <= 0:
            raise ValueError("input.duration_seconds must be positive")
        duration = float(source["duration_seconds"])
        if not str(source.get("sha256", "")).strip():
            raise ValueError("input.sha256 is required")

        for section_name in ("asr", "frame_summary", "summary"):
            section = payload.get(section_name)
            if not isinstance(section, dict):
                raise ValueError(f"{section_name} evidence is required")
            provider = str(section.get("provider", "")).strip().lower()
            if not provider or "mock" in provider or "offline" in provider:
                raise ValueError(f"{section_name}.provider must identify a real provider")
            artifact = Path(str(section.get("artifact", ""))).expanduser()
            _read_nonempty(artifact, section_name)

        asr = payload["asr"]
        summary = payload["summary"]
        if float(asr.get("source_coverage_end_seconds", 0)) < duration * 0.8:
            raise ValueError("ASR evidence does not cover the final 20% of the input")
        if float(summary.get("source_coverage_end_seconds", 0)) < duration * 0.8:
            raise ValueError("summary evidence does not cover the final 20% of the input")

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
    gates: list[Callable[[], GateResult]] = [
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
