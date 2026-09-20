from __future__ import annotations

import json
from pathlib import Path

import pytest

from infra import FileSystemWorkspaceStore
from overall_summary import (
    OpenAICompatibleSummaryProvider,
    OverallSummaryProviderError,
    OverallSummaryResult,
    OverallSummaryService,
    SummaryProviderProvenance,
)


class _RecordingProvider:
    provider_name = "recording"
    model_name = "test-model"

    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def summarize(
        self,
        source_text: str,
        *,
        language_hint: str | None,
        partial: bool,
    ) -> OverallSummaryResult:
        self.calls.append((source_text, partial))
        if partial:
            facts = [fact for fact in ("fact-a", "fact-b", "fact-c") if fact in source_text]
            text = "kept:" + ",".join(facts)
        else:
            text = "model generated final summary"
        return OverallSummaryResult(text=text, provider=self.provider_name, model=self.model_name)

    def describe_provenance(
        self, *, language_hint: str | None
    ) -> SummaryProviderProvenance:
        return SummaryProviderProvenance(
            provider=self.provider_name,
            model=self.model_name,
            prompt_version="test-prompt-v1",
            prompt_sha256="a" * 64,
            endpoint_sha256="b" * 64,
            parameters={"temperature": 0.0, "language_hint": language_hint},
        )


def _write_timeline(store: FileSystemWorkspaceStore, *, texts: list[str]) -> None:
    path = store.timeline_file("p1", "j1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_id": "p1",
                "job_id": "j1",
                "chunks": [
                    {
                        "chunk_id": f"c{i}",
                        "start": float(i),
                        "end": float(i + 1),
                        "text": text,
                        "transcript_refs": [f"seg-{i}"],
                        "frame_refs": [],
                        "frame_summary_refs": [],
                    }
                    for i, text in enumerate(texts)
                ],
            }
        ),
        encoding="utf-8",
    )
    config_path = store.config_snapshot_file("p1", "j1")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text('{"summary_enabled":true}', encoding="utf-8")


