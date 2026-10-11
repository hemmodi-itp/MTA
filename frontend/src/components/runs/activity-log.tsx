"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { usePrefersReducedMotion } from "@/hooks/use-reduced-motion";
import type { RunEvent } from "@/lib/types";

const LEVEL_STYLE: Record<RunEvent["level"], string> = {
  info: "text-muted-foreground",
  success: "text-success-fg",
  warning: "text-warning-fg",
  error: "text-critical-fg",
};

/** Real activity log from RunEvent rows; sticks to the bottom while new lines arrive, and new lines fade in. */
export function ActivityLog({ events, live, className }: { events: RunEvent[]; live: boolean; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  // lines present on first render appear at once; only lines that arrive later fade in
  const [initialCount] = useState(events.length);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    const el = ref.current;
    if (el && pinned.current) el.scrollTo({ top: el.scrollHeight, behavior: reduced || !live ? "auto" : "smooth" });
  }, [events.length, live, reduced]);

  return (
    <div
      ref={ref}
      role="log"
      aria-label="Activity log"
      aria-live={live ? "polite" : "off"}
      onScroll={(e) => {
        const el = e.currentTarget;
        pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
      }}
      className={cn("overflow-y-auto rounded-xl border border-border bg-muted/40 p-3 font-mono text-xs leading-relaxed", className)}
    >
      {events.length === 0 ? (
        <p className="text-muted-foreground">Waiting for the evaluation service to pick up this run…</p>
      ) : (
        events.map((e, i) => (
          <div key={e.id} className={cn("flex gap-2", i >= initialCount && "animate-in fade-in-0 duration-(--dur-panel) ease-enter")}>
            <span className="shrink-0 text-muted-foreground tabular-nums">
              {new Date(e.createdAt).toLocaleTimeString([], { hour12: false })}
            </span>
            <span className={cn("min-w-0 wrap-anywhere whitespace-pre-wrap", LEVEL_STYLE[e.level] ?? LEVEL_STYLE.info)}>
              {e.message}
            </span>
          </div>
        ))
      )}
      {live && <div aria-hidden className="mt-1 animate-pulse text-primary">▍</div>}
    </div>
  );
}
