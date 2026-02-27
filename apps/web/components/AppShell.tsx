"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, KeyRound, Settings } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { I18nProvider } from "@/lib/i18n/I18nProvider";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { getSessionToken, SESSION_CHANGED_EVENT } from "@/lib/auth/session";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n/I18nProvider";

function ShellChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { t } = useI18n();
  const [hasToken, setHasToken] = useState(false);

  const syncHasToken = () => {
    setHasToken(Boolean(getSessionToken()));
  };

  useEffect(() => {
    syncHasToken();
  }, [pathname]);

  useEffect(() => {
    syncHasToken();
    window.addEventListener(SESSION_CHANGED_EVENT, syncHasToken);
    window.addEventListener("storage", syncHasToken);

    return () => {
      window.removeEventListener(SESSION_CHANGED_EVENT, syncHasToken);
      window.removeEventListener("storage", syncHasToken);
    };
  }, []);

  const isCompactPage = pathname.startsWith("/login") || pathname.startsWith("/setup");

  const navItems = useMemo(
    () => [
      { href: "/", label: t("home.title"), icon: Home, show: true },
      { href: "/settings/cookies", label: t("home.cookieVault"), icon: KeyRound, show: hasToken },
      { href: "/settings/system", label: t("home.systemSettings"), icon: Settings, show: hasToken },
    ],
    [hasToken, t],
  );

  const isNavItemActive = (href: string): boolean => {
    if (href === "/") {
      return pathname === "/" || pathname.startsWith("/projects/") || pathname.startsWith("/jobs/");
    }
    return pathname === href || pathname.startsWith(`${href}/`);
  };

  if (isCompactPage) {
    return (
      <>
        {children}
        <LanguageSwitcher className="fixed bottom-4 left-1/2 z-40 -translate-x-1/2" />
      </>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-border/70 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3 md:px-8">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-md border border-primary/40 bg-primary/20" />
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">{t("shell.controlPlane")}</p>
              <p className="text-sm font-semibold tracking-tight">VideoSieve</p>
            </div>
          </div>
          <nav className="hidden items-center gap-1 md:flex">
            {navItems
              .filter((item) => item.show)
              .map((item) => {
                const active = isNavItemActive(item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors",
                      active
                        ? "border-primary/40 bg-primary/20 text-foreground"
                        : "border-transparent text-muted-foreground hover:border-border/80 hover:bg-muted/60 hover:text-foreground",
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                );
              })}
          </nav>
          <LanguageSwitcher className="shrink-0" />
        </div>
        <div className="mx-auto flex max-w-7xl items-center gap-1 px-4 pb-3 md:hidden">
          {navItems
            .filter((item) => item.show)
            .map((item) => {
              const active = isNavItemActive(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={`${item.href}-mobile`}
                  href={item.href}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-xs transition-colors",
                    active
                      ? "border-primary/40 bg-primary/20 text-foreground"
                      : "border-transparent text-muted-foreground hover:border-border/80 hover:bg-muted/60 hover:text-foreground",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {item.label}
                </Link>
              );
            })}
        </div>
      </header>
      <div className="mx-auto max-w-7xl px-2 py-6 md:px-6 md:py-8">{children}</div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <I18nProvider>
      <ShellChrome>{children}</ShellChrome>
    </I18nProvider>
  );
}
