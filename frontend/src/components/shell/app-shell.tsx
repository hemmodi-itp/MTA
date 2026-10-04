"use client";

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { spring } from "@/lib/motion";
import { useUIStore } from "@/lib/stores/ui-store";
import { useRunsPoller } from "@/lib/query/hooks";
import type { CurrentUser } from "@/lib/auth/session";
import { Sidebar, SIDEBAR_WIDTH } from "./sidebar";
import { Topbar } from "./topbar";
import { CommandPalette } from "./command-palette";
import { Copilot } from "./copilot";

function useIsDesktop() {
  const [desktop, setDesktop] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const update = () => setDesktop(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return desktop;
}

/** The app frame: ambient backdrop, floating sidebar, sticky glass topbar, ⌘K palette and ⌘J Copilot. */
export function AppShell({ user, children }: { user: CurrentUser; children: React.ReactNode }) {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const desktop = useIsDesktop();
  useRunsPoller(); // the one timer behind every useRuns() in the shell and pages
  const pad = desktop ? (collapsed ? SIDEBAR_WIDTH.closed : SIDEBAR_WIDTH.open) + 24 : 8;
  return (
    <>
      <div className="app-backdrop" aria-hidden />
      <Sidebar user={user} />
      <motion.div initial={false} animate={{ paddingLeft: pad }} transition={spring.gentle}
        className="flex min-h-screen flex-col pr-2 sm:pr-3">
        <div className="pt-0 sm:pt-0"><Topbar /></div>
        <main className="mx-auto w-full max-w-[1600px] flex-1 px-1 pb-10 pt-6 sm:px-2">{children}</main>
      </motion.div>
      <CommandPalette />
      <Copilot />
    </>
  );
}
