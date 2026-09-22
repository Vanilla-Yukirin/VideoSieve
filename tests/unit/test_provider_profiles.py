from __future__ import annotations

import json
from pathlib import Path

import pytest
from apps.api.models import (
    JobCreateRequest,
    ProjectCreateRequest,
    ProviderProfileCreateRequest,
    ProviderProfileDraftTestRequest,
    ProviderProfilePatchRequest,
    SystemSettingsPatchRequest,
)
from apps.api.service import ApiControlPlane, ApiError
from pydantic import SecretStr

from infra import FileSystemWorkspaceStore, InMemoryEventBus, SQLiteJobRepository


@pytest.fixture(autouse=True)
def _app_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "provider-profile-test-secret")


def _control_plane(
    tmp_path: Path,
) -> tuple[ApiControlPlane, SQLiteJobRepository, FileSystemWorkspaceStore]:
    repository = SQLiteJobRepository(tmp_path / "infra.db")
    repository.ensure_schema()
    workspace = FileSystemWorkspaceStore(tmp_path / "workspaces")
    return (
        ApiControlPlane(
            repository=repository,
            workspace=workspace,
            event_bus=InMemoryEventBus(),
        ),
        repository,
        workspace,
    )


def test_profiles_are_write_only_versioned_and_selected_per_job(tmp_path: Path) -> None:
    control, repository, workspace = _control_plane(tmp_path)
    asr = control.create_provider_profile(
        ProviderProfileCreateRequest(
            display_name="CapsWriter home",
            capability="asr",
            protocol="capswriter_ws",
            api_root="ws://127.0.0.1:6016",
            auth_mode="optional_bearer",
        )
    )
    vlm = control.create_provider_profile(
        ProviderProfileCreateRequest(
            display_name="Vision Responses",
            capability="frame_summary",
            protocol="openai_responses",
            api_root="https://api.example/v1",
            model="vision-model",
            credential=SecretStr("top-secret"),
        )
    )
    replacement = control.patch_provider_profile(
        vlm.id,
        ProviderProfilePatchRequest(
            model="vision-model-2", credential=SecretStr("new-secret")
        ),
    )

    assert replacement.revision == 2
    assert replacement.credential_configured is True
    serialized = json.dumps([item.model_dump() for item in control.list_provider_profiles()])
    assert "top-secret" not in serialized
    assert "new-secret" not in serialized

    control.patch_system_settings(
        SystemSettingsPatchRequest(
            vlm_concurrency=2,
            vlm_rpm=9,
            vlm_frame_prompt_zh="custom global frame prompt",
        )
    )

    project_id = control.create_project(ProjectCreateRequest(title="profiles"))
    job_id = control.create_job(
        JobCreateRequest(
            project_id=project_id,
            asr_profile_id=asr.id,
            frame_summary_profile_id=vlm.id,
            summary_enabled=False,
        )
    )
    snapshot = json.loads(
        workspace.config_snapshot_file(project_id, job_id).read_text(encoding="utf-8")
    )
    assert snapshot["schema_version"] == "2.0"
    assert snapshot["asr"]["profile_id"] == asr.id
    assert snapshot["frame_summary"]["profile_id"] == vlm.id
    assert snapshot["frame_summary"]["protocol"] == "openai_responses"
    assert snapshot["frame_summary"]["model"] == "vision-model-2"
    assert snapshot["frame_summary"]["concurrency"] == 2
    assert snapshot["frame_summary"]["rpm"] == 9
    assert snapshot["frame_summary"]["prompt_zh"] == "custom global frame prompt"
    assert "new-secret" not in json.dumps(snapshot)
    kind = snapshot["frame_summary"]["credential_kind"]
    assert repository.get_provider_secret(
        snapshot["frame_summary"]["credential_ref"], expected_kind=kind
    ) is not None


def test_profile_rejects_full_protocol_route_and_unimplemented_asr(tmp_path: Path) -> None:
    control, _, _ = _control_plane(tmp_path)
    with pytest.raises(ApiError) as route_error:
        control.create_provider_profile(
            ProviderProfileCreateRequest(
                display_name="wrong URL",
                capability="overall_summary",
                protocol="openai_chat_completions",
                api_root="https://api.example/v1/chat/completions",
                model="text-model",
            )
        )
    assert route_error.value.code == "provider_api_root_has_route"

    with pytest.raises(ApiError) as planned_error:
        control.create_provider_profile(
            ProviderProfileCreateRequest.model_validate(
                {
                    "display_name": "Alibaba ASR",
                    "capability": "asr",
                    "protocol": "openai_responses",
                    "api_root": "https://dashscope.aliyuncs.com/api/v1",
                }
            )
        )
    assert planned_error.value.code == "provider_protocol_not_implemented"


def test_draft_test_uses_current_values_without_persisting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control, repository, _ = _control_plane(tmp_path)
    observed: list[dict[str, object]] = []

    class FakeCapsWriter:
        def __init__(self, **kwargs: object) -> None:
            observed.append(kwargs)

        def test_connection(self) -> None:
            return None

    monkeypatch.setattr("apps.api.service.CapsWriterWebSocketProvider", FakeCapsWriter)

    result = control.test_provider_profile_draft(
        ProviderProfileDraftTestRequest(
            capability="asr",
            protocol="capswriter_ws",
            api_root="ws://draft.example:6016",
            auth_mode="optional_bearer",
            options={"timeout_seconds": 8},
            credential=SecretStr("temporary-token"),
        )
    )

    assert result.status == "succeeded"
    assert observed == [
        {
            "endpoint": "ws://draft.example:6016",
            "token": "temporary-token",
            "timeout_seconds": 8,
        }
    ]
    assert control.list_provider_profiles() == []
    assert repository.get_active_provider_secret("provider_profile:test-draft") is None


def test_draft_test_can_reuse_saved_credential_without_saving_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control, _, _ = _control_plane(tmp_path)
    saved = control.create_provider_profile(
        ProviderProfileCreateRequest(
            display_name="Saved CapsWriter",
            capability="asr",
            protocol="capswriter_ws",
            api_root="ws://saved.example:6016",
            auth_mode="optional_bearer",
            credential=SecretStr("saved-token"),
        )
    )
    observed: dict[str, object] = {}

    class FakeCapsWriter:
        def __init__(self, **kwargs: object) -> None:
            observed.update(kwargs)

        def test_connection(self) -> None:
            return None

    monkeypatch.setattr("apps.api.service.CapsWriterWebSocketProvider", FakeCapsWriter)

    control.test_provider_profile_draft(
        ProviderProfileDraftTestRequest(
            capability="asr",
            protocol="capswriter_ws",
            api_root="ws://edited.example:6016",
            auth_mode="optional_bearer",
            saved_credential_profile_id=saved.id,
        )
    )

    assert observed["endpoint"] == "ws://edited.example:6016"
    assert observed["token"] == "saved-token"
    profiles = control.list_provider_profiles()
    assert len(profiles) == 1
    assert profiles[0].api_root == "ws://saved.example:6016"
    assert profiles[0].revision == 1
