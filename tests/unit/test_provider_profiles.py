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
from apps.api.service import SETTING_PROVIDER_PROFILES, ApiControlPlane, ApiError
from pydantic import SecretStr

from infra import FileSystemWorkspaceStore, InMemoryEventBus, SQLiteJobRepository
from overall_summary import OpenAICompatibleSummaryProvider, OverallSummaryService


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
    assert snapshot["frame_summary"]["model_options"]["max_output_tokens"] == 32768
    assert snapshot["frame_summary"]["model_options"]["context_window_tokens"] == 131072
    assert snapshot["frame_summary"]["model_options"]["thinking_enabled"] is True
    control.patch_provider_profile(
        vlm.id,
        ProviderProfilePatchRequest(
            options={"max_output_tokens": 16000, "context_window_tokens": 100000, "max_retries": 0}
        ),
    )
    assert json.loads(workspace.config_snapshot_file(project_id, job_id).read_text()) == snapshot
    assert "new-secret" not in json.dumps(snapshot)
    kind = snapshot["frame_summary"]["credential_kind"]
    assert (
        repository.get_provider_secret(
            snapshot["frame_summary"]["credential_ref"], expected_kind=kind
        )
        is not None
    )


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


@pytest.mark.parametrize(
    "options",
    [
        {"max_output_tokens": -1},
        {"context_window_tokens": 32768},
        {"max_retries": 100},
        {"thinking_enabled": "true"},
    ],
)
def test_invalid_model_budget_is_rejected_before_profile_write(
    tmp_path: Path, options: dict
) -> None:
    control, _, _ = _control_plane(tmp_path)
    with pytest.raises(ApiError) as error:
        control.create_provider_profile(
            ProviderProfileCreateRequest(
                display_name="bad budget",
                capability="overall_summary",
                protocol="openai_chat_completions",
                api_root="https://api.example/v1",
                model="test-model",
                options=options,
            )
        )
    assert error.value.code == "provider_options_invalid"
    assert control.list_provider_profiles() == []


@pytest.mark.parametrize("context", [8192, 14095])
def test_summary_budget_is_rejected_before_save_and_draft_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, context: int
) -> None:
    control, _, _ = _control_plane(tmp_path)

    def unexpected_request(*args: object, **kwargs: object) -> None:
        raise AssertionError("invalid summary budget must not reach the provider")

    monkeypatch.setattr("apps.api.service.request_model", unexpected_request)
    common = {
        "capability": "overall_summary",
        "protocol": "openai_chat_completions",
        "api_root": "https://example.invalid/v1",
        "model": "test-model",
        "options": {"context_window_tokens": context, "max_output_tokens": 6000},
    }
    with pytest.raises(ApiError, match="8096") as save_error:
        control.create_provider_profile(
            ProviderProfileCreateRequest.model_validate(common | {"display_name": "small"})
        )
    with pytest.raises(ApiError, match="8096") as test_error:
        control.test_provider_profile_draft(ProviderProfileDraftTestRequest.model_validate(common))
    assert save_error.value.status_code == test_error.value.status_code == 422
    assert control.list_provider_profiles() == []


def test_saved_summary_boundary_can_initialize_the_real_summary_service(tmp_path: Path) -> None:
    control, _, workspace = _control_plane(tmp_path)
    saved = control.create_provider_profile(
        ProviderProfileCreateRequest(
            display_name="boundary summary",
            capability="overall_summary",
            protocol="openai_chat_completions",
            api_root="https://example.invalid/v1",
            model="test-model",
            options={"context_window_tokens": 14096, "max_output_tokens": 6000},
        )
    )
    provider = OpenAICompatibleSummaryProvider(
        base_url=saved.api_root,
        model=saved.model,
        allow_env_fallback=False,
        model_options=saved.options,
    )
    assert provider.input_char_budget == 1000
    OverallSummaryService(workspace, provider)


def test_small_frame_budget_remains_usable_without_the_summary_constraint(tmp_path: Path) -> None:
    control, _, _ = _control_plane(tmp_path)
    saved = control.create_provider_profile(
        ProviderProfileCreateRequest(
            display_name="small frame",
            capability="frame_summary",
            protocol="openai_chat_completions",
            api_root="https://example.invalid/v1",
            model="test-model",
            options={"context_window_tokens": 8192, "max_output_tokens": 6000},
        )
    )
    assert saved.options["context_window_tokens"] == 8192


def test_legacy_non_reasoning_adapter_cannot_enable_reasoning(tmp_path: Path) -> None:
    control, _, _ = _control_plane(tmp_path)
    with pytest.raises(ApiError) as error:
        control.create_provider_profile(
            ProviderProfileCreateRequest(
                display_name="invalid legacy reasoning",
                capability="frame_summary",
                protocol="openai_chat_completions",
                api_root="https://example.invalid/v1",
                model="test-model",
                options={"thinking_adapter": "openai_legacy", "thinking_enabled": True},
            )
        )
    assert error.value.status_code == 422
    assert control.list_provider_profiles() == []


def test_old_invalid_summary_profile_stays_editable_but_cannot_execute(tmp_path: Path) -> None:
    control, repository, _ = _control_plane(tmp_path)
    saved = control.create_provider_profile(
        ProviderProfileCreateRequest(
            display_name="old summary",
            capability="overall_summary",
            protocol="openai_chat_completions",
            api_root="https://example.invalid/v1",
            model="test-model",
            options={"context_window_tokens": 14096, "max_output_tokens": 6000},
        )
    )
    stored = json.loads(repository.get_setting(SETTING_PROVIDER_PROFILES) or "[]")
    stored[0]["options"]["context_window_tokens"] = 14095
    repository.set_setting(SETTING_PROVIDER_PROFILES, json.dumps(stored))
    assert control.list_provider_profiles()[0].options["context_window_tokens"] == 14095
    with pytest.raises(ApiError, match="8096"):
        control.test_provider_profile(saved.id)
    project_id = control.create_project(ProjectCreateRequest(title="old budgets"))
    control.create_job(JobCreateRequest(project_id=project_id, summary_enabled=False))
    with pytest.raises(ApiError, match="8096"):
        control.create_job(JobCreateRequest(project_id=project_id, summary_enabled=True))
    repaired = control.patch_provider_profile(
        saved.id, ProviderProfilePatchRequest(
            options={"context_window_tokens": 14096, "max_output_tokens": 6000}
        )
    )
    assert repaired.options["context_window_tokens"] == 14096
