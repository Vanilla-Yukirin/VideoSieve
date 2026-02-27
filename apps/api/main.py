"""FastAPI runtime entrypoint for API and websocket gateways."""

from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from infra import FileSystemWorkspaceStore, RedisEventBus, SQLiteJobRepository

from .rest import (
    control_job,
    create_job,
    create_me_cookie,
    create_project,
    delete_me_cookie,
    get_auth_bootstrap_status,
    get_auth_me,
    get_guest_cooldown,
    get_job,
    get_job_snapshot,
    get_project,
    get_public_access_flags,
    get_system_settings,
    list_job_artifacts,
    list_me_cookies,
    list_project_jobs,
    patch_me_cookie,
    patch_system_settings,
    post_auth_bootstrap,
    post_auth_login,
    post_auth_logout,
    probe_ingest_formats,
    validate_me_cookie,
)
from .service import ApiConfigError, ApiControlPlane, ApiError
from .ws_gateway import JobWebSocketGateway


@dataclass(slots=True)
class _Runtime:
    repository: SQLiteJobRepository
    workspace: FileSystemWorkspaceStore
    event_bus: RedisEventBus
    control_plane: ApiControlPlane
    ws_gateway: JobWebSocketGateway


class _SocketQueueAdapter:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def send_json(self, payload: dict[str, Any]) -> None:
        self.queue.put_nowait(payload)


ALLOWED_ARTIFACT_PREFIXES: tuple[str, ...] = (
    "meta/",
    "media/",
    "hotwords/",
    "asr/",
    "frames/",
    "frame_summary/",
    "fusion/",
    "outputs/",
    "logs/",
)


def _read_bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _validation_details(exc: ValidationError | RequestValidationError) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for item in exc.errors():
        cleaned = dict(item)
        ctx = cleaned.get("ctx")
        if isinstance(ctx, dict):
            cleaned["ctx"] = {
                key: (
                    value
                    if isinstance(value, (str, int, float, bool, list, dict, type(None)))
                    else str(value)
                )
                for key, value in ctx.items()
            }
        details.append(cleaned)
    return details


def _build_runtime(*, data_dir_override: Path | None, stub_mode_override: bool | None) -> _Runtime:
    data_dir = data_dir_override or Path(os.getenv("VIDEOSIEVE_API_DATA_DIR", "runtime/api"))
    data_dir.mkdir(parents=True, exist_ok=True)

    repository = SQLiteJobRepository(data_dir / "infra.db")
    repository.ensure_schema()
    workspace = FileSystemWorkspaceStore(data_dir / "workspaces")
    event_bus = RedisEventBus(
        stub_mode=(
            stub_mode_override
            if stub_mode_override is not None
            else _read_bool_env("VIDEOSIEVE_EVENTBUS_STUB_MODE", default=True)
        )
    )
    control_plane = ApiControlPlane(
        repository=repository,
        workspace=workspace,
        event_bus=event_bus,
    )
    ws_gateway = JobWebSocketGateway(control_plane=control_plane, event_bus=event_bus)
    return _Runtime(
        repository=repository,
        workspace=workspace,
        event_bus=event_bus,
        control_plane=control_plane,
        ws_gateway=ws_gateway,
    )


