"""REST route declarations for job control plane."""

from __future__ import annotations

from typing import Any

from contracts import ControlCommandType

from .models import JobCreateRequest, ProjectCreateRequest
from .service import ApiControlPlane

REST_ROUTES: tuple[str, ...] = (
    "POST /projects",
    "GET /projects/{project_id}",
    "POST /jobs",
    "GET /jobs/{job_id}",
    "GET /projects/{project_id}/jobs",
    "GET /jobs/{job_id}/snapshot",
    "GET /jobs/{job_id}/artifacts",
    "POST /jobs/{job_id}/control/{command}",
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


def create_job(control_plane: ApiControlPlane, payload: dict[str, Any]) -> dict[str, str]:
    """POST /jobs"""

    job_id = control_plane.create_job(JobCreateRequest.model_validate(payload))
    return {"job_id": job_id}


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
