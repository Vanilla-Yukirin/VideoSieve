"use client";

import { FormEvent, useState } from "react";
import { Check, Pencil, X } from "lucide-react";

import { Button } from "@/components/Button";
import { useI18n } from "@/lib/i18n/I18nProvider";

interface ProjectTitleEditorProps {
  title: string | null;
  onSave: (title: string) => Promise<void>;
}

export function ProjectTitleEditor({ title, onSave }: ProjectTitleEditorProps) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const beginEditing = () => {
    setDraft(title ?? "");
    setError(null);
    setEditing(true);
  };

  const cancelEditing = () => {
    setDraft(title ?? "");
    setError(null);
    setEditing(false);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextTitle = draft.trim();
    if (!nextTitle) {
      setError(t("project.renameRequired"));
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await onSave(nextTitle);
      setEditing(false);
    } catch (unknownError) {
      setError(
        unknownError instanceof Error ? unknownError.message : t("project.renameFailed"),
      );
    } finally {
      setSaving(false);
    }
  };

  if (!editing) {
    return (
      <div className="flex min-w-0 items-center gap-2">
        <h1 className="truncate text-2xl font-bold tracking-tight">{title}</h1>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          aria-label={t("project.rename")}
          title={t("project.rename")}
          onClick={beginEditing}
        >
          <Pencil className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-1">
      <form className="flex items-center gap-2" onSubmit={(event) => void submit(event)}>
        <label className="sr-only" htmlFor="project-title-input">
          {t("project.rename")}
        </label>
        <input
          id="project-title-input"
          autoFocus
          maxLength={200}
          className="h-10 min-w-0 flex-1 rounded-md border border-input bg-background px-3 text-xl font-bold"
          value={draft}
          placeholder={t("project.renamePlaceholder")}
          disabled={saving}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape" && !saving) cancelEditing();
          }}
        />
        <Button
          type="submit"
          size="icon"
          className="h-9 w-9 shrink-0"
          aria-label={t("common.save")}
          title={t("common.save")}
          isLoading={saving}
        >
          {!saving ? <Check className="h-4 w-4" /> : null}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-9 w-9 shrink-0"
          aria-label={t("common.cancel")}
          title={t("common.cancel")}
          disabled={saving}
          onClick={cancelEditing}
        >
          <X className="h-4 w-4" />
        </Button>
      </form>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
