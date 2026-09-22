"use client";

import { useMemo, useState } from "react";
import { CheckCircle2, Pencil, Plus, Star, Trash2, Wifi } from "lucide-react";

import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Dialog } from "@/components/Dialog";
import { api } from "@/lib/api/client";
import type {
  ProviderAuthMode,
  ProviderCapability,
  ProviderProfile,
  ProviderProfileCreateRequest,
  ProviderProfileDraftTestRequest,
  ProviderProtocol,
} from "@/lib/api/types";
import { useI18n } from "@/lib/i18n/I18nProvider";
import {
  PROVIDER_TEMPLATES,
  profilesForCapability,
  ProviderTemplateId,
  templateForProfile,
} from "@/lib/settings/providerSetup";

interface ProviderProfilesManagerProps {
  profiles: ProviderProfile[];
  onProfilesChange: () => Promise<void> | void;
  capabilities?: ProviderCapability[];
}

interface EditorState {
  profileId: string | null;
  capability: ProviderCapability;
  template: ProviderTemplateId;
  displayName: string;
  protocol: ProviderProtocol;
  apiRoot: string;
  model: string;
  authMode: ProviderAuthMode;
  options: Record<string, unknown>;
  credential: string;
  credentialConfigured: boolean;
  clearCredential: boolean;
  isDefault: boolean;
  language: string;
  context: string;
  timeoutSeconds: number;
}

const CAPABILITIES: ProviderCapability[] = ["asr", "frame_summary", "overall_summary"];

function newEditor(capability: ProviderCapability, isDefault: boolean): EditorState {
  const templateId: ProviderTemplateId = capability === "asr" ? "capswriter" : "openai_chat";
  const template = PROVIDER_TEMPLATES[templateId];
  return {
    profileId: null,
    capability,
    template: templateId,
    displayName: capability === "asr" ? "CapsWriter" : "",
    protocol: template.protocol,
    apiRoot: template.apiRoot,
    model: "",
    authMode: template.authMode,
    options: {},
    credential: "",
    credentialConfigured: false,
    clearCredential: false,
    isDefault,
    language: "auto",
    context: "",
    timeoutSeconds: 900,
  };
}

function editProfile(profile: ProviderProfile): EditorState {
  const options = profile.options;
  return {
    profileId: profile.id,
    capability: profile.capability,
    template: templateForProfile(profile),
    displayName: profile.display_name,
    protocol: profile.protocol,
    apiRoot: profile.api_root,
    model: profile.model,
    authMode: profile.auth_mode,
    options: profile.options,
    credential: "",
    credentialConfigured: profile.credential_configured,
    clearCredential: false,
    isDefault: profile.is_default,
    language: typeof options.language === "string" ? options.language : "auto",
    context: typeof options.context === "string" ? options.context : "",
    timeoutSeconds:
      typeof options.timeout_seconds === "number" ? options.timeout_seconds : 900,
  };
}

function capabilityTitle(
  capability: ProviderCapability,
  t: ReturnType<typeof useI18n>["t"],
): string {
  if (capability === "asr") return t("providers.capabilityAsr");
  if (capability === "frame_summary") return t("providers.capabilityFrame");
  return t("providers.capabilityOverall");
}

function protocolLabel(protocol: ProviderProtocol): string {
  return {
    capswriter_ws: "CapsWriter WebSocket",
    openai_chat_completions: "OpenAI Chat Completions",
    openai_responses: "OpenAI Responses",
    anthropic_messages: "Anthropic Messages",
  }[protocol];
}

function editorDraftTestPayload(editor: EditorState): ProviderProfileDraftTestRequest {
  return {
    capability: editor.capability,
    protocol: editor.protocol,
    api_root: editor.apiRoot.trim(),
    model: editor.capability === "asr" ? "" : editor.model.trim(),
    auth_mode: editor.authMode,
    options:
      editor.capability === "asr"
        ? {
            ...editor.options,
            language: editor.language.trim() || "auto",
            context: editor.context.trim(),
            timeout_seconds: editor.timeoutSeconds,
          }
        : editor.options,
    ...(editor.credential.trim() ? { credential: editor.credential.trim() } : {}),
  };
}

function editorPayload(editor: EditorState): ProviderProfileCreateRequest {
  return {
    ...editorDraftTestPayload(editor),
    display_name: editor.displayName.trim(),
    is_default: editor.isDefault,
  };
}

