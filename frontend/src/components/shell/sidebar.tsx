"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronLeft, ChevronsUpDown, Command, LogOut, Plus, Sparkles, X } from "lucide-react";
import { useMemo } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { spring } from "@/lib/motion";
import { isActiveStatus, useProjects, useRuns } from "@/lib/query/hooks";
import { useUIStore, type WorkspaceScope } from "@/lib/stores/ui-store";
import { logout } from "@/app/actions/auth";
import type { CurrentUser } from "@/lib/auth/session";
import { NAV, SETTINGS_NAV, type NavItem } from "./nav";

export const SIDEBAR_WIDTH = { open: 252, closed: 76 } as const;

export function initials(user: CurrentUser) {
  const source = user.name?.trim() || user.email;
  const parts = source.split(/[\s@._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

const SCOPES: { value: WorkspaceScope; label: string; hint: string }[] = [
  { value: "all", label: "All projects", hint: "Yours and the shared samples" },
  { value: "mine", label: "My projects", hint: "Only repos you submitted" },
  { value: "samples", label: "Samples", hint: "Shared demo evaluations" },
];

function Reveal({ show, children, className }: { show: boolean; children: React.ReactNode; className?: string }) {
  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.span
          initial={{ opacity: 0, x: -6 }}
          animate={{ opacity: 1, x: 0, transition: { delay: 0.06, duration: 0.18 } }}
          exit={{ opacity: 0, x: -6, transition: { duration: 0.1 } }}
          className={cn("truncate", className)}
        >
          {children}
        </motion.span>
      )}
    </AnimatePresence>
  );
}

function NavLink({ item, active, open, badge, onNavigate }: { item: NavItem; active: boolean; open: boolean; badge?: number;
  onNavigate?: () => void }) {
  const link = (
    <Link
      href={item.href}
      onClick={onNavigate}
      className={cn(
        "group relative flex h-10 items-center gap-3 rounded-xl px-3 text-sm font-medium outline-none transition-colors",
        "focus-visible:ring-2 focus-visible:ring-ring/60",
        active ? "text-foreground" : "text-muted-foreground hover:text-foreground"
      )}
    >
      {active && (
        <motion.span layoutId="nav-active" transition={spring.layout}
          className="absolute inset-0 rounded-xl border border-primary/25 bg-gradient-to-r from-primary/15 via-primary/8 to-transparent">
          <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-primary" />
        </motion.span>
      )}
      {!active && <span className="absolute inset-0 rounded-xl bg-muted/0 transition-colors group-hover:bg-muted/60" />}
      <item.icon className={cn("relative size-[18px] shrink-0 transition-transform group-hover:scale-110", active && "text-primary")} />
      <Reveal show={open} className="relative flex-1">{item.label}</Reveal>
      {badge ? (
        open ? (
          <span className="relative rounded-full bg-primary/15 px-1.5 text-[11px] font-semibold tabular-nums text-primary">{badge}</span>
        ) : (
          <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-primary ring-2 ring-background" />
        )
      ) : null}
    </Link>
  );
  if (open) return link;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right" className="max-w-56">
        <p className="font-medium">{item.label}</p>
        <p className="text-xs opacity-80">{item.hint}</p>
      </TooltipContent>
    </Tooltip>
  );
}

