"use client";

import { useEffect } from "react";
import { useUIStore } from "@/lib/stores/ui-store";
import { useRunsPoller } from "@/lib/query/hooks";
import type { CurrentUser } from "@/lib/auth/session";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";
import { CommandPalette } from "./command-palette";
import { Copilot } from "./copilot";
import { CurrentUserProvider } from "./current-user";

/** Mirrors the persisted sidebar state onto <html data-sidebar>, which drives the rail width and the content offset
 *  in CSS (the root layout sets it before first paint, so nothing jumps on load). */
function useSidebarAttribute() {
  useEffect(() => {
    const apply = (collapsed: boolean) => {
      document.documentElement.dataset.sidebar = collapsed ? "collapsed" : "open";
    };
    apply(useUIStore.getState().sidebarCollapsed);
    return useUIStore.subscribe((s) => apply(s.sidebarCollapsed));
  }, []);
}

/** The app frame: ambient backdrop, floating sidebar, sticky top bar, ⌘K palette and ⌘J Copilot. */
export function AppShell({ user, children }: { user: CurrentUser; children: React.ReactNode }) {
  useRunsPoller(); // the one timer behind every useRuns() in the shell and pages
  useSidebarAttribute();
  return (
    <CurrentUserProvider user={user}>
      <div className="app-backdrop" aria-hidden />
      <Sidebar user={user} />
      {/* desktop offset = sidebar width + gutter, straight from CSS: correct from the first paint, no measuring */}
      <div className="flex min-h-screen flex-col pr-2 pl-2 sm:pr-3 md:pl-[calc(var(--sidebar-w)+1.5rem)]">
        <Topbar />
        <main id="main" className="mx-auto w-full max-w-[1600px] flex-1 px-1 pt-4 pb-10 sm:px-2 sm:pt-6">{children}</main>
      </div>
      <CommandPalette />
      <Copilot />
    </CurrentUserProvider>
  );
}
