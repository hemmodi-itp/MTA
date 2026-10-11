"use client";

import Link from "next/link";
import { AnimatePresence, m } from "framer-motion";
import { Activity } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";
import { transition } from "@/lib/motion";
import { useActivity } from "@/lib/query/hooks";
import { timeAgo } from "@/components/shell/notifications";
import { shortName } from "@/lib/insights";

const DOT: Record<string, string> = { success: "bg-success", warning: "bg-warning", error: "bg-critical", info: "bg-primary" };

/** Live, cross-run activity stream (newest first): new events fade and drop in on top. */
export function ActivityTimeline({ limit = 12 }: { limit?: number }) {
  const activity = useActivity();
  const items = (activity.data ?? []).slice(0, limit);
  if (activity.isLoading) {
    return (
      <div role="status" className="space-y-4">
        <span className="sr-only">Loading activity…</span>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex gap-3">
            <Skeleton className="mt-1 size-[11px] shrink-0 rounded-full" />
            <div className="flex-1 space-y-1.5"><Skeleton className="h-3.5 w-full" /><Skeleton className="h-3 w-1/2" /></div>
          </div>
        ))}
      </div>
    );
  }
  if (!items.length) {
    return <EmptyState size="inline" icon={Activity} title="No activity yet" description="Pipeline events appear here as evaluations run." />;
  }
  return (
    <ol className="relative space-y-3 before:absolute before:inset-y-1 before:left-[5px] before:w-px before:bg-border">
      <AnimatePresence initial={false}>
        {items.map((e) => (
          <m.li key={e.id} initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, transition: transition.exit }}
            transition={transition.enter} className="relative pl-6">
            <span aria-hidden className={cn("absolute top-1.5 left-0 size-[11px] rounded-full ring-4 ring-card", DOT[e.level] ?? "bg-primary")} />
            <Link href={`/runs/${e.runId}`} className="group block rounded-sm">
              <p className="line-clamp-2 text-[13px] leading-snug transition-colors duration-(--dur-micro) group-hover:text-info-fg">{e.message}</p>
              <p className="mt-0.5 text-2xs text-muted-foreground">
                {shortName(e.projectName)}{e.stage ? ` · ${e.stage.replace(/_/g, " ")}` : ""} · {timeAgo(e.createdAt)}
              </p>
            </Link>
          </m.li>
        ))}
      </AnimatePresence>
    </ol>
  );
}
