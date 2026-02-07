from __future__ import annotations

from pathlib import Path

import pytest

from infra import FileSystemWorkspaceStore


def test_workspace_store_creates_canonical_layout(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")

    root = store.ensure_project_layout("project-1")

    assert root == tmp_path / "workspaces" / "project-1"
    assert (root / "meta").is_dir()
    assert (root / "media").is_dir()
    assert (root / "frames" / "images").is_dir()
    assert (root / "outputs").is_dir()


def test_workspace_store_builds_expected_paths(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")

    assert (
        store.meta_file("project-2") == tmp_path / "workspaces" / "project-2" / "meta" / "meta.json"
    )
    assert (
        store.source_video_file("project-2")
        == tmp_path / "workspaces" / "project-2" / "media" / "source.mp4"
    )
    assert (
        store.summary_file("project-2")
        == tmp_path / "workspaces" / "project-2" / "outputs" / "summary.json"
    )


def test_workspace_store_rejects_path_escape(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")

    with pytest.raises(ValueError):
        store.path("project-3", "..", "outside.txt")
