"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { m } from "framer-motion";
import { Check, ChevronLeft, Command, Laptop, LogOut, Moon, Plus, Sparkles, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Indicator, IndicatorGroup } from "@/components/motion/sliding-indicator";
import { cn } from "@/lib/utils";
import { transition } from "@/lib/motion";
import { isActiveStatus, useRuns } from "@/lib/query/hooks";
import { useUIStore } from "@/lib/stores/ui-store";
import { logout } from "@/app/actions/auth";
import type { CurrentUser } from "@/lib/auth/session";
import { NAV, SETTINGS_NAV, type NavItem } from "./nav";

export function initials(user: CurrentUser) {
  const source = user.name?.trim() || user.email;
  const parts = source.split(/[\s@._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

const THEMES = [["light", Sun, "Light"], ["dark", Moon, "Dark"], ["system", Laptop, "System"]] as const;

/*
 * The collapsed desktop rail is pure CSS: <html data-sidebar="collapsed"> (set before first paint) narrows the aside
 * and the `rail:` variant hides labels and re-centres icons. Server and client render identical markup either way,
 * so collapsing never shifts layout on load. The mobile drawer reuses the same body, always expanded.
 */
type Variant = "desktop" | "drawer";

/** Text that disappears in the collapsed rail and fades back in when it expands. */
function Label({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("rail-label truncate rail:hidden", className)}>{children}</span>;
}

/** Tooltip that only shows while the desktop rail is collapsed (labels are hidden then). */
function RailTooltip({ variant, label, hint, children }: { variant: Variant; label: string; hint?: string; children: React.ReactElement }) {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  return (
    <Tooltip open={variant === "desktop" && collapsed ? undefined : false}>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right" className="max-w-56">
        <p className="font-medium">{label}</p>
        {hint && <p className="text-xs opacity-80">{hint}</p>}
      </TooltipContent>
    </Tooltip>
  );
}

function NavLink({ item, active, badge, variant, onNavigate }: {
  item: NavItem; active: boolean; badge?: number; variant: Variant; onNavigate?: () => void;
}) {
  return (
    <RailTooltip variant={variant} label={item.label} hint={item.hint}>
      <Link
        href={item.href}
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        className={cn(
          "group relative flex h-10 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors duration-(--dur-micro) rail:justify-center rail:px-0",
          active ? "text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
        )}
      >
        {active && (
          <Indicator className="rounded-xl border border-primary/25 bg-gradient-to-r from-primary/15 via-primary/8 to-transparent before:absolute before:inset-y-2 before:left-0 before:w-0.5 before:rounded-full before:bg-primary" />
        )}
        <item.icon aria-hidden className={cn("relative size-[18px] shrink-0", active && "text-primary")} />
        <Label className="relative flex-1">{item.label}</Label>
        {badge ? (
          <>
            <span className="relative rounded-full bg-primary/12 px-1.5 text-2xs font-semibold tabular-nums text-info-fg rail:hidden">
              {badge}
              <span className="sr-only"> running</span>
            </span>
            <span aria-hidden className="absolute top-1.5 right-1.5 hidden size-2 rounded-full bg-primary ring-2 ring-background rail:block" />
          </>
        ) : null}
      </Link>
    </RailTooltip>
  );
}

/** Appearance: light / dark / follow the OS. Shows the current choice when the sidebar is open. */
function ThemeSwitch({ variant }: { variant: Variant }) {
  const { theme, setTheme, resolvedTheme } = useTheme();
  // true only on the client: the theme is unknown during SSR, so render a neutral icon until hydrated
  const mounted = useSyncExternalStore(() => () => {}, () => true, () => false);
  const Icon = !mounted ? Sun : theme === "system" ? Laptop : resolvedTheme === "dark" ? Moon : Sun;
  const current = THEMES.find(([v]) => v === theme)?.[2] ?? "System";
  return (
    <DropdownMenu>
      <RailTooltip variant={variant} label="Theme" hint={mounted ? current : undefined}>
        <DropdownMenuTrigger
          aria-label="Theme"
          className="flex h-10 w-full items-center gap-3 rounded-xl px-3 text-sm font-medium text-muted-foreground transition-colors duration-(--dur-micro) hover:bg-muted/60 hover:text-foreground rail:justify-center rail:px-0"
        >
          {/* the icon turns in when the theme changes: it explains what just happened */}
          <m.span key={mounted ? `${theme}-${resolvedTheme}` : "ssr"} initial={{ rotate: -30, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} transition={transition.micro}>
            <Icon aria-hidden className="size-[18px] shrink-0" />
          </m.span>
          <Label className="flex-1 text-left">Theme</Label>
          {mounted && <span className="text-xs text-muted-foreground rail:hidden">{current}</span>}
        </DropdownMenuTrigger>
      </RailTooltip>
      <DropdownMenuContent side="right" align="end" className="w-40 rounded-xl">
        <DropdownMenuLabel className="text-xs text-muted-foreground">Appearance</DropdownMenuLabel>
        {THEMES.map(([v, I, l]) => (
          <DropdownMenuItem key={v} onSelect={() => setTheme(v)} className={cn("gap-2", theme === v && "text-info-fg")}>
            <I className="size-3.5" /> {l}
            {theme === v && <Check className="ml-auto size-3.5" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

const groupLabel = "rail-label px-3 pb-1 type-eyebrow text-muted-foreground rail:hidden";

function SidebarBody({ user, variant, onNavigate }: { user: CurrentUser; variant: Variant; onNavigate?: () => void }) {
  const pathname = usePathname();
  const runs = useRuns();
  const { setCopilotOpen, setCommandPaletteOpen } = useUIStore();
  const running = (runs.data ?? []).filter((r) => isActiveStatus(r.status)).length;
  const activeHref = [...NAV, SETTINGS_NAV].find((n) => pathname.startsWith(n.href))?.href ?? null;

  const quick = [
    { label: "Ask Copilot", icon: Sparkles, kbd: "⌘J", onClick: () => { setCopilotOpen(true); onNavigate?.(); } },
    { label: "Command palette", icon: Command, kbd: "⌘K", onClick: () => { setCommandPaletteOpen(true); onNavigate?.(); } },
  ];

  return (
    <IndicatorGroup activeKey={activeHref}>
      <div className="flex h-full flex-col gap-4 p-3">
        {/* brand */}
        <Link href="/dashboard" onClick={onNavigate} className="flex h-11 items-center gap-3 rounded-xl px-1.5 rail:justify-center rail:px-0">
          <span className="relative flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-solid to-violet text-white shadow-control">
            <Sparkles aria-hidden className="size-[18px]" />
            <span className="absolute inset-0 rounded-xl ring-1 ring-white/20 ring-inset" />
          </span>
          <Label className="flex flex-col leading-tight">
            <span className="text-[15px] font-bold tracking-tight">MTA</span>
            <span className="text-2xs font-medium text-muted-foreground">Master Testing Agent</span>
          </Label>
        </Link>

        {/* navigation */}
        <nav className="flex flex-col gap-1" aria-label="Main">
          <span className={groupLabel}>Workspace</span>
          {NAV.map((item) => (
            <NavLink key={item.href} item={item} variant={variant} active={item.href === activeHref}
              badge={item.href === "/runs" ? running : undefined} onNavigate={onNavigate} />
          ))}
        </nav>

        {/* quick actions */}
        <div className="flex flex-col gap-1">
          <span className={groupLabel}>Actions</span>
          <RailTooltip variant={variant} label="New evaluation">
            <Link href="/projects/new" onClick={onNavigate}
              className="flex h-10 items-center gap-3 rounded-xl bg-primary-solid px-3 text-sm font-semibold text-primary-foreground shadow-control transition-[background-color,transform] duration-(--dur-fast) ease-enter hover:bg-primary-solid-hover active:scale-[0.98] rail:justify-center rail:px-0">
              <Plus aria-hidden className="size-[18px] shrink-0" />
              <Label>New evaluation</Label>
            </Link>
          </RailTooltip>
          {quick.map((q) => (
            <RailTooltip key={q.label} variant={variant} label={q.label} hint={q.kbd}>
              <button type="button" onClick={q.onClick}
                className="flex h-10 items-center gap-3 rounded-xl px-3 text-sm font-medium text-muted-foreground transition-colors duration-(--dur-micro) hover:bg-muted/60 hover:text-foreground rail:justify-center rail:px-0">
                <q.icon aria-hidden className="size-[18px] shrink-0" />
                <Label className="flex-1 text-left">{q.label}</Label>
                <span className="kbd rail:hidden">{q.kbd}</span>
              </button>
            </RailTooltip>
          ))}
        </div>

        {/* preferences + profile */}
        <div className="mt-auto flex flex-col gap-1">
          <ThemeSwitch variant={variant} />
          <NavLink item={SETTINGS_NAV} variant={variant} active={activeHref === SETTINGS_NAV.href} onNavigate={onNavigate} />
          <DropdownMenu>
            <DropdownMenuTrigger aria-label="Account"
              className="flex items-center gap-3 rounded-xl border border-border bg-muted/30 p-2 text-left transition-colors duration-(--dur-micro) hover:bg-muted/60 rail:justify-center rail:border-transparent rail:bg-transparent">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet to-primary-solid text-xs font-bold text-white">
                {initials(user)}
              </span>
              <Label className="flex min-w-0 flex-1 flex-col leading-tight">
                <span className="truncate text-sm font-medium">{user.name ?? user.email.split("@")[0]}</span>
                <span className="truncate text-2xs text-muted-foreground">{user.email}</span>
              </Label>
            </DropdownMenuTrigger>
            <DropdownMenuContent side="right" align="end" className="w-56 rounded-xl">
              <DropdownMenuLabel className="font-normal">
                <p className="text-sm font-medium text-foreground">{user.name ?? user.email}</p>
                <p className="truncate text-xs text-muted-foreground">{user.email}</p>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => logout()} className="gap-2"><LogOut className="size-3.5" /> Log out</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </IndicatorGroup>
  );
}

/** Floating, collapsible desktop sidebar (md+) and slide-in drawer (phones). */
export function Sidebar({ user }: { user: CurrentUser }) {
  const { sidebarCollapsed, toggleSidebar, mobileNavOpen, setMobileNavOpen } = useUIStore();
  return (
    <>
      <aside
        data-slot="desktop-sidebar"
        aria-label="Sidebar"
        className="glass fixed inset-y-3 left-3 z-(--z-sidebar) hidden w-(--sidebar-w) rounded-2xl shadow-popover md:block"
      >
        <div className="h-full overflow-x-hidden overflow-y-auto">
          <SidebarBody user={user} variant="desktop" />
        </div>
        <button
          type="button"
          onClick={toggleSidebar}
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!sidebarCollapsed}
          className="absolute top-[4.25rem] -right-3 flex size-6 items-center justify-center rounded-full border border-border bg-popover text-muted-foreground shadow-control transition-colors duration-(--dur-micro) hover:text-foreground"
        >
          <ChevronLeft aria-hidden className="size-3.5 transition-transform duration-(--dur-panel) ease-enter rail:rotate-180" />
        </button>
      </aside>

      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent
          side="left"
          className="gap-0 bg-popover/95 p-0 backdrop-blur-xl data-[side=left]:inset-y-2 data-[side=left]:left-2 data-[side=left]:h-auto data-[side=left]:w-[272px] data-[side=left]:max-w-[calc(100vw-1rem)] data-[side=left]:rounded-2xl data-[side=left]:border md:hidden"
        >
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <SheetDescription className="sr-only">Pages, quick actions and your account</SheetDescription>
          <div className="h-full overflow-y-auto">
            <SidebarBody user={user} variant="drawer" onNavigate={() => setMobileNavOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
