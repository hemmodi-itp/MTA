"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ExternalLink, GitBranch, History, KeyRound, Loader2, Plus, RotateCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StatusPill } from "@/components/shared/status-pill";
import { RecentRunsList } from "@/components/dashboard/recent-runs-list";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { KpiCard } from "@/components/shared/kpi-card";
import { PageHeader, PageHeaderSkeleton } from "@/components/shared/page-header";
import { KpiRowSkeleton, TableSkeleton } from "@/components/shared/skeletons";
import { MotionCard } from "@/components/motion/motion-card";
import { Stagger } from "@/components/motion/stagger";
import { timeAgo } from "@/components/shell/notifications";
import { band, scoreOf, shortName } from "@/lib/insights";
import { BAND_TONE } from "@/lib/status";
import { isActiveStatus, useDeleteLiveAuth, useProject, useRerunProject, useRuns } from "@/lib/query/hooks";
import type { Project, SubmissionMode } from "@/lib/types";

const MODE: Record<SubmissionMode, string> = { brd_and_live: "BRD + live agent", live_only: "Live agent · BRD generated", brd_only: "BRD only · static review" };

export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const project = useProject(id);
  const runs = useRuns();
  const rerun = useRerunProject();

  if (project.isLoading) {
    return (
      <>
        <PageHeaderSkeleton meta actions />
        <KpiRowSkeleton count={4} dense className="grid grid-cols-2 gap-3 lg:grid-cols-4" />
        <TableSkeleton rows={5} label="Loading the project…" />
      </>
    );
  }
  if (project.isError || !project.data) {
    return <ErrorState title="Project not found" message="It may have been removed, or it belongs to another account." onRetry={project.refetch} />;
  }

  const p = project.data;
  const projectRuns = (runs.data ?? []).filter((r) => r.projectId === id);
  // newest completed run's score; "—" when it was not scored (never a 0 standing in for "no score")
  const latestCompleted = projectRuns.find((r) => r.status === "completed");
  const latestScore = latestCompleted ? scoreOf(latestCompleted) : p.lastQualityScore;
  const running = projectRuns.some((r) => isActiveStatus(r.status));

  async function onRerun() {
    try {
      const result = await rerun.mutateAsync(p.id);
      router.push(`/runs/${result.runId}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not start a new run");
    }
  }

  return (
    <>
      <PageHeader
        breadcrumb={[{ label: "Projects", href: "/projects" }, { label: shortName(p.name) }]}
        title={p.name}
        adornment={<StatusPill status={p.lastRunStatus} />}
        meta={
          <>
            <a href={p.githubUrl} target="_blank" rel="noreferrer" className="inline-flex min-w-0 items-center gap-1 rounded-sm transition-colors duration-(--dur-micro) hover:text-foreground">
              <span className="truncate">{p.githubUrl.replace(/^https?:\/\//, "")}</span> <ExternalLink aria-hidden className="size-3 shrink-0" />
            </a>
            <Badge variant="secondary" className="font-normal">{MODE[p.mode] ?? p.mode}</Badge>
            {p.isSample && <Badge variant="outline" className="font-normal">Sample project</Badge>}
          </>
        }
        actions={
          <>
            {!p.isSample && p.mode && !running && (
              <Button variant="outline" className="gap-1.5" onClick={onRerun} disabled={rerun.isPending}>
                {rerun.isPending ? <Loader2 aria-hidden className="size-3.5 animate-spin" /> : <RotateCw aria-hidden className="size-3.5" />}
                Re-run
              </Button>
            )}
            <Button asChild className="gap-1.5">
              <Link href="/projects/new"><Plus aria-hidden /> New evaluation</Link>
            </Button>
          </>
        }
      />

      <Stagger className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard size="sm" label="Latest score" value={latestScore != null ? Math.round(latestScore) : "—"}
          valueTone={latestScore != null ? BAND_TONE[band(latestScore)] : undefined}
          sub={latestCompleted && latestScore == null ? "latest run was not scored" : "out of 100, latest completed run"} />
        <KpiCard size="sm" label="Runs" value={projectRuns.length} sub={running ? "one is running now" : "all evaluations of this repo"} />
        <KpiCard size="sm" label="Last run" value={projectRuns[0] ? timeAgo(projectRuns[0].startedAt) : "—"} sub={projectRuns[0] ? new Date(projectRuns[0].startedAt).toLocaleDateString() : undefined} />
        <KpiCard size="sm" label="Branch" value={<span className="inline-flex items-center gap-1.5"><GitBranch aria-hidden className="size-5 text-muted-foreground" />{p.branch}</span>} />
      </Stagger>

      {!p.isSample && p.mode !== "brd_only" && <LiveLoginCard project={p} />}

      <section className="space-y-3">
        <h2 className="type-section-title">Run history</h2>
        {runs.isLoading ? (
          <TableSkeleton rows={4} label="Loading runs…" />
        ) : projectRuns.length ? (
          <RecentRunsList runs={projectRuns} />
        ) : (
          <EmptyState icon={History} title="No runs yet" description="Start an evaluation of this repository to see its results here."
            actionLabel="New evaluation" actionHref="/projects/new" />
        )}
      </section>
    </>
  );
}

/** The stored live-app test account: present or not, and a way for the owner to remove it. Never shows the login itself. */
function LiveLoginCard({ project }: { project: Project }) {
  const remove = useDeleteLiveAuth();
  const [open, setOpen] = useState(false);

  async function onRemove() {
    try {
      await remove.mutateAsync(project.id);
      toast.success("Test login removed", { description: "Later runs test the live app without signing in." });
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not remove the test login.");
    }
  }

  return (
    <MotionCard interactive={false} className="flex flex-wrap items-center gap-3 p-5">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-muted text-muted-foreground">
        <KeyRound aria-hidden className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">Live-app test login</p>
        <p className="text-xs text-pretty text-muted-foreground">
          {project.hasLiveAuth
            ? "A test account is stored encrypted and used only by the evaluation service. It is never shown again."
            : "None stored. To add one, submit this repository again from New evaluation with the login filled in."}
        </p>
      </div>
      {project.hasLiveAuth && (
        <Dialog open={open} onOpenChange={setOpen}>
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setOpen(true)}>
            <Trash2 aria-hidden className="size-3.5" /> Remove
          </Button>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Remove the stored test login?</DialogTitle>
              <DialogDescription>
                MTA deletes the encrypted credentials for {project.name}. Later runs can&apos;t sign in to the live app,
                so pages behind the login won&apos;t be tested. A run already in progress keeps the login it started with.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline">Keep it</Button>
              </DialogClose>
              <Button variant="destructive" onClick={onRemove} disabled={remove.isPending} className="gap-1.5">
                {remove.isPending && <Loader2 aria-hidden className="size-3.5 animate-spin" />} Remove login
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </MotionCard>
  );
}