def create_app(*, data_dir: Path | None = None, event_bus_stub_mode: bool | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = _build_runtime(
            data_dir_override=data_dir,
            stub_mode_override=event_bus_stub_mode,
        )
        app.state.runtime = runtime
        try:
            yield
        finally:
            runtime.event_bus.close()
            runtime.repository.close()

    app = FastAPI(title="VideoSieve API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(KeyError)
    async def _handle_key_error(_request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "code": "not_found",
                "message": str(exc).strip("'"),
                "retryable": False,
            },
        )

    @app.exception_handler(ValidationError)
    async def _handle_pydantic_validation_error(
        _request: Request, exc: ValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "request validation failed",
                "retryable": False,
                "details": _validation_details(exc),
            },
        )

    @app.exception_handler(ValueError)
    async def _handle_value_error(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": str(exc),
                "retryable": False,
            },
        )

    @app.exception_handler(ApiConfigError)
    async def _handle_api_config_error(_request: Request, exc: ApiConfigError) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "code": "config_error",
                "message": str(exc),
                "retryable": False,
            },
        )

    @app.exception_handler(ApiError)
    async def _handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        content: dict[str, object] = {
            "code": exc.code,
            "message": exc.message,
            "retryable": False,
        }
        content.update(exc.details)
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(RequestValidationError)
    async def _handle_fastapi_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "request validation failed",
                "retryable": False,
                "details": _validation_details(exc),
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "internal server error",
                "retryable": False,
            },
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    def _control_plane(request: Request) -> ApiControlPlane:
        runtime: _Runtime = request.app.state.runtime
        return runtime.control_plane

    def _token(request: Request) -> str | None:
        auth = request.headers.get("Authorization")
        if isinstance(auth, str) and auth.startswith("Bearer "):
            return auth[len("Bearer ") :].strip() or None
        fallback = request.headers.get("X-Session-Token")
        return fallback if isinstance(fallback, str) else None

    @app.get("/public/access-flags")
    async def get_public_flags(request: Request) -> dict[str, bool]:
        return get_public_access_flags(_control_plane(request))

    @app.get("/auth/bootstrap-status")
    async def get_bootstrap_status(request: Request) -> dict[str, bool]:
        return get_auth_bootstrap_status(_control_plane(request))

    @app.post("/auth/bootstrap")
    async def post_bootstrap(payload: dict[str, Any], request: Request) -> dict[str, str]:
        return post_auth_bootstrap(_control_plane(request), payload)

    @app.post("/auth/login")
    async def post_login(payload: dict[str, Any], request: Request) -> dict[str, str]:
        return post_auth_login(_control_plane(request), payload)

    @app.post("/auth/logout")
    async def post_logout(request: Request) -> dict[str, bool]:
        return post_auth_logout(_control_plane(request), _token(request))

    @app.get("/auth/me")
    async def get_me(request: Request) -> dict[str, str]:
        return get_auth_me(_control_plane(request), _token(request))

    @app.get("/settings/system")
    async def get_settings(request: Request) -> dict[str, bool]:
        return get_system_settings(_control_plane(request), _token(request))

    @app.patch("/settings/system")
    async def patch_settings(request: Request, payload: dict[str, Any]) -> dict[str, bool]:
        return patch_system_settings(_control_plane(request), _token(request), payload)

    @app.get("/guest/cooldown")
    async def get_guest_cooldown_status(request: Request) -> dict[str, object]:
        return get_guest_cooldown(_control_plane(request))

    @app.post("/projects")
    async def post_projects(payload: dict[str, Any], request: Request) -> dict[str, str]:
        return create_project(_control_plane(request), payload)

    @app.get("/projects/{project_id}")
    async def get_projects(project_id: str, request: Request) -> dict[str, str | None]:
        return get_project(_control_plane(request), project_id)

    @app.post("/jobs")
    async def post_jobs(payload: dict[str, Any], request: Request) -> dict[str, str]:
        token = _token(request)
        actor = "guest"
        if token is not None:
            _ = _control_plane(request).get_me(token)
            actor = "user"
        return create_job(_control_plane(request), payload, actor=actor)

    @app.get("/jobs/{job_id}")
    async def get_jobs(job_id: str, request: Request) -> dict[str, str | None]:
        return get_job(_control_plane(request), job_id)

    @app.get("/projects/{project_id}/jobs")
    async def get_project_jobs(request: Request, project_id: str) -> list[dict[str, str | None]]:
        return list_project_jobs(_control_plane(request), project_id)

    @app.get("/jobs/{job_id}/snapshot")
    async def get_jobs_snapshot(request: Request, job_id: str) -> dict[str, object]:
        return get_job_snapshot(_control_plane(request), job_id)

    @app.get("/jobs/{job_id}/artifacts")
    async def get_jobs_artifacts(request: Request, job_id: str) -> list[dict[str, object]]:
        return list_job_artifacts(_control_plane(request), job_id)

    @app.get("/jobs/{job_id}/artifacts/download/{artifact_path:path}")
    async def get_jobs_artifact_download(
        request: Request,
        job_id: str,
        artifact_path: str,
    ) -> FileResponse:
        runtime: _Runtime = request.app.state.runtime
        control_plane = _control_plane(request)
        job = get_job(control_plane, job_id)
        project_id = job.get("project_id")
        if not isinstance(project_id, str):
            raise ValueError(f"job has invalid project_id: {job_id}")

        safe_parts = [part for part in artifact_path.split("/") if part]
        candidate = runtime.workspace.path(project_id, *safe_parts)
        project_root = runtime.workspace.project_root(project_id).resolve()
        relative_path = candidate.relative_to(project_root).as_posix()
        if not any(relative_path.startswith(prefix) for prefix in ALLOWED_ARTIFACT_PREFIXES):
            raise KeyError(f"artifact path is not downloadable: {artifact_path}")
        allowed_paths = {
            str(item.get("path", ""))
            for item in list_job_artifacts(control_plane, job_id)
            if isinstance(item, dict)
        }
        if relative_path not in allowed_paths:
            raise KeyError(f"artifact not available for job: {job_id} path={artifact_path}")

        if not candidate.exists() or not candidate.is_file():
            raise KeyError(f"artifact not found for job: {job_id} path={artifact_path}")

        return FileResponse(path=candidate, filename=candidate.name)

    @app.get("/jobs/{job_id}/source-video")
    async def get_jobs_source_video(request: Request, job_id: str) -> FileResponse:
        runtime: _Runtime = request.app.state.runtime
        job = get_job(_control_plane(request), job_id)
        project_id = job.get("project_id")
        if not isinstance(project_id, str):
            raise ValueError(f"job has invalid project_id: {job_id}")

        source_path = runtime.workspace.source_video_file(project_id)
        if not source_path.exists():
            raise KeyError(f"source video not found for job: {job_id}")

        return FileResponse(path=source_path, media_type="video/mp4", filename="source.mp4")

    @app.post("/jobs/{job_id}/control/{command}")
    async def post_job_control(
        request: Request, job_id: str, command: str
    ) -> dict[str, str | bool]:
        return control_job(_control_plane(request), job_id=job_id, command=command)

    @app.post("/ingest/probe")
    async def post_ingest_probe(payload: dict[str, Any], request: Request) -> dict[str, object]:
        return probe_ingest_formats(_control_plane(request), payload)

    @app.post("/me/cookies")
    async def post_me_cookies(payload: dict[str, Any], request: Request) -> dict[str, object]:
        return create_me_cookie(_control_plane(request), payload)

    @app.get("/me/cookies")
    async def get_me_cookies(request: Request) -> list[dict[str, object]]:
        return list_me_cookies(_control_plane(request))

    @app.patch("/me/cookies/{cookie_id}")
    async def patch_me_cookies(
        cookie_id: str, payload: dict[str, Any], request: Request
    ) -> dict[str, object]:
        return patch_me_cookie(_control_plane(request), cookie_id, payload)

    @app.delete("/me/cookies/{cookie_id}")
    async def delete_me_cookies(cookie_id: str, request: Request) -> dict[str, bool]:
        return delete_me_cookie(_control_plane(request), cookie_id)

    @app.post("/me/cookies/{cookie_id}/validate")
    async def post_me_cookie_validate(
        cookie_id: str, payload: dict[str, Any], request: Request
    ) -> dict[str, object]:
        return validate_me_cookie(_control_plane(request), cookie_id, payload)

    @app.websocket("/ws/jobs/{job_id}")
    async def ws_jobs(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        runtime: _Runtime = websocket.app.state.runtime
        socket_adapter = _SocketQueueAdapter()

        async def _sender() -> None:
            while True:
                payload = await socket_adapter.queue.get()
                await websocket.send_json(payload)

        sender_task = asyncio.create_task(_sender())

        try:
            runtime.ws_gateway.connect(job_id=job_id, socket=socket_adapter)
        except KeyError:
            sender_task.cancel()
            await websocket.close(code=4404, reason="job not found")
            return

        try:
            while True:
                message = await websocket.receive_json()
                ack = runtime.ws_gateway.handle_command(job_id=job_id, payload=message)
                await websocket.send_json({"event_type": "control_ack", "payload": ack})
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            runtime.ws_gateway.disconnect(job_id=job_id, socket=socket_adapter)
            sender_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender_task

    return app


app = create_app()
