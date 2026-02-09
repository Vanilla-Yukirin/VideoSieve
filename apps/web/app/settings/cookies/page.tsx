"use client";

import { FormEvent, useMemo, useState } from "react";
import useSWR from "swr";
import Link from "next/link";

import { api } from "@/lib/api/client";
import { CookieListItem } from "@/lib/api/types";
import { Button } from "@/components/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/Card";

type EditState = {
  id: string;
  name: string;
  cookieText: string;
};

function statusClass(status: CookieListItem["status"]): string {
  if (status === "valid") return "text-green-700";
  if (status === "expired") return "text-amber-700";
  if (status === "invalid") return "text-red-700";
  return "text-slate-600";
}

export default function CookieVaultSettingsPage() {
  const { data: cookies, error, mutate, isLoading } = useSWR("/me/cookies", api.listMeCookies);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string>("");
  const [createName, setCreateName] = useState("");
  const [createCookieText, setCreateCookieText] = useState("");
  const [createDefault, setCreateDefault] = useState(false);
  const [edit, setEdit] = useState<EditState | null>(null);

  const rows = useMemo(() => cookies ?? [], [cookies]);

  const onCreate = async (event: FormEvent) => {
    event.preventDefault();
    if (!createName.trim() || !createCookieText.trim()) {
      setMessage("Name and Netscape cookie text are required.");
      return;
    }
    setBusyId("create");
    setMessage("");
    try {
      await api.createMeCookie({
        name: createName.trim(),
        cookie_netscape_text: createCookieText,
        is_default: createDefault,
      });
      setCreateName("");
      setCreateCookieText("");
      setCreateDefault(false);
      await mutate();
      setMessage("Cookie created.");
    } catch (unknownError) {
      const msg = unknownError instanceof Error ? unknownError.message : "Create failed";
      setMessage(msg);
    } finally {
      setBusyId(null);
    }
  };

  const onDelete = async (cookieId: string) => {
    setBusyId(cookieId);
    setMessage("");
    try {
      await api.deleteMeCookie(cookieId);
      await mutate();
      if (edit?.id === cookieId) {
        setEdit(null);
      }
      setMessage("Cookie deleted.");
    } catch (unknownError) {
      const msg = unknownError instanceof Error ? unknownError.message : "Delete failed";
      setMessage(msg);
    } finally {
      setBusyId(null);
    }
  };

  const onSetDefault = async (cookieId: string) => {
    setBusyId(cookieId);
    setMessage("");
    try {
      await api.patchMeCookie(cookieId, { is_default: true });
      await mutate();
      setMessage("Default cookie updated.");
    } catch (unknownError) {
      const msg = unknownError instanceof Error ? unknownError.message : "Set default failed";
      setMessage(msg);
    } finally {
      setBusyId(null);
    }
  };

  const onValidate = async (cookieId: string) => {
    setBusyId(cookieId);
    setMessage("");
    try {
      const result = await api.validateMeCookie(cookieId, {});
      await mutate((current) => {
        if (!current) return current;
        return current.map((cookie) =>
          cookie.id === cookieId
            ? {
                ...cookie,
                status: result.status,
                last_validated_at: result.last_validated_at ?? null,
                last_error_code: result.last_error_code ?? null,
              }
            : cookie,
        );
      }, false);
      setMessage(`Validation completed: ${result.status}`);
    } catch (unknownError) {
      const msg = unknownError instanceof Error ? unknownError.message : "Validate failed";
      setMessage(msg);
    } finally {
      setBusyId(null);
    }
  };

  const onSaveEdit = async (event: FormEvent) => {
    event.preventDefault();
    if (!edit) return;
    if (!edit.name.trim()) {
      setMessage("Cookie name cannot be empty.");
      return;
    }
    setBusyId(edit.id);
    setMessage("");
    try {
      await api.patchMeCookie(edit.id, {
        name: edit.name.trim(),
        cookie_netscape_text: edit.cookieText.trim() ? edit.cookieText : undefined,
      });
      await mutate();
      setEdit(null);
      setMessage("Cookie updated.");
    } catch (unknownError) {
      const msg = unknownError instanceof Error ? unknownError.message : "Update failed";
      setMessage(msg);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <main className="container mx-auto space-y-6 p-4 md:p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Cookie Vault</h1>
          <p className="text-sm text-muted-foreground">
            Manage login cookies by id. Cookie plaintext is never shown after submit.
          </p>
        </div>
        <Link href="/">
          <Button variant="outline">Back to Projects</Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Add Cookie</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-3" onSubmit={onCreate}>
            <input
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              placeholder="Cookie name"
              disabled={busyId === "create"}
            />
            <textarea
              className="min-h-32 w-full rounded-md border border-input bg-background px-3 py-2 text-xs"
              value={createCookieText}
              onChange={(e) => setCreateCookieText(e.target.value)}
              placeholder="# Netscape cookie file text"
              disabled={busyId === "create"}
            />
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={createDefault}
                onChange={(e) => setCreateDefault(e.target.checked)}
                disabled={busyId === "create"}
              />
              Set as default cookie
            </label>
            <Button type="submit" isLoading={busyId === "create"}>
              Create Cookie
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Saved Cookies</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {isLoading ? <p className="text-sm text-muted-foreground">Loading cookies...</p> : null}
          {error ? <p className="text-sm text-destructive">Failed to load cookies.</p> : null}

          {rows.map((cookie) => {
            const isBusy = busyId === cookie.id;
            const isEditing = edit?.id === cookie.id;

            return (
              <div key={cookie.id} className="rounded-md border p-3">
                {isEditing ? (
                  <form className="space-y-2" onSubmit={onSaveEdit}>
                    <input
                      className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                      value={edit.name}
                      onChange={(e) => setEdit({ ...edit, name: e.target.value })}
                      disabled={isBusy}
                    />
                    <textarea
                      className="min-h-28 w-full rounded-md border border-input bg-background px-3 py-2 text-xs"
                      value={edit.cookieText}
                      onChange={(e) => setEdit({ ...edit, cookieText: e.target.value })}
                      placeholder="Paste new Netscape cookie text to replace (optional)"
                      disabled={isBusy}
                    />
                    <div className="flex gap-2">
                      <Button type="submit" isLoading={isBusy}>
                        Save
                      </Button>
                      <Button type="button" variant="outline" onClick={() => setEdit(null)} disabled={isBusy}>
                        Cancel
                      </Button>
                    </div>
                  </form>
                ) : (
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <div className="font-medium">{cookie.name}</div>
                        <div className="text-xs text-muted-foreground">id: {cookie.id}</div>
                      </div>
                      <div className="text-xs">
                        <span className={statusClass(cookie.status)}>{cookie.status}</span>
                        {cookie.is_default ? <span className="ml-2 rounded bg-muted px-2 py-0.5">default</span> : null}
                      </div>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      last_validated_at: {cookie.last_validated_at ?? "-"}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => setEdit({ id: cookie.id, name: cookie.name, cookieText: "" })}
                        disabled={isBusy}
                      >
                        Edit
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => onValidate(cookie.id)}
                        isLoading={isBusy}
                      >
                        Validate
                      </Button>
                      {!cookie.is_default ? (
                        <Button type="button" variant="outline" onClick={() => onSetDefault(cookie.id)} disabled={isBusy}>
                          Set Default
                        </Button>
                      ) : null}
                      <Button type="button" variant="destructive" onClick={() => onDelete(cookie.id)} disabled={isBusy}>
                        Delete
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {!isLoading && !error && rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No cookies yet.</p>
          ) : null}

          {message ? <p className="text-sm">{message}</p> : null}
        </CardContent>
      </Card>
    </main>
  );
}
