"use client";

import { useI18n } from "@/lib/i18n/I18nProvider";
import { cn } from "@/lib/utils";

export function LanguageSwitcher({ className }: { className?: string }) {
  const { locale, setLocale, t } = useI18n();

  return (
    <div className={cn("inline-flex rounded-full border border-border/80 bg-card/85 p-1 backdrop-blur", className)}>
      <div className="flex items-center gap-1 text-sm">
        <button
          type="button"
          onClick={() => setLocale("zh")}
          className={cn(
            "rounded-full px-3 py-1 transition-colors",
            locale === "zh" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
          )}
        >
          {t("lang.zh")}
        </button>
        <button
          type="button"
          onClick={() => setLocale("en")}
          className={cn(
            "rounded-full px-3 py-1 transition-colors",
            locale === "en" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
          )}
        >
          {t("lang.en")}
        </button>
      </div>
    </div>
  );
}