function SidebarBody({ user, open, onNavigate }: { user: CurrentUser; open: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const runs = useRuns();
  const projects = useProjects();
  const { workspace, setWorkspace, setCopilotOpen, setCommandPaletteOpen } = useUIStore();
  const active = (runs.data ?? []).filter((r) => isActiveStatus(r.status)).length;
  const counts = useMemo(() => {
    const list = projects.data ?? [];
    return { all: list.length, mine: list.filter((p) => !p.isSample).length, samples: list.filter((p) => p.isSample).length };
  }, [projects.data]);
  const scope = SCOPES.find((s) => s.value === workspace) ?? SCOPES[0];

  const quick = [
    { label: "Ask Copilot", icon: Sparkles, kbd: "⌘J", onClick: () => { setCopilotOpen(true); onNavigate?.(); } },
    { label: "Command palette", icon: Command, kbd: "⌘K", onClick: () => { setCommandPaletteOpen(true); onNavigate?.(); } },
  ];

  return (
    <div className="flex h-full flex-col gap-4 p-3">
      {/* brand */}
      <div className="flex h-11 items-center gap-3 px-1.5">
        <div className="relative flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-violet text-white shadow-lg shadow-primary/30">
          <Sparkles className="size-[18px]" />
          <span className="absolute inset-0 rounded-xl ring-1 ring-inset ring-white/20" />
        </div>
        <Reveal show={open} className="flex flex-col leading-tight">
          <span className="text-[15px] font-bold tracking-tight">MTA</span>
          <span className="text-[11px] font-medium text-muted-foreground">Master Testing Agent</span>
        </Reveal>
      </div>

      {/* workspace switcher */}
      <DropdownMenu>
        <DropdownMenuTrigger
          className={cn("flex h-11 items-center gap-2.5 rounded-xl border border-border bg-muted/40 px-2.5 text-left text-sm outline-none transition-colors hover:bg-muted/70 focus-visible:ring-2 focus-visible:ring-ring/60",
            !open && "justify-center px-0")}
          aria-label="Switch workspace scope"
        >
          <span className="flex size-6 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-success/80 to-primary/80 text-[11px] font-bold text-white">
            {scope.label[0]}
          </span>
          <Reveal show={open} className="flex min-w-0 flex-1 flex-col leading-tight">
            <span className="truncate font-medium">{scope.label}</span>
            <span className="text-[11px] text-muted-foreground">{counts[scope.value]} project{counts[scope.value] === 1 ? "" : "s"}</span>
          </Reveal>
          {open && <ChevronsUpDown className="size-4 shrink-0 text-muted-foreground" />}
        </DropdownMenuTrigger>
        <DropdownMenuContent side="right" align="start" className="w-64 rounded-xl">
          <DropdownMenuLabel className="text-xs text-muted-foreground">Workspace scope</DropdownMenuLabel>
          {SCOPES.map((s) => (
            <DropdownMenuItem key={s.value} onSelect={() => setWorkspace(s.value)} className="gap-2.5 py-2">
              <div className="flex-1">
                <p className="text-sm font-medium">{s.label} <span className="text-muted-foreground">· {counts[s.value]}</span></p>
                <p className="text-xs text-muted-foreground">{s.hint}</p>
              </div>
              {workspace === s.value && <Check className="size-4 text-primary" />}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      {/* navigation */}
      <nav className="flex flex-col gap-1" aria-label="Main">
        <Reveal show={open} className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/80">
          Workspace
        </Reveal>
        {NAV.map((item) => (
          <NavLink key={item.href} item={item} open={open} active={pathname.startsWith(item.href)}
            badge={item.href === "/runs" ? active : undefined} onNavigate={onNavigate} />
        ))}
      </nav>

      {/* AI quick actions */}
      <div className="flex flex-col gap-1">
        <Reveal show={open} className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/80">
          AI actions
        </Reveal>
        <Link href="/projects/new" onClick={onNavigate}
          className={cn("group relative flex h-10 items-center gap-3 overflow-hidden rounded-xl bg-gradient-to-r from-primary to-violet px-3 text-sm font-semibold text-white shadow-lg shadow-primary/25 transition-transform hover:scale-[1.02] active:scale-[0.98]",
            !open && "justify-center px-0")}>
          <Plus className="size-[18px] shrink-0" />
          <Reveal show={open}>New evaluation</Reveal>
          <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/25 to-transparent transition-transform duration-700 group-hover:translate-x-full" />
        </Link>
        {quick.map((q) => {
          const btn = (
            <button key={q.label} type="button" onClick={q.onClick}
              className={cn("group flex h-10 items-center gap-3 rounded-xl px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground",
                !open && "justify-center px-0")}>
              <q.icon className="size-[18px] shrink-0 transition-transform group-hover:scale-110" />
              <Reveal show={open} className="flex-1 text-left">{q.label}</Reveal>
              {open && <span className="kbd">{q.kbd}</span>}
            </button>
          );
          return open ? btn : (
            <Tooltip key={q.label}><TooltipTrigger asChild>{btn}</TooltipTrigger><TooltipContent side="right">{q.label} · {q.kbd}</TooltipContent></Tooltip>
          );
        })}
      </div>

      {/* profile */}
      <div className="mt-auto flex flex-col gap-1">
        <NavLink item={SETTINGS_NAV} open={open} active={pathname.startsWith("/settings")} onNavigate={onNavigate} />
        <DropdownMenu>
          <DropdownMenuTrigger className={cn("flex items-center gap-3 rounded-xl border border-border bg-muted/30 p-2 text-left outline-none transition-colors hover:bg-muted/60",
            !open && "justify-center border-transparent bg-transparent")} aria-label="Account">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet to-primary text-xs font-bold text-white">
              {initials(user)}
            </span>
            <Reveal show={open} className="flex min-w-0 flex-1 flex-col leading-tight">
              <span className="truncate text-sm font-medium">{user.name ?? user.email.split("@")[0]}</span>
              <span className="truncate text-[11px] text-muted-foreground">{user.email}</span>
            </Reveal>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="right" align="end" className="w-56 rounded-xl">
            <DropdownMenuLabel className="font-normal">
              <p className="text-sm font-medium">{user.name ?? user.email}</p>
              <p className="truncate text-xs text-muted-foreground">{user.email}</p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => logout()} className="gap-2"><LogOut className="size-3.5" /> Log out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}

/** Floating, collapsible desktop sidebar (md+) and slide-in drawer (mobile). */
export function Sidebar({ user }: { user: CurrentUser }) {
  const { sidebarCollapsed, toggleSidebar, mobileNavOpen, setMobileNavOpen } = useUIStore();
  const open = !sidebarCollapsed;
  return (
    <>
      <motion.aside
        initial={false}
        animate={{ width: open ? SIDEBAR_WIDTH.open : SIDEBAR_WIDTH.closed }}
        transition={spring.gentle}
        className="glass fixed inset-y-3 left-3 z-40 hidden overflow-visible rounded-2xl shadow-2xl shadow-black/10 md:block"
      >
        <div className="h-full overflow-y-auto overflow-x-hidden">
          <SidebarBody user={user} open={open} />
        </div>
        <button
          type="button"
          onClick={toggleSidebar}
          aria-label={open ? "Collapse sidebar" : "Expand sidebar"}
          className="absolute -right-3 top-[4.25rem] flex size-6 items-center justify-center rounded-full border border-border bg-popover text-muted-foreground shadow-md transition-colors hover:text-foreground"
        >
          <motion.span animate={{ rotate: open ? 0 : 180 }} transition={spring.snappy}><ChevronLeft className="size-3.5" /></motion.span>
        </button>
      </motion.aside>

      <AnimatePresence>
        {mobileNavOpen && (
          <>
            <motion.div key="scrim" className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm md:hidden"
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMobileNavOpen(false)} />
            <motion.aside key="drawer" className="glass fixed inset-y-2 left-2 z-50 w-[272px] rounded-2xl shadow-2xl md:hidden"
              initial={{ x: -300 }} animate={{ x: 0 }} exit={{ x: -300 }} transition={spring.gentle}>
              <button type="button" onClick={() => setMobileNavOpen(false)} aria-label="Close menu"
                className="absolute right-3 top-4 rounded-lg p-1.5 text-muted-foreground hover:bg-muted"><X className="size-4" /></button>
              <SidebarBody user={user} open onNavigate={() => setMobileNavOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
