"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import type { RunEvent } from "@/lib/types";

const LEVEL_STYLE: Record<RunEvent["level"], string> = {
  info: "text-muted-foreground",
  success: "text-success",
  warning: "text-warning-foreground dark:text-warning",
  error: "text-critical",
};

/** Real activity log from RunEvent rows; sticks to the bottom while new lines arrive. */
export function ActivityLog({ events, live }: { events: RunEvent[]; live: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);

  useEffect(() => {
    const el = ref.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  return (
    <div
      ref={ref}
      onScroll={(e) => {
        const el = e.currentTarget;
        pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
      }}
      className="h-72 overflow-y-auto rounded-lg border border-border bg-muted/40 p-3 font-mono text-xs leading-relaxed"
    >
      {events.length === 0 ? (
        <p className="text-muted-foreground">Waiting for the evaluation service to pick up this run…</p>
      ) : (
        events.map((e) => (
          <div key={e.id} className="flex gap-2">
            <span className="shrink-0 tabular-nums text-muted-foreground/70">
              {new Date(e.createdAt).toLocaleTimeString([], { hour12: false })}
            </span>
            <span className={cn("whitespace-pre-wrap break-words", LEVEL_STYLE[e.level] ?? LEVEL_STYLE.info)}>
              {e.message}
            </span>
          </div>
        ))
      )}
      {live && <div className="mt-1 animate-pulse text-primary">▍</div>}
    </div>
  );
}
