"""FastAPI runtime entrypoint for API and websocket gateways."""

from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from infra import (
    EventBus,
    FileSystemWorkspaceStore,
    InMemoryEventBus,
    SQLiteEventBus,
    SQLiteJobRepository,
)
from ingest import (
    INGEST_AUTH_REQUIRED,
    INGEST_CANCELLED,
    INGEST_DEPENDENCY_MISSING,
    INGEST_DOWNLOAD_FAILED,
    INGEST_INVALID_SOURCE,
    INGEST_SOURCE_NOT_FOUND,
    IngestError,
)

from .rest import (
    control_job,
    create_cookie,
    create_job,
    create_project,
    create_provider_profile,
    delete_cookie,
    delete_project,
    delete_provider_profile,
    get_job,
    get_job_snapshot,
    get_project,
    get_system_settings,
    list_cookies,
    list_job_artifacts,
    list_project_jobs,
    list_projects,
    list_provider_profiles,
    patch_cookie,
    patch_project,
    patch_provider_profile,
    patch_system_settings,
    probe_ingest_formats,
    test_provider_profile,
    validate_cookie,
)
from .service import ApiConfigError, ApiControlPlane, ApiError
from .ws_gateway import JobWebSocketGateway


@dataclass(slots=True)
class _Runtime:
    repository: SQLiteJobRepository
    workspace: FileSystemWorkspaceStore
    event_bus: EventBus
    control_plane: ApiControlPlane
    ws_gateway: JobWebSocketGateway


class _SocketQueueAdapter:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._loop = asyncio.get_running_loop()

    def send_json(self, payload: dict[str, Any]) -> None:
        self._loop.call_soon_threadsafe(self.queue.put_nowait, payload)


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


def _web_origins() -> list[str]:
    raw = os.getenv("VIDEOSIEVE_WEB_ORIGINS", "")
    if raw.strip():
        return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


def _validation_details(exc: ValidationError | RequestValidationError) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for item in exc.errors():
        cleaned = dict(item)
        ctx = cleaned.get("ctx")
        if isinstance(ctx, dict):
            cleaned["ctx"] = {
                key: (
                    value
                    if isinstance(value, str | int | float | bool | list | dict | type(None))
                    else str(value)
                )
                for key, value in ctx.items()
            }
        details.append(cleaned)
    return details


def _ingest_error_status(code: str) -> int:
    return {
        INGEST_SOURCE_NOT_FOUND: 404,
        INGEST_INVALID_SOURCE: 422,
        INGEST_AUTH_REQUIRED: 403,
        INGEST_CANCELLED: 409,
        INGEST_DOWNLOAD_FAILED: 502,
        INGEST_DEPENDENCY_MISSING: 503,
    }.get(code, 502)


def _build_runtime(
    *, data_dir_override: Path | None, in_memory_event_bus_override: bool | None
) -> _Runtime:
    data_dir = data_dir_override or Path(os.getenv("VIDEOSIEVE_API_DATA_DIR", "runtime/api"))
    data_dir.mkdir(parents=True, exist_ok=True)

    repository = SQLiteJobRepository(data_dir / "infra.db")
    repository.ensure_schema()
    workspace = FileSystemWorkspaceStore(data_dir / "workspaces")
    event_bus: EventBus
    if in_memory_event_bus_override is True:
        event_bus = InMemoryEventBus()
    else:
        event_bus = SQLiteEventBus(data_dir / "infra.db")
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


