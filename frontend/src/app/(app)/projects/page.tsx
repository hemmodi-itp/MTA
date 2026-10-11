"use client";

import Link from "next/link";
import { FolderGit2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StatusPill } from "@/components/shared/status-pill";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { ScoreBadge } from "@/components/shared/score";
import { CardGridSkeleton } from "@/components/shared/skeletons";
import { MotionCard } from "@/components/motion/motion-card";
import { Stagger } from "@/components/motion/stagger";
import { timeAgo } from "@/components/shell/notifications";
import { animatesAt } from "@/lib/motion";
import { useProjects } from "@/lib/query/hooks";
import type { SubmissionMode } from "@/lib/types";

const MODE: Record<SubmissionMode, string> = { brd_and_live: "BRD + live", live_only: "Live only", brd_only: "BRD only" };

export default function ProjectsPage() {
  const { data, isLoading, isError, refetch } = useProjects();

  return (
    <>
      <PageHeader
        title="Projects"
        description="Every repository you evaluate, with the result of its latest run."
        actions={
          <Button asChild size="lg" className="gap-1.5">
            <Link href="/projects/new"><Plus aria-hidden /> New evaluation</Link>
          </Button>
        }
      />

      {isError ? (
        <ErrorState onRetry={refetch} />
      ) : isLoading ? (
        <CardGridSkeleton count={6} label="Loading projects…" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" />
      ) : !data?.length ? (
        <EmptyState icon={FolderGit2} title="No projects yet" description="Submit a public GitHub repository to run its first evaluation."
          actionLabel="New evaluation" actionHref="/projects/new" />
      ) : (
        <Stagger className="grid gap-4 *:min-w-0 sm:grid-cols-2 xl:grid-cols-3">
          {data.map((p, i) => {
            const [owner, repo] = p.name.includes("/") ? [p.name.split("/").slice(0, -1).join("/"), p.name.split("/").pop()!] : ["", p.name];
            return (
              <Link key={p.id} href={`/projects/${p.id}`} className="group block rounded-2xl">
                <MotionCard initial={animatesAt(i) ? undefined : false} className="flex h-full flex-col gap-4 p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground transition-colors duration-(--dur-micro) group-hover:text-info-fg">
                        <FolderGit2 aria-hidden className="size-4" />
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate font-semibold transition-colors duration-(--dur-micro) group-hover:text-info-fg">{repo}</span>
                        {owner && <span className="block truncate text-xs text-muted-foreground">{owner}</span>}
                      </span>
                    </div>
                    <StatusPill status={p.lastRunStatus} className="shrink-0" />
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge variant="secondary" className="font-normal">{MODE[p.mode] ?? p.mode}</Badge>
                    {p.isSample && <Badge variant="outline" className="font-normal">Sample</Badge>}
                  </div>
                  <div className="mt-auto flex items-end justify-between gap-3 border-t border-border/70 pt-3">
                    <span className="text-xs text-muted-foreground">Updated {timeAgo(p.updatedAt)}</span>
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      Latest score <ScoreBadge score={p.lastQualityScore} />
                    </span>
                  </div>
                </MotionCard>
              </Link>
            );
          })}
        </Stagger>
      )}
    </>
  );
}
