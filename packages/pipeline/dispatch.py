"""Helpers for API-side pipeline dispatch bootstrap."""

from __future__ import annotations

import json
from typing import Any

from infra import WorkspaceStore

PIPELINE_DISPATCH_FAILED = "PIPELINE_DISPATCH_FAILED"


def load_job_config_snapshot(
    workspace: WorkspaceStore,
    *,
    project_id: str,
) -> dict[str, Any]:
    """Load ``meta/config.snapshot.json`` for one project."""

    snapshot_path = workspace.path(project_id, "meta", "config.snapshot.json")
    if not snapshot_path.exists():
        raise FileNotFoundError(f"config snapshot not found: {snapshot_path}")
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("config snapshot payload must be an object")
    return payload


def extract_ingest_config(config_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Extract ingest config object from one config snapshot payload."""

    ingest = config_snapshot.get("ingest")
    if ingest is None:
        return {}
    if not isinstance(ingest, dict):
        raise ValueError("config snapshot ingest field must be an object")
    return dict(ingest)
