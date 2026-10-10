"use client";

import Link from "next/link";
import { Menu } from "lucide-react";
import { isActiveStatus, useRuns } from "@/lib/query/hooks";
import { useUIStore } from "@/lib/stores/ui-store";
import { Notifications } from "./notifications";

/** Live indicator: how many evaluations are running right now (pulses while > 0). */
function Activity() {
  const runs = useRuns();
  const live = (runs.data ?? []).filter((r) => isActiveStatus(r.status));
  if (!live.length) return null;
  return (
    <Link href="/runs?status=running" className="hidden items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary sm:flex">
      <span className="relative flex size-2">
        <span className="absolute inset-0 animate-[pulse-ring_1.8s_cubic-bezier(0.2,0,0,1)_infinite] rounded-full bg-primary" />
        <span className="relative size-2 rounded-full bg-primary" />
      </span>
      {live.length} running
    </Link>
  );
}

/** No title bar: pages carry their own heading. Only the phone menu button, live-run indicator and notifications. */
export function Topbar() {
  const setMobileNavOpen = useUIStore((s) => s.setMobileNavOpen);
  return (
    <header className="sticky top-3 z-30 flex h-14 items-center gap-2 px-2 sm:px-3">
      <button type="button" onClick={() => setMobileNavOpen(true)} aria-label="Open menu"
        className="flex size-9 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted md:hidden">
        <Menu className="size-[18px]" />
      </button>

      <div className="ml-auto flex shrink-0 items-center gap-1">
        <Activity />
        <Notifications />
      </div>
    </header>
  );
}
