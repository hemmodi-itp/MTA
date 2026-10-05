"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { Menu } from "lucide-react";
import { cn } from "@/lib/utils";
import { isActiveStatus, useRuns } from "@/lib/query/hooks";
import { useUIStore } from "@/lib/stores/ui-store";
import { Notifications } from "./notifications";
import { titleFor } from "./nav";

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

export function Topbar() {
  const pathname = usePathname();
  const setMobileNavOpen = useUIStore((s) => s.setMobileNavOpen);
  // Projects pages carry their own heading: on desktop the bar would only repeat it (phones keep it for the menu)
  const bare = pathname.startsWith("/projects");
  return (
    <header className={cn("glass sticky top-3 z-30 flex h-14 items-center gap-2 rounded-2xl px-2 shadow-lg shadow-black/5 sm:px-3",
      bare && "md:hidden")}>
      <button type="button" onClick={() => setMobileNavOpen(true)} aria-label="Open menu"
        className="flex size-9 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted md:hidden">
        <Menu className="size-[18px]" />
      </button>
      <motion.h1 key={pathname} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
        className="min-w-24 flex-1 px-1 text-sm font-semibold tracking-tight">
        {titleFor(pathname)}
      </motion.h1>

      <div className="flex shrink-0 items-center gap-1">
        <Activity />
        <Notifications />
      </div>
    </header>
  );
}
