"""REST route declarations for job control plane."""

from __future__ import annotations

from typing import Any

from contracts import ControlCommandType

from .models import (
    CookieCreateRequest,
    CookiePatchRequest,
    CookieValidateRequest,
    IngestProbeRequest,
    JobCreateRequest,
    ProjectCreateRequest,
    ProjectPatchRequest,
    ProviderProfileCreateRequest,
    ProviderProfilePatchRequest,
    SystemSettingsPatchRequest,
)
from .service import ApiControlPlane

REST_ROUTES: tuple[str, ...] = (
    "GET /settings/system",
    "PATCH /settings/system",
    "GET /provider-profiles",
    "POST /provider-profiles",
    "PATCH /provider-profiles/{profile_id}",
    "DELETE /provider-profiles/{profile_id}",
    "POST /provider-profiles/{profile_id}/test",
    "POST /projects",
    "GET /projects",
    "GET /projects/{project_id}",
    "PATCH /projects/{project_id}",
    "DELETE /projects/{project_id}",
    "POST /jobs",
    "POST /projects/{project_id}/jobs/upload",
    "GET /jobs/{job_id}",
    "GET /projects/{project_id}/jobs",
    "GET /jobs/{job_id}/snapshot",
    "GET /jobs/{job_id}/artifacts",
    "GET /jobs/{job_id}/artifacts/download/{artifact_path}",
    "GET /jobs/{job_id}/artifacts/keyframes-zip",
    "GET /jobs/{job_id}/source-video",
    "POST /jobs/{job_id}/control/{command}",
    "POST /ingest/probe",
    "POST /cookies",
    "GET /cookies",
    "PATCH /cookies/{cookie_id}",
    "DELETE /cookies/{cookie_id}",
    "POST /cookies/{cookie_id}/validate",
)


def create_project(control_plane: ApiControlPlane, payload: dict[str, Any]) -> dict[str, str]:
    """POST /projects"""

    project_id = control_plane.create_project(ProjectCreateRequest.model_validate(payload))
    return {"project_id": project_id}


def list_projects(control_plane: ApiControlPlane) -> list[dict[str, str | None]]:
    """GET /projects"""

    return control_plane.list_projects()


def get_project(control_plane: ApiControlPlane, project_id: str) -> dict[str, str | None]:
    """GET /projects/{project_id}"""

    project = control_plane.get_project(project_id)
    if project is None:
        raise KeyError(f"project not found: {project_id}")
    return project


def patch_project(
    control_plane: ApiControlPlane, project_id: str, payload: dict[str, Any]
) -> dict[str, str | None]:
    """PATCH /projects/{project_id}"""

    request = ProjectPatchRequest.model_validate(payload)
    return control_plane.patch_project(project_id, request)


def delete_project(
    control_plane: ApiControlPlane,
    project_id: str,
    *,
    force_cancel_active: bool,
) -> dict[str, object]:
    """DELETE /projects/{project_id}"""

    return control_plane.delete_project(
        project_id,
        force_cancel_active=force_cancel_active,
    )


def create_job(
    control_plane: ApiControlPlane,
    payload: dict[str, Any],
) -> dict[str, str]:
    """POST /jobs"""

    job_id = control_plane.create_job(JobCreateRequest.model_validate(payload))
    return {"job_id": job_id}


def get_system_settings(control_plane: ApiControlPlane) -> dict[str, Any]:
    """GET /settings/system"""

    return control_plane.get_system_settings().model_dump(mode="json")


def patch_system_settings(
    control_plane: ApiControlPlane,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """PATCH /settings/system"""

    request = SystemSettingsPatchRequest.model_validate(payload)
    return control_plane.patch_system_settings(request).model_dump(mode="json")


def list_provider_profiles(
    control_plane: ApiControlPlane, capability: str | None = None
) -> list[dict[str, Any]]:
    """GET /provider-profiles"""

    return [
        item.model_dump(mode="json")
        for item in control_plane.list_provider_profiles(capability)
    ]


def create_provider_profile(
    control_plane: ApiControlPlane, payload: dict[str, Any]
) -> dict[str, Any]:
    """POST /provider-profiles"""

    request = ProviderProfileCreateRequest.model_validate(payload)
    return control_plane.create_provider_profile(request).model_dump(mode="json")


def patch_provider_profile(
    control_plane: ApiControlPlane, profile_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """PATCH /provider-profiles/{profile_id}"""

    request = ProviderProfilePatchRequest.model_validate(payload)
    return control_plane.patch_provider_profile(profile_id, request).model_dump(mode="json")


def delete_provider_profile(control_plane: ApiControlPlane, profile_id: str) -> dict[str, bool]:
    """DELETE /provider-profiles/{profile_id}"""

    control_plane.delete_provider_profile(profile_id)
    return {"deleted": True}


def test_provider_profile(
    control_plane: ApiControlPlane, profile_id: str
) -> dict[str, Any]:
    """POST /provider-profiles/{profile_id}/test"""

    return control_plane.test_provider_profile(profile_id).model_dump(mode="json")


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
        artifact.model_dump(mode="json")
        for artifact in control_plane.list_artifacts(project_id, job_id)
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


def create_cookie(control_plane: ApiControlPlane, payload: dict[str, Any]) -> dict[str, object]:
    """POST /cookies"""

    created = control_plane.create_cookie(CookieCreateRequest.model_validate(payload))
    return created.model_dump(mode="json")


def list_cookies(control_plane: ApiControlPlane) -> list[dict[str, object]]:
    """GET /cookies"""

    return [item.model_dump(mode="json") for item in control_plane.list_cookies()]


def patch_cookie(
    control_plane: ApiControlPlane, cookie_id: str, payload: dict[str, Any]
) -> dict[str, object]:
    """PATCH /cookies/{cookie_id}"""

    updated = control_plane.patch_cookie(cookie_id, CookiePatchRequest.model_validate(payload))
    return updated.model_dump(mode="json")


def delete_cookie(control_plane: ApiControlPlane, cookie_id: str) -> dict[str, bool]:
    """DELETE /cookies/{cookie_id}"""

    control_plane.delete_cookie(cookie_id)
    return {"deleted": True}


def validate_cookie(
    control_plane: ApiControlPlane, cookie_id: str, payload: dict[str, Any]
) -> dict[str, object]:
    """POST /cookies/{cookie_id}/validate"""

    result = control_plane.validate_cookie(cookie_id, CookieValidateRequest.model_validate(payload))
    return result.model_dump(mode="json")
