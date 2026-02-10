"use client";

import { useI18n } from "@/lib/i18n/I18nProvider";
import { cn } from "@/lib/utils";

export function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n();

  return (
    <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-full border bg-background/95 p-1 shadow-sm backdrop-blur">
      <div className="flex items-center gap-1 text-sm">
        <button
          type="button"
          onClick={() => setLocale("zh")}
          className={cn(
            "rounded-full px-3 py-1 transition-colors",
            locale === "zh" ? "bg-primary text-primary-foreground" : "hover:bg-muted",
          )}
        >
          {t("lang.zh")}
        </button>
        <button
          type="button"
          onClick={() => setLocale("en")}
          className={cn(
            "rounded-full px-3 py-1 transition-colors",
            locale === "en" ? "bg-primary text-primary-foreground" : "hover:bg-muted",
          )}
        >
          {t("lang.en")}
        </button>
      </div>
    </div>
  );
}
