"""Start the complete local VideoSieve stack from one terminal."""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "apps" / "web"
EXAMPLE_APP_SECRET = "change-me-in-local-or-production"
MINIMUM_NODE_VERSION = (20, 9, 0)
WEB_SOURCE_DIRS = ("app", "components", "lib")
WEB_BUILD_INPUTS = (
    "eslint.config.mjs",
    "next-env.d.ts",
    "next.config.js",
    "package-lock.json",
    "package.json",
    "postcss.config.js",
    "tailwind.config.ts",
    "tsconfig.json",
)


class LocalRunError(RuntimeError):
    """Raised when the local stack cannot start safely."""


@dataclass(frozen=True, slots=True)
class ManagedProcess:
    name: str
    process: subprocess.Popen[str]
    output_thread: threading.Thread


def _log(message: str, *, source: str = "launcher") -> None:
    output = f"[{source}] {message}"
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    safe_output = output.encode(encoding, errors="replace").decode(encoding)
    print(safe_output, flush=True)


def load_and_validate_env(env_file: Path, *, api_port: int) -> dict[str, str]:
    """Load deployment settings and reject configurations that cannot start safely."""

    if not env_file.is_file():
        raise LocalRunError(
            f"missing {env_file}; copy .env.example to .env.local and set APP_SECRET_KEY"
        )

    raw = dotenv_values(env_file)
    values = {key: value for key, value in raw.items() if value is not None}
    app_secret = values.get("APP_SECRET_KEY", "").strip()
    if not app_secret:
        raise LocalRunError(f"APP_SECRET_KEY is missing or empty in {env_file}")
    if app_secret == EXAMPLE_APP_SECRET:
        raise LocalRunError(f"APP_SECRET_KEY in {env_file} still uses the example value")

    api_origin = values.get(
        "NEXT_PUBLIC_API_ORIGIN",
        f"http://127.0.0.1:{api_port}",
    ).rstrip("/")
    parsed_origin = urlparse(api_origin)
    try:
        origin_port = parsed_origin.port or (443 if parsed_origin.scheme == "https" else 80)
    except ValueError as exc:
        raise LocalRunError(f"NEXT_PUBLIC_API_ORIGIN is invalid: {api_origin!r}") from exc
    if parsed_origin.scheme != "http" or parsed_origin.hostname not in {"127.0.0.1", "localhost"}:
        raise LocalRunError(
            "NEXT_PUBLIC_API_ORIGIN must use local HTTP for the local launcher "
            f"(received {api_origin!r})"
        )
    if origin_port != api_port:
        raise LocalRunError(
            "NEXT_PUBLIC_API_ORIGIN port does not match --api-port "
            f"({origin_port} != {api_port})"
        )
    return values


