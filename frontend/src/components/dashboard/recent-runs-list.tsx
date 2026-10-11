"use client";

import Link from "next/link";
import { m } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { MotionCard } from "@/components/motion/motion-card";
import { IndeterminateBar } from "@/components/motion/progress-bar";
import { itemMotion } from "@/components/motion/stagger";
import { StatusPill } from "@/components/shared/status-pill";
import { ScoreBar } from "@/components/shared/score";
import { timeAgo } from "@/components/shell/notifications";
import { stagger } from "@/lib/motion";
import { isActive, scoreOf } from "@/lib/insights";
import type { Run } from "@/lib/types";

/** One project's runs, newest first: status, score (or a live bar while it runs), tests and when. */
export function RecentRunsList({ runs }: { runs: Run[] }) {
  return (
    <MotionCard interactive={false} className="overflow-hidden">
      <m.ul variants={stagger()} initial="hidden" animate="show" className="divide-y divide-border/70">
        {runs.map((run, i) => {
          const score = scoreOf(run);
          return (
            <m.li key={run.id} {...itemMotion(i)}>
              <Link href={`/runs/${run.id}`}
                className="group grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-2 px-5 py-3.5 text-sm transition-colors duration-(--dur-micro) hover:bg-muted/40 sm:grid-cols-[8rem_minmax(0,1fr)_6rem_9rem_1rem]">
                <StatusPill status={run.status} className="justify-self-start" />
                <div className="col-span-2 min-w-0 sm:col-span-1">
                  {isActive(run) ? (
                    <IndeterminateBar label="Evaluation in progress" />
                  ) : score != null ? (
                    <ScoreBar score={score} animateOnMount={i < 20} />
                  ) : (
                    <span className="text-muted-foreground">{run.status === "completed" ? "Not scored" : "—"}</span>
                  )}
                </div>
                <span className="hidden text-right text-xs tabular-nums sm:block" title="passed / failed / other">
                  <span className="text-success-fg">{run.stats.passed}</span>
                  <span className="text-muted-foreground"> / </span>
                  <span className="text-critical-fg">{run.stats.failed}</span>
                  <span className="text-muted-foreground"> / {run.stats.skipped}</span>
                </span>
                <span className="row-start-1 text-right text-xs whitespace-nowrap text-muted-foreground sm:row-auto" title={new Date(run.startedAt).toLocaleString()}>
                  <span className="mr-2 font-mono">{run.commitRef?.slice(0, 7) ?? ""}</span>
                  {timeAgo(run.startedAt)}
                </span>
                <ChevronRight aria-hidden className="hidden size-4 text-muted-foreground transition-transform duration-(--dur-micro) group-hover:translate-x-0.5 sm:block" />
              </Link>
            </m.li>
          );
        })}
      </m.ul>
    </MotionCard>
  );
}