def create_app(*, data_dir: Path | None = None, event_bus_in_memory: bool | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = _build_runtime(
            data_dir_override=data_dir,
            in_memory_event_bus_override=event_bus_in_memory,
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
        allow_origins=_web_origins(),
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

    @app.exception_handler(IngestError)
    async def _handle_ingest_error(_request: Request, exc: IngestError) -> JSONResponse:
        content: dict[str, object] = {
            "code": exc.code,
            "message": exc.message,
            "retryable": exc.retryable,
        }
        if exc.hint is not None:
            content["hint"] = exc.hint
        content.update(exc.context)
        return JSONResponse(status_code=_ingest_error_status(exc.code), content=content)

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

    @app.get("/settings/system")
    async def get_settings(request: Request) -> dict[str, object]:
        return get_system_settings(_control_plane(request))

    @app.patch("/settings/system")
    async def patch_settings(request: Request, payload: dict[str, Any]) -> dict[str, object]:
        return patch_system_settings(_control_plane(request), payload)

    @app.get("/provider-profiles")
    async def get_provider_profiles(
        request: Request, capability: str | None = None
    ) -> list[dict[str, Any]]:
        return list_provider_profiles(_control_plane(request), capability)

    @app.post("/provider-profiles")
    async def post_provider_profile(
        request: Request, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return create_provider_profile(_control_plane(request), payload)

    @app.patch("/provider-profiles/{profile_id}")
    async def patch_provider_profile_route(
        profile_id: str, request: Request, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return patch_provider_profile(_control_plane(request), profile_id, payload)

    @app.delete("/provider-profiles/{profile_id}")
    async def delete_provider_profile_route(
        profile_id: str, request: Request
    ) -> dict[str, bool]:
        return delete_provider_profile(_control_plane(request), profile_id)

    @app.post("/provider-profiles/{profile_id}/test")
    async def test_provider_profile_route(
        profile_id: str, request: Request
    ) -> dict[str, Any]:
        return test_provider_profile(_control_plane(request), profile_id)

    @app.post("/projects")
    async def post_projects(payload: dict[str, Any], request: Request) -> dict[str, str]:
        return create_project(_control_plane(request), payload)

    @app.get("/projects")
    async def get_project_list(request: Request) -> list[dict[str, str | None]]:
        return list_projects(_control_plane(request))

    @app.get("/projects/{project_id}")
    async def get_projects(project_id: str, request: Request) -> dict[str, str | None]:
        return get_project(_control_plane(request), project_id)

    @app.patch("/projects/{project_id}")
    async def patch_projects(
        project_id: str, request: Request, payload: dict[str, Any]
    ) -> dict[str, str | None]:
        return patch_project(_control_plane(request), project_id, payload)

    @app.delete("/projects/{project_id}")
    async def delete_projects(
        project_id: str,
        request: Request,
        force_cancel_active: bool = False,
    ) -> dict[str, object]:
        return delete_project(
            _control_plane(request),
            project_id,
            force_cancel_active=force_cancel_active,
        )

    @app.post("/jobs")
    async def post_jobs(payload: dict[str, Any], request: Request) -> dict[str, str]:
        return create_job(_control_plane(request), payload)

    @app.post("/projects/{project_id}/jobs/upload")
    async def post_upload_local_video(
        project_id: str,
        request: Request,
        video: Annotated[UploadFile, File()],
        context: Annotated[str, Form()] = "",
        summary_enabled: Annotated[str, Form()] = "false",
        asr_profile_id: Annotated[str, Form()] = "",
        frame_summary_profile_id: Annotated[str, Form()] = "",
        overall_summary_profile_id: Annotated[str, Form()] = "",
    ) -> dict[str, str]:
        control_plane = _control_plane(request)
        video_path = control_plane.stage_local_upload(
            project_id,
            filename=video.filename,
            source=video.file,
        )
        payload = {
            "project_id": project_id,
            "summary_enabled": summary_enabled.lower() == "true",
            "local_video_path": str(video_path),
            "local_video_context": context.strip() if context.strip() else None,
            "asr_profile_id": asr_profile_id.strip() or None,
            "frame_summary_profile_id": frame_summary_profile_id.strip() or None,
            "overall_summary_profile_id": overall_summary_profile_id.strip() or None,
        }
        try:
            return create_job(control_plane, payload)
        except Exception:
            control_plane.discard_local_upload(project_id, video_path)
            raise

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
        candidate = runtime.workspace.job_path(project_id, job_id, *safe_parts)
        job_root = runtime.workspace.job_root(project_id, job_id).resolve()
        relative_path = candidate.relative_to(job_root).as_posix()
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

    @app.get("/jobs/{job_id}/artifacts/keyframes-zip")
    async def get_jobs_keyframes_zip(request: Request, job_id: str) -> FileResponse:
        runtime: _Runtime = request.app.state.runtime
        job = get_job(_control_plane(request), job_id)
        project_id = job.get("project_id")
        if not isinstance(project_id, str):
            raise ValueError(f"job has invalid project_id: {job_id}")

        images_dir = runtime.workspace.job_path(project_id, job_id, "frames", "images")
        if not images_dir.exists() or not images_dir.is_dir():
            raise KeyError(f"keyframe image directory not found for job: {job_id}")
        image_files = [
            path
            for path in images_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}
        ]
        if not image_files:
            raise KeyError(f"keyframe images not found for job: {job_id}")

        zip_path = runtime.workspace.job_path(project_id, job_id, "frames", "images.zip")
        if not zip_path.exists() or not zip_path.is_file():
            raise KeyError(f"keyframe zip not found for job: {job_id}")
        return FileResponse(path=zip_path, media_type="application/zip", filename=zip_path.name)

    @app.get("/jobs/{job_id}/source-video")
    async def get_jobs_source_video(request: Request, job_id: str) -> FileResponse:
        runtime: _Runtime = request.app.state.runtime
        job = get_job(_control_plane(request), job_id)
        project_id = job.get("project_id")
        if not isinstance(project_id, str):
            raise ValueError(f"job has invalid project_id: {job_id}")

        source_path = runtime.workspace.source_video_file(project_id, job_id)
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

    @app.post("/cookies")
    async def post_cookies(payload: dict[str, Any], request: Request) -> dict[str, object]:
        return create_cookie(_control_plane(request), payload)

    @app.get("/cookies")
    async def get_cookies(request: Request) -> list[dict[str, object]]:
        return list_cookies(_control_plane(request))

    @app.patch("/cookies/{cookie_id}")
    async def patch_cookies(
        cookie_id: str, payload: dict[str, Any], request: Request
    ) -> dict[str, object]:
        return patch_cookie(_control_plane(request), cookie_id, payload)

    @app.delete("/cookies/{cookie_id}")
    async def delete_cookies(cookie_id: str, request: Request) -> dict[str, bool]:
        return delete_cookie(_control_plane(request), cookie_id)

    @app.post("/cookies/{cookie_id}/validate")
    async def post_cookie_validate(
        cookie_id: str, payload: dict[str, Any], request: Request
    ) -> dict[str, object]:
        return validate_cookie(_control_plane(request), cookie_id, payload)

    @app.websocket("/ws/jobs/{job_id}")
    async def ws_jobs(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        runtime: _Runtime = websocket.app.state.runtime
        socket_adapter = _SocketQueueAdapter()
        sender_task: asyncio.Task[None] | None = None

        async def _sender() -> None:
            while True:
                payload = await socket_adapter.queue.get()
                await websocket.send_json(payload)

        try:
            raw_after_cursor = websocket.query_params.get("after_cursor")
            try:
                after_cursor = int(raw_after_cursor) if raw_after_cursor is not None else None
            except ValueError as exc:
                raise ValueError("after_cursor must be a non-negative integer") from exc
            if after_cursor is not None and after_cursor < 0:
                raise ValueError("after_cursor must be a non-negative integer")

            runtime.ws_gateway.connect(
                job_id=job_id,
                socket=socket_adapter,
                after_cursor=after_cursor,
            )
            # Replay and snapshot messages are queued during synchronous setup.
            # Start the sender only after the gateway has committed the connection.
            sender_task = asyncio.create_task(_sender())
            while True:
                message = await websocket.receive_json()
                runtime.ws_gateway.handle_command(job_id=job_id, payload=message)
        except KeyError:
            with contextlib.suppress(RuntimeError):
                await websocket.close(code=4404, reason="job not found")
        except (ValidationError, ValueError):
            with contextlib.suppress(RuntimeError):
                await websocket.close(code=4400, reason="invalid websocket request")
        except WebSocketDisconnect:
            pass
        except RuntimeError:
            with contextlib.suppress(RuntimeError):
                await websocket.close(code=1011, reason="websocket runtime failure")
        except Exception:
            with contextlib.suppress(RuntimeError):
                await websocket.close(code=1011, reason="websocket setup failure")
            raise
        finally:
            runtime.ws_gateway.disconnect(job_id=job_id, socket=socket_adapter)
            if sender_task is not None:
                sender_task.cancel()
                with contextlib.suppress(
                    asyncio.CancelledError,
                    WebSocketDisconnect,
                    RuntimeError,
                ):
                    await sender_task

    return app


app = create_app()
