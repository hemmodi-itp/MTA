"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { Laptop, Menu, Moon, Search, Sparkles, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { pressable } from "@/lib/motion";
import { isActiveStatus, useRuns } from "@/lib/query/hooks";
import { useUIStore } from "@/lib/stores/ui-store";
import { Notifications } from "./notifications";
import { titleFor } from "./nav";


function ThemeSwitch() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  // true only on the client: the theme is unknown during SSR, so render a neutral icon until hydrated
  const mounted = useSyncExternalStore(() => () => {}, () => true, () => false);
  const Icon = !mounted ? Sun : theme === "system" ? Laptop : resolvedTheme === "dark" ? Moon : Sun;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex size-9 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground" aria-label="Theme">
        <motion.span key={mounted ? `${theme}-${resolvedTheme}` : "ssr"} initial={{ rotate: -40, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }}>
          <Icon className="size-[18px]" />
        </motion.span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-40 rounded-xl">
        <DropdownMenuLabel className="text-xs text-muted-foreground">Appearance</DropdownMenuLabel>
        {([["light", Sun, "Light"], ["dark", Moon, "Dark"], ["system", Laptop, "System"]] as const).map(([v, I, l]) => (
          <DropdownMenuItem key={v} onSelect={() => setTheme(v)} className={cn("gap-2", theme === v && "text-primary")}>
            <I className="size-3.5" /> {l}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

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
  const { setCommandPaletteOpen, setCopilotOpen, setMobileNavOpen } = useUIStore();
  return (
    <header className="glass sticky top-3 z-30 flex h-14 items-center gap-2 rounded-2xl px-2 shadow-lg shadow-black/5 sm:px-3">
      <button type="button" onClick={() => setMobileNavOpen(true)} aria-label="Open menu"
        className="flex size-9 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted md:hidden">
        <Menu className="size-[18px]" />
      </button>
      <motion.h1 key={pathname} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
        className="hidden min-w-24 px-1 text-sm font-semibold tracking-tight sm:block">
        {titleFor(pathname)}
      </motion.h1>

      {/* search or ask: opens the command palette */}
      <button type="button" onClick={() => setCommandPaletteOpen(true)}
        className="group mx-auto flex h-9 min-w-0 flex-1 max-w-xl items-center gap-2.5 rounded-xl border border-border bg-muted/40 px-3 text-sm text-muted-foreground transition-all hover:border-primary/40 hover:bg-muted/70 hover:shadow-[0_0_0_4px_var(--glow)]">
        <Search className="size-4 shrink-0 transition-colors group-hover:text-primary" />
        <span className="flex-1 truncate text-left">
          <span className="sm:hidden">Search…</span>
          <span className="hidden sm:inline">Search, or ask “show failed runs from yesterday”…</span>
        </span>
        <span className="kbd hidden sm:inline-flex">⌘K</span>
      </button>

      <div className="flex shrink-0 items-center gap-1">
        <Activity />
        <Notifications />
        <ThemeSwitch />
        <motion.button type="button" {...pressable} onClick={() => setCopilotOpen(true)}
          className="relative ml-1 flex h-9 items-center gap-2 overflow-hidden rounded-xl bg-gradient-to-r from-primary to-violet px-3 text-sm font-semibold text-white shadow-lg shadow-primary/25"
          aria-label="Open MTA Copilot (⌘J)">
          <Sparkles className="size-4" />
          <span className="hidden lg:inline">Copilot</span>
        </motion.button>
      </div>
    </header>
  );
}