def _command_path(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise LocalRunError(f"required command is not available on PATH: {name}")
    return path


def check_runtime_dependencies() -> tuple[str, str]:
    """Return the Node and npm commands after checking all runtime dependencies."""

    missing_modules = [
        name
        for name in ("fastapi", "uvicorn", "dotenv", "websockets")
        if importlib.util.find_spec(name) is None
    ]
    if missing_modules:
        raise LocalRunError(
            "missing Python dependencies: "
            f"{', '.join(missing_modules)}; run `uv sync --locked --extra dev`"
        )
    node = _command_path("node")
    npm = _command_path("npm.cmd" if os.name == "nt" else "npm")
    _command_path("ffmpeg")
    _command_path("ffprobe")
    return node, npm


def validate_node_version(raw_version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", raw_version.strip())
    if match is None:
        raise LocalRunError(f"could not parse Node.js version: {raw_version!r}")
    major, minor, patch = (int(part) for part in match.groups())
    version = (major, minor, patch)
    if version < MINIMUM_NODE_VERSION:
        required = ".".join(str(part) for part in MINIMUM_NODE_VERSION)
        raise LocalRunError(f"Node.js {required} or newer is required; found {raw_version.strip()}")
    return version


def port_is_available(host: str, port: int) -> bool:
    """Return whether a TCP listener can bind the requested address."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def _check_ports(host: str, ports: Iterable[int]) -> None:
    checked: set[int] = set()
    for port in ports:
        if port in checked:
            raise LocalRunError(f"Web and API cannot share port {port}")
        checked.add(port)
        if not port_is_available(host, port):
            raise LocalRunError(
                f"{host}:{port} is already in use; stop the existing service or choose another port"
            )


def _newest_mtime(paths: Iterable[Path]) -> float:
    newest = 0.0
    for path in paths:
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
        elif path.is_dir():
            newest = max(
                newest,
                *(item.stat().st_mtime for item in path.rglob("*") if item.is_file()),
            )
    return newest


def web_dependencies_need_install(web_dir: Path = WEB_DIR) -> bool:
    marker = web_dir / "node_modules" / ".package-lock.json"
    next_entry = web_dir / "node_modules" / "next" / "dist" / "bin" / "next"
    if not marker.is_file() or not next_entry.is_file():
        return True
    install_inputs = (web_dir / "package.json", web_dir / "package-lock.json")
    return _newest_mtime(install_inputs) > marker.stat().st_mtime


def web_build_is_stale(
    *, env_file: Path, web_dir: Path = WEB_DIR, force: bool = False
) -> bool:
    if force:
        return True
    marker = web_dir / ".next" / "BUILD_ID"
    if not marker.is_file():
        return True
    inputs = [web_dir / name for name in WEB_BUILD_INPUTS]
    inputs.extend(web_dir / name for name in WEB_SOURCE_DIRS)
    inputs.append(env_file)
    return _newest_mtime(inputs) > marker.stat().st_mtime


def _run_prepare(label: str, command: Sequence[str], *, env: Mapping[str, str]) -> None:
    _log(f"{label}...")
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if completed.returncode != 0:
        raise LocalRunError(f"{label} failed with exit code {completed.returncode}")


def prepare_web(
    *,
    npm: str,
    env_file: Path,
    child_env: Mapping[str, str],
    force_build: bool,
) -> None:
    if web_dependencies_need_install():
        _run_prepare(
            "installing Web dependencies from package-lock.json",
            [npm, "--prefix", str(WEB_DIR), "ci"],
            env=child_env,
        )
    else:
        _log("Web dependencies are ready")

    if web_build_is_stale(env_file=env_file, force=force_build):
        _run_prepare(
            "building the production Web app",
            [npm, "--prefix", str(WEB_DIR), "run", "build"],
            env=child_env,
        )
    else:
        _log("production Web build is current")


def _forward_output(name: str, process: subprocess.Popen[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        _log(line.rstrip(), source=name)


def _spawn(
    name: str,
    command: Sequence[str],
    *,
    env: Mapping[str, str],
    cwd: Path = ROOT,
) -> ManagedProcess:
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=creation_flags,
        start_new_session=os.name != "nt",
    )
    output_thread = threading.Thread(
        target=_forward_output,
        args=(name, process),
        name=f"videosieve-{name}-output",
        daemon=True,
    )
    output_thread.start()
    _log(f"started PID {process.pid}", source=name)
    return ManagedProcess(name=name, process=process, output_thread=output_thread)


def _exited_process(processes: Sequence[ManagedProcess]) -> ManagedProcess | None:
    return next((item for item in processes if item.process.poll() is not None), None)


def _wait_for_http(
    url: str,
    *,
    label: str,
    processes: Sequence[ManagedProcess],
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        exited = _exited_process(processes)
        if exited is not None:
            raise LocalRunError(
                f"{exited.name} exited during startup with code {exited.process.returncode}"
            )
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status < 500:
                    _log(f"{label} is ready")
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    raise LocalRunError(f"timed out after {timeout:g}s waiting for {label} at {url}")


def _request_stop(item: ManagedProcess) -> None:
    process = item.process
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.kill(-process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        return


def _force_stop(item: ManagedProcess) -> None:
    process = item.process
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.kill(-process.pid, 9)
        except ProcessLookupError:
            return


def stop_processes(processes: Sequence[ManagedProcess], *, grace_seconds: float = 5) -> None:
    if not processes:
        return
    _log("stopping Web, worker, and API...")
    for item in reversed(processes):
        _request_stop(item)
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if all(item.process.poll() is not None for item in processes):
            break
        time.sleep(0.1)
    for item in reversed(processes):
        _force_stop(item)
    for item in processes:
        try:
            item.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        item.output_thread.join(timeout=1)
    _log("all local processes stopped")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run VideoSieve API, worker, and production Web from one terminal"
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env.local"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--web-port", type=int, default=3000)
    parser.add_argument("--startup-timeout", type=float, default=30.0)
    parser.add_argument("--force-build", action="store_true")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="validate config, commands, dependencies, ports, and build freshness without starting",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env_file = args.env_file if args.env_file.is_absolute() else ROOT / args.env_file
    processes: list[ManagedProcess] = []
    try:
        if args.host not in {"127.0.0.1", "localhost"}:
            raise LocalRunError("the local launcher only binds loopback addresses")
        if not (1 <= args.api_port <= 65535 and 1 <= args.web_port <= 65535):
            raise LocalRunError("ports must be between 1 and 65535")
        values = load_and_validate_env(env_file, api_port=args.api_port)
        node, npm = check_runtime_dependencies()
        node_version = subprocess.run(
            [node, "--version"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        validate_node_version(node_version)
        _log(f"preflight passed with Python {sys.version.split()[0]} and Node {node_version}")
        _check_ports(args.host, (args.api_port, args.web_port))

        child_env = os.environ.copy()
        child_env.update(values)
        child_env.update({"PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1", "NO_COLOR": "1"})
        if args.check_only:
            build_state = "needed" if web_build_is_stale(env_file=env_file) else "current"
            install_state = "needed" if web_dependencies_need_install() else "current"
            _log(f"Web dependencies: {install_state}; production build: {build_state}")
            return 0

        prepare_web(
            npm=npm,
            env_file=env_file,
            child_env=child_env,
            force_build=args.force_build,
        )

        processes.append(
            _spawn(
                "api",
                [
                    sys.executable,
                    "-u",
                    "-m",
                    "uvicorn",
                    "apps.api.main:app",
                    "--env-file",
                    str(env_file),
                    "--host",
                    args.host,
                    "--port",
                    str(args.api_port),
                ],
                env=child_env,
            )
        )
        processes.append(
            _spawn(
                "worker",
                [
                    sys.executable,
                    "-u",
                    "-m",
                    "workers.single_host",
                    "--env-file",
                    str(env_file),
                ],
                env=child_env,
            )
        )
        processes.append(
            _spawn(
                "web",
                [
                    node,
                    str(WEB_DIR / "node_modules" / "next" / "dist" / "bin" / "next"),
                    "start",
                    "--hostname",
                    args.host,
                    "--port",
                    str(args.web_port),
                ],
                env=child_env,
                cwd=WEB_DIR,
            )
        )

        _wait_for_http(
            f"http://{args.host}:{args.api_port}/healthz",
            label="API",
            processes=processes,
            timeout=args.startup_timeout,
        )
        _wait_for_http(
            f"http://{args.host}:{args.web_port}/",
            label="Web",
            processes=processes,
            timeout=args.startup_timeout,
        )
        time.sleep(0.5)
        exited = _exited_process(processes)
        if exited is not None:
            raise LocalRunError(
                f"{exited.name} exited during startup with code {exited.process.returncode}"
            )
        _log(f"VideoSieve is ready: http://{args.host}:{args.web_port}")
        _log("the worker does not open a network port; press Ctrl+C once to stop everything")

        while True:
            exited = _exited_process(processes)
            if exited is not None:
                raise LocalRunError(
                    f"{exited.name} exited unexpectedly with code {exited.process.returncode}"
                )
            time.sleep(0.5)
    except KeyboardInterrupt:
        _log("Ctrl+C received")
        return 0
    except LocalRunError as exc:
        _log(f"ERROR: {exc}")
        return 1
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    raise SystemExit(main())
