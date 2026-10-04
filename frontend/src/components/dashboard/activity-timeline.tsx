"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { Activity } from "lucide-react";
import { cn } from "@/lib/utils";
import { spring } from "@/lib/motion";
import { useActivity } from "@/lib/query/hooks";
import { timeAgo } from "@/components/shell/notifications";
import { shortName } from "@/lib/insights";

const DOT: Record<string, string> = { success: "bg-success", warning: "bg-warning", error: "bg-critical", info: "bg-primary" };

/** Live, cross-run activity stream (newest first): new lines slide in on top. */
export function ActivityTimeline({ limit = 12 }: { limit?: number }) {
  const activity = useActivity();
  const items = (activity.data ?? []).slice(0, limit);
  if (activity.isLoading) {
    return <div className="space-y-3">{Array.from({ length: 5 }).map((_, i) => <div key={i} className="shimmer h-10 rounded-lg" />)}</div>;
  }
  if (!items.length) {
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-center text-sm text-muted-foreground">
        <Activity className="size-6" /> Activity appears here as evaluations run.
      </div>
    );
  }
  return (
    <ol className="relative space-y-3 before:absolute before:inset-y-1 before:left-[5px] before:w-px before:bg-border">
      <AnimatePresence initial={false}>
        {items.map((e) => (
          <motion.li key={e.id} layout initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={spring.gentle}
            className="relative pl-6">
            <span className={cn("absolute left-0 top-1.5 size-[11px] rounded-full ring-4 ring-background", DOT[e.level] ?? "bg-primary")} />
            <Link href={`/runs/${e.runId}`} className="group block">
              <p className="line-clamp-2 text-[13px] leading-snug group-hover:text-primary">{e.message}</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {shortName(e.projectName)}{e.stage ? ` · ${e.stage.replace(/_/g, " ")}` : ""} · {timeAgo(e.createdAt)}
              </p>
            </Link>
          </motion.li>
        ))}
      </AnimatePresence>
    </ol>
  );
}
