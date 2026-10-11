"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, Sparkles } from "lucide-react";
import { LiveDot } from "@/components/motion/live-dot";
import { isActiveStatus, useRuns } from "@/lib/query/hooks";
import { useUIStore } from "@/lib/stores/ui-store";
import { NAV, SETTINGS_NAV } from "./nav";
import { Notifications } from "./notifications";

/** Live indicator: how many evaluations are running right now (pulses while > 0). */
function Activity() {
  const runs = useRuns();
  const live = (runs.data ?? []).filter((r) => isActiveStatus(r.status));
  if (!live.length) return null;
  return (
    <Link
      href="/runs?status=running"
      className="tone-info tone-tint tone-border tone-text hidden h-8 items-center gap-2 rounded-full border px-3 text-xs font-medium transition-colors duration-(--dur-micro) hover:bg-primary/15 sm:flex"
    >
      <LiveDot />
      {live.length} running
    </Link>
  );
}

/** Pages carry their own heading; on phones the bar adds the brand and the section name so you know where you are. */
export function Topbar() {
  const setMobileNavOpen = useUIStore((s) => s.setMobileNavOpen);
  const pathname = usePathname();
  const section = [...NAV, SETTINGS_NAV].find((n) => pathname.startsWith(n.href))?.label;
  return (
    <header className="sticky top-0 z-(--z-sticky) -mx-2 flex h-14 items-center gap-2 border-b border-border bg-background/80 px-3 backdrop-blur-lg sm:-mr-3 md:static md:mt-3 md:mx-0 md:border-0 md:bg-transparent md:px-3 md:backdrop-blur-none">
      <button type="button" onClick={() => setMobileNavOpen(true)} aria-label="Open menu"
        className="flex size-9 items-center justify-center rounded-xl text-muted-foreground transition-colors duration-(--dur-micro) hover:bg-muted hover:text-foreground md:hidden">
        <Menu aria-hidden className="size-[18px]" />
      </button>
      <Link href="/dashboard" className="flex min-w-0 items-center gap-2 rounded-lg md:hidden">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary-solid to-violet text-white">
          <Sparkles aria-hidden className="size-3.5" />
        </span>
        <span className="truncate text-sm font-semibold">{section ?? "MTA"}</span>
      </Link>

      {/* full-width and right-aligned, so the bell never moves when the live pill appears */}
      <div className="flex min-w-0 flex-1 items-center justify-end gap-1">
        <Activity />
        <Notifications />
      </div>
    </header>
  );
}
