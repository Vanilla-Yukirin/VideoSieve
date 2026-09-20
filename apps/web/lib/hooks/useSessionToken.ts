"use client";

import { useSyncExternalStore } from "react";

import { getSessionToken, SESSION_CHANGED_EVENT } from "@/lib/auth/session";

function subscribeToSession(listener: () => void): () => void {
  window.addEventListener(SESSION_CHANGED_EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(SESSION_CHANGED_EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}

function getServerSessionToken(): null {
  return null;
}

export function useSessionToken(): string | null {
  return useSyncExternalStore(subscribeToSession, getSessionToken, getServerSessionToken);
}
