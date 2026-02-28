"use client";

import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import { X } from "lucide-react";

type ToastLevel = "success" | "info" | "warning" | "error";

type ToastItem = {
  id: number;
  message: string;
  level: ToastLevel;
  visible: boolean;
};

type ToastInput = {
  message: string;
  level?: ToastLevel;
  durationMs?: number;
};

type ToastContextValue = {
  pushToast: (input: ToastInput) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const EXIT_ANIMATION_MS = 220;
const DEFAULT_DURATION_MS = 2800;
const MAX_VISIBLE = 3;

function levelClass(level: ToastLevel): string {
  if (level === "success") {
    return "border-emerald-500/40 bg-emerald-50 text-emerald-900";
  }
  if (level === "warning") {
    return "border-amber-500/40 bg-amber-50 text-amber-900";
  }
  if (level === "error") {
    return "border-red-500/40 bg-red-50 text-red-900";
  }
  return "border-blue-500/40 bg-blue-50 text-blue-900";
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.map((item) => (item.id === id ? { ...item, visible: false } : item)));
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== id));
    }, EXIT_ANIMATION_MS);
  }, []);

  const pushToast = useCallback(
    ({ message, level = "info", durationMs = DEFAULT_DURATION_MS }: ToastInput) => {
      const id = Date.now() + Math.floor(Math.random() * 1000);
      setToasts((prev) => {
        const next = [...prev, { id, message, level, visible: false }];
        return next.slice(-MAX_VISIBLE);
      });
      window.setTimeout(() => {
        setToasts((prev) => prev.map((item) => (item.id === id ? { ...item, visible: true } : item)));
      }, 20);
      window.setTimeout(() => {
        removeToast(id);
      }, durationMs);
    },
    [removeToast],
  );

  const value = useMemo(() => ({ pushToast }), [pushToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed left-4 top-4 z-[70] flex w-[min(92vw,420px)] flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            aria-live="polite"
            className={`pointer-events-auto rounded-md border px-3 py-2 shadow-sm transition-all duration-200 ${levelClass(toast.level)} ${
              toast.visible ? "translate-x-0 opacity-100" : "-translate-x-4 opacity-0"
            }`}
          >
            <div className="flex items-start gap-2">
              <p className="flex-1 text-sm leading-5">{toast.message}</p>
              <button
                type="button"
                className="rounded p-0.5 opacity-70 transition hover:opacity-100"
                onClick={() => removeToast(toast.id)}
                aria-label="dismiss"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return ctx;
}