export function ProviderProfilesManager({
  profiles,
  onProfilesChange,
  capabilities = CAPABILITIES,
}: ProviderProfilesManagerProps) {
  const { t } = useI18n();
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [busy, setBusy] = useState(false);
  const [editorAction, setEditorAction] = useState<"save" | "test" | null>(null);
  const [editorTestResult, setEditorTestResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProviderProfile | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});
  const grouped = useMemo(
    () => Object.fromEntries(capabilities.map((capability) => [capability, profilesForCapability(profiles, capability)])),
    [capabilities, profiles],
  ) as Record<ProviderCapability, ProviderProfile[]>;

  const applyTemplate = (templateId: ProviderTemplateId) => {
    if (!editor) return;
    const template = PROVIDER_TEMPLATES[templateId];
    setEditor({
      ...editor,
      template: templateId,
      protocol: template.protocol,
      apiRoot: template.apiRoot,
      authMode: template.authMode,
    });
    setError(null);
    setEditorTestResult(null);
  };

  const updateEditor = (patch: Partial<EditorState>) => {
    setEditor((current) => current ? { ...current, ...patch } : current);
    setError(null);
    setEditorTestResult(null);
  };

  const closeEditor = () => {
    setEditor(null);
    setError(null);
    setEditorTestResult(null);
  };

  const validateEditor = (
    current: EditorState,
    requireDisplayName: boolean,
  ): boolean => {
    if (!current.apiRoot.trim() || (requireDisplayName && !current.displayName.trim())) {
      setError(t("providers.required"));
      return false;
    }
    if (current.capability !== "asr" && !current.model.trim()) {
      setError(t("providers.modelRequired"));
      return false;
    }
    return true;
  };

  const saveEditor = async () => {
    if (!editor) return;
    if (!validateEditor(editor, true)) return;
    setBusy(true);
    setEditorAction("save");
    setError(null);
    try {
      const { capability, ...common } = editorPayload(editor);
      const savedProfile = editor.profileId
        ? await api.patchProviderProfile(editor.profileId, {
          ...common,
          ...(editor.clearCredential ? { clear_credential: true } : {}),
        })
        : await api.createProviderProfile({
          ...common,
          capability,
        } satisfies ProviderProfileCreateRequest);
      setTestResults((current) => {
        const next = { ...current };
        delete next[savedProfile.id];
        return next;
      });
      await onProfilesChange();
      closeEditor();
    } catch (unknownError) {
      setError(unknownError instanceof Error ? unknownError.message : t("providers.saveFailed"));
    } finally {
      setBusy(false);
      setEditorAction(null);
    }
  };

  const testEditor = async () => {
    if (!editor) return;
    if (!validateEditor(editor, false)) return;
    setBusy(true);
    setEditorAction("test");
    setError(null);
    setEditorTestResult(t("providers.testing"));
    try {
      const payload: ProviderProfileDraftTestRequest = {
        ...editorDraftTestPayload(editor),
        ...(
          editor.profileId
          && editor.credentialConfigured
          && !editor.clearCredential
          && !editor.credential.trim()
            ? { saved_credential_profile_id: editor.profileId }
            : {}
        ),
      };
      const result = await api.testProviderProfileDraft(payload);
      setEditorTestResult(t("providers.testSucceeded", { latency: result.latency_ms }));
    } catch (unknownError) {
      setEditorTestResult(null);
      setError(unknownError instanceof Error ? unknownError.message : t("providers.testFailed"));
    } finally {
      setBusy(false);
      setEditorAction(null);
    }
  };

  const setDefault = async (profile: ProviderProfile) => {
    setBusy(true);
    setError(null);
    try {
      await api.patchProviderProfile(profile.id, { is_default: true });
      setTestResults((current) => {
        const next = { ...current };
        delete next[profile.id];
        return next;
      });
      await onProfilesChange();
    } catch (unknownError) {
      setError(unknownError instanceof Error ? unknownError.message : t("providers.saveFailed"));
    } finally {
      setBusy(false);
    }
  };

  const testProfileId = async (profileId: string) => {
    setTestResults((current) => ({ ...current, [profileId]: t("providers.testing") }));
    try {
      const result = await api.testProviderProfile(profileId);
      setTestResults((current) => ({
        ...current,
        [profileId]: t("providers.testSucceeded", { latency: result.latency_ms }),
      }));
    } catch (unknownError) {
      setTestResults((current) => ({
        ...current,
        [profileId]: unknownError instanceof Error ? unknownError.message : t("providers.testFailed"),
      }));
    }
  };

  const deleteProfile = async () => {
    if (!deleteTarget) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteProviderProfile(deleteTarget.id);
      setTestResults((current) => {
        const next = { ...current };
        delete next[deleteTarget.id];
        return next;
      });
      await onProfilesChange();
      setDeleteTarget(null);
      if (editor?.profileId === deleteTarget.id) setEditor(null);
    } catch (unknownError) {
      setError(unknownError instanceof Error ? unknownError.message : t("providers.deleteFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {capabilities.map((capability) => (
        <Card key={capability}>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <CardTitle>{capabilityTitle(capability, t)}</CardTitle>
                <p className="mt-1 text-xs text-muted-foreground">
                  {capability === "asr"
                    ? t("providers.asrDescription")
                    : capability === "frame_summary"
                      ? t("providers.frameDescription")
                      : t("providers.overallDescription")}
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                onClick={() => {
                  setError(null);
                  setEditorTestResult(null);
                  setEditor(newEditor(capability, grouped[capability].length === 0));
                }}
                disabled={busy}
              >
                <Plus className="mr-1 h-4 w-4" /> {t("providers.add")}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {capability === "asr" ? (
              <div className="rounded-md border border-border/70 bg-muted/20 p-3 text-xs text-muted-foreground">
                <p>{t("providers.capswriterAvailable")}</p>
                <p className="mt-1">{t("providers.aliyunPlanned")}</p>
              </div>
            ) : null}
            {grouped[capability].length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("providers.empty")}</p>
            ) : (
              grouped[capability].map((profile) => (
                <div key={profile.id} className="rounded-md border border-border p-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{profile.display_name}</span>
                        {profile.is_default ? <Badge variant="success">{t("providers.default")}</Badge> : null}
                        <Badge variant={profile.credential_configured ? "outline" : "secondary"}>
                          {profile.credential_configured
                            ? t("providers.credentialConfigured")
                            : profile.protocol === "capswriter_ws"
                              ? t("providers.credentialOptional")
                              : t("providers.credentialMissing")}
                        </Badge>
                      </div>
                      <p className="break-all text-xs text-muted-foreground">
                        {protocolLabel(profile.protocol)} · {profile.api_root}
                        {profile.model ? ` · ${profile.model}` : ""}
                      </p>
                      {testResults[profile.id] ? (
                        <p className="text-xs text-muted-foreground">{testResults[profile.id]}</p>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {!profile.is_default ? (
                        <Button type="button" size="sm" variant="outline" onClick={() => void setDefault(profile)} disabled={busy}>
                          <Star className="mr-1 h-3.5 w-3.5" /> {t("providers.setDefault")}
                        </Button>
                      ) : null}
                      <Button type="button" size="sm" variant="outline" onClick={() => void testProfileId(profile.id)} disabled={busy}>
                        <Wifi className="mr-1 h-3.5 w-3.5" /> {t("providers.test")}
                      </Button>
                      <Button type="button" size="sm" variant="outline" onClick={() => {
                        setError(null);
                        setEditorTestResult(null);
                        setEditor(editProfile(profile));
                      }} disabled={busy}>
                        <Pencil className="mr-1 h-3.5 w-3.5" /> {t("providers.edit")}
                      </Button>
                      <Button type="button" size="sm" variant="destructive" onClick={() => setDeleteTarget(profile)} disabled={busy}>
                        <Trash2 className="mr-1 h-3.5 w-3.5" /> {t("providers.delete")}
                      </Button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      ))}

      {editor ? (
        <Dialog
          open
          title={editor.profileId ? t("providers.editTitle") : t("providers.addTitle")}
          description={capabilityTitle(editor.capability, t)}
          closeLabel={t("common.cancel")}
          initialFocusSelector="#provider-display-name"
          size="xl"
          busy={busy}
          onClose={closeEditor}
          footer={
            <>
              <Button type="button" variant="outline" onClick={closeEditor} disabled={busy}>{t("common.cancel")}</Button>
              <Button type="button" variant="outline" onClick={() => void testEditor()} isLoading={editorAction === "test"} disabled={busy}>
                <Wifi className="mr-1 h-4 w-4" /> {t("providers.test")}
              </Button>
              <Button type="button" onClick={() => void saveEditor()} isLoading={editorAction === "save"} disabled={busy}>
                <CheckCircle2 className="mr-1 h-4 w-4" /> {t("common.save")}
              </Button>
            </>
          }
        >
          <div className="space-y-4">
            <TextField id="provider-display-name" label={t("providers.displayName")} value={editor.displayName} onChange={(displayName) => updateEditor({ displayName })} disabled={busy} />

            {editor.capability === "asr" ? (
              <div className="space-y-1">
                <label className="text-sm font-medium">{t("providers.template")}</label>
                <select className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value="capswriter" onChange={() => undefined} disabled={busy}>
                  <option value="capswriter">CapsWriter (WS)</option>
                  <option value="aliyun" disabled>{t("providers.aliyunOption")}</option>
                </select>
              </div>
            ) : (
              <>
                <div className="space-y-1">
                  <label className="text-sm font-medium" htmlFor="provider-template">{t("providers.template")}</label>
                  <select id="provider-template" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={editor.template} onChange={(event) => applyTemplate(event.target.value as ProviderTemplateId)} disabled={busy}>
                    <option value="openai_chat">OpenAI · Chat Completions</option>
                    <option value="openai_responses">OpenAI · Responses API</option>
                    <option value="anthropic">Anthropic · Messages API</option>
                    <option value="custom">{t("providers.custom")}</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium" htmlFor="provider-protocol">{t("providers.protocol")}</label>
                  <select id="provider-protocol" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={editor.protocol} onChange={(event) => {
                    const protocol = event.target.value as ProviderProtocol;
                    updateEditor({
                      template: "custom",
                      protocol,
                      authMode: protocol === "anthropic_messages" ? "x_api_key" : "bearer",
                    });
                  }} disabled={busy}>
                    <option value="openai_chat_completions">OpenAI Chat Completions</option>
                    <option value="openai_responses">OpenAI Responses</option>
                    <option value="anthropic_messages">Anthropic Messages</option>
                  </select>
                </div>
              </>
            )}

            <TextField id="provider-api-root" label={editor.capability === "asr" ? t("providers.serviceUrl") : t("providers.apiRoot")} value={editor.apiRoot} onChange={(apiRoot) => updateEditor({ apiRoot })} disabled={busy} placeholder={editor.capability === "asr" ? "ws://127.0.0.1:6016" : "https://api.example.com/v1"} />
            <p className="text-xs text-muted-foreground">
              {editor.capability === "asr" ? t("providers.capswriterUrlHint") : t("providers.apiRootHint")}
            </p>

            {editor.capability !== "asr" ? (
              <TextField id="provider-model" label={t("providers.model")} value={editor.model} onChange={(model) => updateEditor({ model })} disabled={busy} />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                <TextField id="provider-language" label={t("settings.asrLanguage")} value={editor.language} onChange={(language) => updateEditor({ language })} disabled={busy} />
                <div className="space-y-1">
                  <label className="text-sm font-medium" htmlFor="provider-timeout">{t("settings.asrTimeout")}</label>
                  <input id="provider-timeout" type="number" min={1} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={editor.timeoutSeconds} onChange={(event) => updateEditor({ timeoutSeconds: Math.max(1, Number(event.target.value) || 1) })} disabled={busy} />
                </div>
              </div>
            )}

            {editor.capability === "asr" ? (
              <div className="space-y-1">
                <label className="text-sm font-medium" htmlFor="provider-context">{t("settings.asrContext")}</label>
                <textarea id="provider-context" rows={3} maxLength={2000} className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" value={editor.context} onChange={(event) => updateEditor({ context: event.target.value })} disabled={busy} />
              </div>
            ) : null}

            <div className="space-y-1">
              <div className="flex items-center justify-between gap-3">
                <label className="text-sm font-medium" htmlFor="provider-credential">{t("providers.credential")}</label>
                <span className="text-xs text-muted-foreground">
                  {editor.credentialConfigured ? t("providers.credentialConfigured") : t("providers.credentialNotSaved")}
                </span>
              </div>
              <input id="provider-credential" type="password" autoComplete="new-password" className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={editor.credential} onChange={(event) => updateEditor({ credential: event.target.value, clearCredential: false })} placeholder={editor.credentialConfigured ? t("providers.keepCredential") : editor.capability === "asr" ? t("providers.optionalCredential") : "API key"} disabled={busy || editor.clearCredential} />
              <p className="text-xs text-muted-foreground">{t("providers.credentialHint")}</p>
              {editor.profileId && editor.credentialConfigured ? (
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input type="checkbox" checked={editor.clearCredential} onChange={(event) => updateEditor({ clearCredential: event.target.checked, credential: "" })} disabled={busy} />
                  {t("settings.clearCredential")}
                </label>
              ) : null}
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={editor.isDefault} onChange={(event) => updateEditor({ isDefault: event.target.checked })} disabled={busy} />
              {t("providers.useDefault")}
            </label>

            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            {editorTestResult ? <p className="text-sm text-muted-foreground">{editorTestResult}</p> : null}
          </div>
        </Dialog>
      ) : error ? (
        <p className="text-sm text-destructive">{error}</p>
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title={t("providers.delete")}
        description={t("providers.confirmDelete", { name: deleteTarget?.display_name ?? "" })}
        confirmLabel={t("providers.delete")}
        cancelLabel={t("common.cancel")}
        busy={busy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void deleteProfile()}
      />
    </div>
  );
}

function TextField({
  id,
  label,
  value,
  onChange,
  disabled,
  placeholder,
}: {
  id?: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  placeholder?: string;
}) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium" htmlFor={id}>{label}</label>
      <input id={id} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} placeholder={placeholder} />
    </div>
  );
}
