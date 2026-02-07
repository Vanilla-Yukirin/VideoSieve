from __future__ import annotations

import json
from pathlib import Path

from hotwords import run_hotwords, run_hotwords_from_meta
from infra import FileSystemWorkspaceStore


def test_run_hotwords_extracts_rule_based_terms_and_writes_workspace_file(tmp_path: Path) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")

    result = run_hotwords(
        workspace,
        project_id="p_hot_1",
        job_id="j_hot_1",
        title="PyTorch 实战：Transformer 与 Attention",
        description="本期介绍 Transformer, Attention, CUDA 加速 与 线性代数基础。",
        tags=["PyTorch", "深度学习", "Transformer"],
        max_terms=10,
    )

    hotwords_path = workspace.hotwords_file("p_hot_1")
    assert hotwords_path.exists()
    payload = json.loads(hotwords_path.read_text(encoding="utf-8"))

    assert payload["project_id"] == "p_hot_1"
    assert payload["job_id"] == "j_hot_1"

    terms = {item["text"]: item["weight"] for item in payload["items"]}
    assert "transformer" in terms
    assert "pytorch" in terms
    assert "cuda" in terms
    assert terms["transformer"] >= terms["cuda"]

    assert result.hotwords_path == str(hotwords_path)


def test_run_hotwords_from_meta_reads_title_description_and_tags(tmp_path: Path) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    workspace.ensure_project_layout("p_hot_2")

    meta_payload = {
        "schema_version": "1.0",
        "project_id": "p_hot_2",
        "job_id": "j_ingest_2",
        "source_type": "local_file",
        "source_ref": str(tmp_path / "input.mp4"),
        "title": "机器学习导论 Machine Learning",
        "description": "课程介绍：监督学习与神经网络。",
        "tags": ["MachineLearning", "神经网络"],
    }
    workspace.meta_file("p_hot_2").write_text(
        json.dumps(meta_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = run_hotwords_from_meta(
        workspace,
        project_id="p_hot_2",
        job_id="j_hot_2",
        max_terms=8,
    )

    texts = [item.text for item in result.hotwords.items]
    assert "machine" in texts
    assert "learning" in texts


def test_run_hotwords_is_case_insensitive_and_limits_max_terms(tmp_path: Path) -> None:
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    result = run_hotwords(
        workspace,
        project_id="p_hot_3",
        job_id="j_hot_3",
        title="Python python PYTHON deep dive",
        description="the and of are stopwords, data engineering intro",
        tags=["Python", "DataEngineering"],
        max_terms=3,
    )

    texts = [item.text for item in result.hotwords.items]
    assert len(texts) == 3
    assert texts.count("python") == 1
