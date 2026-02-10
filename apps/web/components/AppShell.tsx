"use client";

import { I18nProvider } from "@/lib/i18n/I18nProvider";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <I18nProvider>
      {children}
      <LanguageSwitcher />
    </I18nProvider>
  );
}
