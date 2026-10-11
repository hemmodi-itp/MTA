"use client";

import Link from "next/link";
import { format } from "date-fns";
import { m } from "framer-motion";
import { ChevronRight, FileBarChart2, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { ScoreBadge } from "@/components/shared/score";
import { TableSkeleton } from "@/components/shared/skeletons";
import { MotionCard } from "@/components/motion/motion-card";
import { itemMotion } from "@/components/motion/stagger";
import { timeAgo } from "@/components/shell/notifications";
import { stagger } from "@/lib/motion";
import { scoreOf } from "@/lib/insights";
import { useRuns } from "@/lib/query/hooks";
import type { SubmissionMode } from "@/lib/types";

const MODE: Record<SubmissionMode, string> = { brd_and_live: "BRD + live", live_only: "Live only", brd_only: "BRD only" };

export default function ReportsPage() {
  const { data, isLoading, isError, refetch } = useRuns();
  const completed = (data ?? []).filter((r) => r.status === "completed");

  return (
    <>
      <PageHeader title="Reports" description="The final report of every completed evaluation, newest first." />

      {isError ? (
        <ErrorState onRetry={refetch} />
      ) : isLoading ? (
        <TableSkeleton rows={6} label="Loading reports…" />
      ) : !completed.length ? (
        <EmptyState icon={FileBarChart2} title="No reports yet" description="A report appears here as soon as an evaluation completes."
          actionLabel="New evaluation" actionHref="/projects/new" />
      ) : (
        <MotionCard interactive={false} className="overflow-hidden">
          <m.ul variants={stagger()} initial="hidden" animate="show" className="divide-y divide-border/70">
            {completed.map((r, i) => {
              const parts = r.projectName.split("/");
              const repo = parts.pop();
              const blocks = (r.compliance?.gates ?? []).filter((g) => g.level === "block").length;
              const s = scoreOf(r);
              return (
                <m.li key={r.id} {...itemMotion(i)}>
                  <Link href={`/reports/${r.id}`}
                    className="group flex items-center gap-4 px-5 py-3.5 text-sm transition-colors duration-(--dur-micro) hover:bg-muted/40">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground transition-colors duration-(--dur-micro) group-hover:text-info-fg">
                      <FileBarChart2 aria-hidden className="size-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium transition-colors duration-(--dur-micro) group-hover:text-info-fg">
                        {repo} {parts.length > 0 && <span className="font-normal text-muted-foreground">· {parts.join("/")}</span>}
                      </p>
                      <p className="text-xs text-muted-foreground" title={new Date(r.startedAt).toLocaleString()}>
                        {format(new Date(r.startedAt), "d MMM yyyy")} · {timeAgo(r.startedAt)}
                      </p>
                    </div>
                    {r.mode && <Badge variant="secondary" className="hidden font-normal sm:inline-flex">{MODE[r.mode]}</Badge>}
                    {blocks > 0 && (
                      <span className="hidden items-center gap-1 text-xs font-medium text-critical-fg sm:inline-flex">
                        <ShieldAlert aria-hidden className="size-3.5" /> {blocks} blocking
                      </span>
                    )}
                    <ScoreBadge score={s} title={s == null ? "Not scored" : "Score"} />
                    <ChevronRight aria-hidden className="size-4 text-muted-foreground transition-transform duration-(--dur-micro) group-hover:translate-x-0.5" />
                  </Link>
                </m.li>
              );
            })}
          </m.ul>
        </MotionCard>
      )}
    </>
  );
}