def test_overall_summary_uses_every_transcript_and_frame_section(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    _write_timeline(store, texts=["first transcript fact", "last transcript fact"])
    frame_path = store.frame_summary_file("p1", "j1")
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "frame_id": "f1",
                "lang": "en",
                "provider": "test-frame",
                "description_text": "visual fact",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    provider = _RecordingProvider()

    output = OverallSummaryService(store, provider).run("p1", job_id="j1", language_hint="en")

    assert len(provider.calls) == 1
    evidence, partial = provider.calls[0]
    assert partial is False
    assert "first transcript fact" in evidence
    assert "last transcript fact" in evidence
    assert "visual fact" in evidence
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"] == "model generated final summary"
    assert payload["provider"] == "recording"
    assert payload["model"] == "test-model"
    assert payload["source_sections"] == 3
    provenance = payload["provenance"]
    assert len(provenance["input_sha256"]) == 64
    assert len(provenance["summary_config_sha256"]) == 64
    assert len(provenance["job_config_sha256"]) == 64
    assert provenance["source_ids"] == [
        "transcript:c0",
        "transcript:c1",
        "frame:f1",
    ]
    assert provenance["coverage"] == {
        "validated_source_count": 3,
        "summarized_source_count": 3,
        "transcript_section_count": 2,
        "frame_section_count": 1,
        "coverage_ratio": 1.0,
    }
    assert provenance["prompt_version"] == "test-prompt-v1"
    assert provenance["prompt_sha256"] == "a" * 64
    assert provenance["parameters"]["temperature"] == 0.0
    assert provenance["generated_at"].endswith("+00:00")


def test_overall_summary_partitions_all_evidence_then_synthesizes(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    _write_timeline(store, texts=["fact-a " + "a" * 650, "fact-b " + "b" * 650])
    provider = _RecordingProvider()

    OverallSummaryService(store, provider, max_input_chars=1_000).run("p1", job_id="j1")

    assert [partial for _, partial in provider.calls] == [True, True, False]
    final_input = provider.calls[-1][0]
    assert "kept:fact-a" in final_input
    assert "kept:fact-b" in final_input


def test_overall_summary_splits_one_oversized_evidence_section(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    _write_timeline(store, texts=["fact-a " + "x" * 2_200])
    provider = _RecordingProvider()

    OverallSummaryService(store, provider, max_input_chars=1_000).run("p1", job_id="j1")

    partial_inputs = [text for text, partial in provider.calls if partial]
    assert len(partial_inputs) == 3
    assert sum(text.count("x") for text in partial_inputs) == 2_200
    assert "kept:fact-a" in provider.calls[-1][0]


def test_overall_summary_missing_credentials_is_explicit_failure(tmp_path: Path) -> None:
    provider = OpenAICompatibleSummaryProvider(
        base_url="https://example.invalid/v1/chat/completions",
        model="test-model",
        api_key="",
    )

    with pytest.raises(OverallSummaryProviderError) as exc_info:
        provider.summarize("evidence", language_hint="zh", partial=False)

    assert exc_info.value.code == "OVERALL_SUMMARY_CONFIG_MISSING"
    assert exc_info.value.retryable is False


def test_overall_summary_failure_removes_stale_artifact(tmp_path: Path) -> None:
    class _FailingProvider(_RecordingProvider):
        def summarize(
            self,
            source_text: str,
            *,
            language_hint: str | None,
            partial: bool,
        ) -> OverallSummaryResult:
            raise OverallSummaryProviderError("PROVIDER_FAILED", "failed")

    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    _write_timeline(store, texts=["evidence"])
    output = store.summary_file("p1", "j1")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('{"summary":"previous"}', encoding="utf-8")
    manifest = store.deliverables_manifest_file("p1", "j1")
    manifest.write_text('{"ready":true}', encoding="utf-8")

    with pytest.raises(OverallSummaryProviderError):
        OverallSummaryService(store, _FailingProvider()).run("p1", job_id="j1")

    assert not output.exists()
    assert not manifest.exists()


@pytest.mark.parametrize(
    "chunks",
    [
        ["not-an-object"],
        [{"chunk_id": "c0", "start": 0.0, "end": 1.0, "text": ""}],
        [{"chunk_id": "c0", "start": 2.0, "end": 1.0, "text": "bad range"}],
    ],
)
def test_overall_summary_rejects_malformed_timeline_evidence(
    tmp_path: Path,
    chunks: list[object],
) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    timeline_path = store.timeline_file("p1", "j1")
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    timeline_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_id": "p1",
                "job_id": "j1",
                "chunks": chunks,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        OverallSummaryService(store, _RecordingProvider()).run("p1", job_id="j1")

    assert getattr(exc_info.value, "code", None) == "OVERALL_SUMMARY_INPUT_INVALID"
    assert not store.summary_file("p1", "j1").exists()


def test_overall_summary_rejects_malformed_frame_evidence(tmp_path: Path) -> None:
    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    _write_timeline(store, texts=["valid transcript"])
    frame_path = store.frame_summary_file("p1", "j1")
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_text(json.dumps(["not-an-object"]) + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        OverallSummaryService(store, _RecordingProvider()).run("p1", job_id="j1")

    assert getattr(exc_info.value, "code", None) == "OVERALL_SUMMARY_INPUT_INVALID"


def test_overall_summary_rejects_mismatched_provider_provenance(tmp_path: Path) -> None:
    class _MismatchedProvider(_RecordingProvider):
        def summarize(
            self,
            source_text: str,
            *,
            language_hint: str | None,
            partial: bool,
        ) -> OverallSummaryResult:
            del source_text, language_hint, partial
            return OverallSummaryResult(
                text="summary",
                provider="unexpected-provider",
                model=self.model_name,
            )

    store = FileSystemWorkspaceStore(tmp_path / "workspaces")
    _write_timeline(store, texts=["valid transcript"])

    with pytest.raises(OverallSummaryProviderError) as exc_info:
        OverallSummaryService(store, _MismatchedProvider()).run("p1", job_id="j1")

    assert exc_info.value.code == "OVERALL_SUMMARY_INVALID_RESULT"
    assert not store.summary_file("p1", "j1").exists()
