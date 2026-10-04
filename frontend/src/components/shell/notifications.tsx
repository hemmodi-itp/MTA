"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { Ban, Bell, CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { listItem, stagger } from "@/lib/motion";
import { isActiveStatus, useRuns } from "@/lib/query/hooks";
import { scoreOf } from "@/lib/insights";
import { useUIStore } from "@/lib/stores/ui-store";
import type { Run } from "@/lib/types";

// before you ever open the panel, only the 3 days before this page load count as new
const FIRST_VISIT_CUTOFF = new Date(Date.now() - 3 * 86_400_000).toISOString();

export function timeAgo(iso: string) {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const h = Math.round(mins / 60);
  return h < 24 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
}

interface Note { id: string; run: Run; at: string; title: string; body: string; tone: "ok" | "bad" | "live" | "muted" }

function toNote(r: Run): Note | null {
  const name = r.projectName.split("/").pop() ?? r.projectName;
  if (isActiveStatus(r.status)) {
    return { id: r.id, run: r, at: r.startedAt, tone: "live", title: `${name} is being evaluated`,
      body: r.cancelRequested ? "Cancelling…" : r.currentStage ? `Now: ${r.currentStage.replace(/_/g, " ")}` : "Queued" };
  }
  if (!r.finishedAt) return null;
  if (r.status === "failed") {
    return { id: r.id, run: r, at: r.finishedAt, tone: "bad", title: `${name} evaluation failed`, body: r.errorMessage?.slice(0, 120) ?? "See the run log" };
  }
  if (r.status === "cancelled") {
    return { id: r.id, run: r, at: r.finishedAt, tone: "muted", title: `${name} evaluation cancelled`, body: r.errorMessage ?? "Cancelled by the user" };
  }
  const score = scoreOf(r);
  const blocks = r.compliance?.gates.filter((g) => g.level === "block").length ?? 0;
  return { id: r.id, run: r, at: r.finishedAt, tone: blocks ? "bad" : "ok",
    title: `${name} evaluated · ${score != null ? `${Math.round(score)}/100` : "not scored"}`,
    body: blocks ? `${blocks} blocking gate${blocks > 1 ? "s" : ""}` : "Report ready" };
}

/** Notification center: run lifecycle events from your evaluations, newest first, unread since you last looked. */
export function Notifications() {
  const runs = useRuns();
  const { notificationsSeenAt, markNotificationsSeen } = useUIStore();
  const [open, setOpen] = useState(false);
  const notes = useMemo(() => (runs.data ?? []).map(toNote).filter((n): n is Note => !!n)
    .sort((a, b) => b.at.localeCompare(a.at)).slice(0, 12), [runs.data]);
  const since = notificationsSeenAt ?? FIRST_VISIT_CUTOFF;
  const unread = notes.filter((n) => n.tone === "live" || n.at > since).length;

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) markNotificationsSeen(); }}>
      <PopoverTrigger className="relative flex size-9 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground"
        aria-label={`Notifications${unread ? `, ${unread} new` : ""}`}>
        <motion.span animate={unread ? { rotate: [0, -12, 10, -6, 0] } : {}} transition={{ duration: 0.6, repeat: unread ? Infinity : 0, repeatDelay: 6 }}>
          <Bell className="size-[18px]" />
        </motion.span>
        <AnimatePresence>
          {unread > 0 && (
            <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }}
              className="absolute right-1 top-1 flex min-w-4 items-center justify-center rounded-full bg-critical px-1 text-[10px] font-bold leading-4 text-white">
              {unread}
            </motion.span>
          )}
        </AnimatePresence>
      </PopoverTrigger>
      <PopoverContent className="w-[360px]">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <p className="text-sm font-semibold">Notifications</p>
          <span className="text-xs text-muted-foreground">{unread ? `${unread} new` : "All caught up"}</span>
        </div>
        {notes.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-4 py-10 text-center text-sm text-muted-foreground">
            <CircleDashed className="size-6" /> No evaluations yet
          </div>
        ) : (
          <motion.ul variants={stagger(0.04)} initial="hidden" animate="show" className="max-h-[420px] overflow-y-auto p-1.5">
            {notes.map((n) => {
              const fresh = n.tone === "live" || n.at > since;
              const Icon = n.tone === "live" ? Loader2 : n.tone === "bad" ? XCircle : n.tone === "muted" ? Ban : CheckCircle2;
              return (
                <motion.li key={n.id + n.at} variants={listItem}>
                  <Link href={`/runs/${n.run.id}`} onClick={() => setOpen(false)}
                    className="flex gap-3 rounded-xl px-2.5 py-2.5 transition-colors hover:bg-muted/60">
                    <span className={cn("mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg",
                      n.tone === "ok" && "bg-success/15 text-success", n.tone === "bad" && "bg-critical/15 text-critical",
                      n.tone === "live" && "bg-primary/15 text-primary", n.tone === "muted" && "bg-muted text-muted-foreground")}>
                      <Icon className={cn("size-4", n.tone === "live" && "animate-spin")} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium">{n.title}</span>
                        {fresh && <span className="size-1.5 shrink-0 rounded-full bg-primary" />}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">{n.body}</span>
                      <span className="text-[11px] text-muted-foreground/70">{timeAgo(n.at)}</span>
                    </span>
                  </Link>
                </motion.li>
              );
            })}
          </motion.ul>
        )}
      </PopoverContent>
    </Popover>
  );
}
