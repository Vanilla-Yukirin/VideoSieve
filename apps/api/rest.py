"""REST route declarations for job control plane."""

from __future__ import annotations

from typing import Any

from contracts import ControlCommandType

from .models import (
    AuthBootstrapRequest,
    AuthLoginRequest,
    CookieCreateRequest,
    CookiePatchRequest,
    CookieValidateRequest,
    IngestProbeRequest,
    JobCreateRequest,
    ProjectCreateRequest,
    SystemSettingsPatchRequest,
)
from .service import ApiControlPlane

REST_ROUTES: tuple[str, ...] = (
    "GET /auth/bootstrap-status",
    "POST /auth/bootstrap",
    "POST /auth/login",
    "POST /auth/logout",
    "GET /auth/me",
    "GET /settings/system",
    "PATCH /settings/system",
    "GET /guest/cooldown",
    "POST /projects",
    "GET /projects/{project_id}",
    "POST /jobs",
    "GET /jobs/{job_id}",
    "GET /projects/{project_id}/jobs",
    "GET /jobs/{job_id}/snapshot",
    "GET /jobs/{job_id}/artifacts",
    "POST /jobs/{job_id}/control/{command}",
    "POST /ingest/probe",
    "POST /me/cookies",
    "GET /me/cookies",
    "PATCH /me/cookies/{cookie_id}",
    "DELETE /me/cookies/{cookie_id}",
    "POST /me/cookies/{cookie_id}/validate",
)


def create_project(control_plane: ApiControlPlane, payload: dict[str, Any]) -> dict[str, str]:
    """POST /projects"""

    project_id = control_plane.create_project(ProjectCreateRequest.model_validate(payload))
    return {"project_id": project_id}


def get_project(control_plane: ApiControlPlane, project_id: str) -> dict[str, str | None]:
    """GET /projects/{project_id}"""

    project = control_plane.get_project(project_id)
    if project is None:
        raise KeyError(f"project not found: {project_id}")
    return project


def create_job(
    control_plane: ApiControlPlane,
    payload: dict[str, Any],
    *,
    actor: str = "guest",
) -> dict[str, str]:
    """POST /jobs"""

    job_id = control_plane.create_job(JobCreateRequest.model_validate(payload), actor=actor)
    return {"job_id": job_id}


def get_auth_bootstrap_status(control_plane: ApiControlPlane) -> dict[str, bool]:
    """GET /auth/bootstrap-status"""

    return control_plane.get_bootstrap_status().model_dump(mode="json")


def post_auth_bootstrap(control_plane: ApiControlPlane, payload: dict[str, Any]) -> dict[str, str]:
    """POST /auth/bootstrap"""

    return control_plane.bootstrap_user(AuthBootstrapRequest.model_validate(payload)).model_dump(
        mode="json"
    )


def post_auth_login(control_plane: ApiControlPlane, payload: dict[str, Any]) -> dict[str, str]:
    """POST /auth/login"""

    return control_plane.login(AuthLoginRequest.model_validate(payload)).model_dump(mode="json")


def post_auth_logout(control_plane: ApiControlPlane, token: str | None) -> dict[str, bool]:
    """POST /auth/logout"""

    control_plane.logout(token)
    return {"ok": True}


def get_auth_me(control_plane: ApiControlPlane, token: str | None) -> dict[str, str]:
    """GET /auth/me"""

    return control_plane.get_me(token).model_dump(mode="json")


def get_system_settings(control_plane: ApiControlPlane, token: str | None) -> dict[str, bool]:
    """GET /settings/system"""

    return control_plane.get_system_settings(token).model_dump(mode="json")


def patch_system_settings(
    control_plane: ApiControlPlane,
    token: str | None,
    payload: dict[str, Any],
) -> dict[str, bool]:
    """PATCH /settings/system"""

    request = SystemSettingsPatchRequest.model_validate(payload)
    return control_plane.patch_system_settings(token, request).model_dump(mode="json")


def get_guest_cooldown(control_plane: ApiControlPlane) -> dict[str, object]:
    """GET /guest/cooldown"""

    return control_plane.get_guest_cooldown().model_dump(mode="json")


def get_job(control_plane: ApiControlPlane, job_id: str) -> dict[str, str | None]:
    """GET /jobs/{job_id}"""

    job = control_plane.get_job(job_id)
    if job is None:
        raise KeyError(f"job not found: {job_id}")
    return job


def list_project_jobs(
    control_plane: ApiControlPlane, project_id: str
) -> list[dict[str, str | None]]:
    """GET /projects/{project_id}/jobs"""

    return control_plane.list_jobs_for_project(project_id)


def get_job_snapshot(control_plane: ApiControlPlane, job_id: str) -> dict[str, object]:
    """GET /jobs/{job_id}/snapshot"""

    return control_plane.get_job_snapshot(job_id).model_dump(mode="json")


def list_job_artifacts(control_plane: ApiControlPlane, job_id: str) -> list[dict[str, object]]:
    """GET /jobs/{job_id}/artifacts"""

    job = control_plane.get_job(job_id)
    if job is None:
        raise KeyError(f"job not found: {job_id}")
    project_id = job.get("project_id")
    if not isinstance(project_id, str):
        raise ValueError(f"job has invalid project_id: {job_id}")
    return [
        artifact.model_dump(mode="json") for artifact in control_plane.list_artifacts(project_id)
    ]


def control_job(
    control_plane: ApiControlPlane,
    *,
    job_id: str,
    command: str,
) -> dict[str, str | bool]:
    """POST /jobs/{job_id}/control/{command}"""

    return control_plane.dispatch_control_command(
        job_id=job_id,
        command=ControlCommandType(command),
    )


def probe_ingest_formats(
    control_plane: ApiControlPlane, payload: dict[str, Any]
) -> dict[str, object]:
    """POST /ingest/probe"""

    result = control_plane.probe_ingest_formats(IngestProbeRequest.model_validate(payload))
    return result.model_dump(mode="json")


def create_me_cookie(control_plane: ApiControlPlane, payload: dict[str, Any]) -> dict[str, object]:
    """POST /me/cookies"""

    created = control_plane.create_cookie(CookieCreateRequest.model_validate(payload))
    return created.model_dump(mode="json")


def list_me_cookies(control_plane: ApiControlPlane) -> list[dict[str, object]]:
    """GET /me/cookies"""

    return [item.model_dump(mode="json") for item in control_plane.list_cookies()]


def patch_me_cookie(
    control_plane: ApiControlPlane, cookie_id: str, payload: dict[str, Any]
) -> dict[str, object]:
    """PATCH /me/cookies/{cookie_id}"""

    updated = control_plane.patch_cookie(cookie_id, CookiePatchRequest.model_validate(payload))
    return updated.model_dump(mode="json")


def delete_me_cookie(control_plane: ApiControlPlane, cookie_id: str) -> dict[str, bool]:
    """DELETE /me/cookies/{cookie_id}"""

    control_plane.delete_cookie(cookie_id)
    return {"deleted": True}


def validate_me_cookie(
    control_plane: ApiControlPlane, cookie_id: str, payload: dict[str, Any]
) -> dict[str, object]:
    """POST /me/cookies/{cookie_id}/validate"""

    result = control_plane.validate_cookie(cookie_id, CookieValidateRequest.model_validate(payload))
    return result.model_dump(mode="json")
