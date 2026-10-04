"use client";

import { use, useState } from "react";
import Link from "next/link";
import { ExternalLink, GitBranch, KeyRound, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { ErrorState } from "@/components/shared/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { formatScore, scoreOf } from "@/lib/insights";
import { useDeleteLiveAuth, useProject, useRuns } from "@/lib/query/hooks";
import type { Project } from "@/lib/types";

export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const project = useProject(id);
  const runs = useRuns();

  if (project.isLoading) return <Skeleton className="h-40 rounded-lg" />;
  if (project.isError || !project.data) return <ErrorState message="Project not found." onRetry={project.refetch} />;

  const projectRuns = (runs.data ?? []).filter((r) => r.projectId === id);
  // newest completed run's score; "—" when it was not scored (never a 0 standing in for "no score")
  const latestCompleted = projectRuns.find((r) => r.status === "completed");
  const latestScore = latestCompleted ? scoreOf(latestCompleted) : project.data.lastQualityScore;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">{project.data.name}</h1>
          <a
            href={project.data.githubUrl}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            {project.data.githubUrl} <ExternalLink className="size-3" />
          </a>
        </div>
        <StatusPill status={project.data.lastRunStatus} />
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Card>
          <CardContent className="space-y-1">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Branch</p>
            <p className="flex items-center gap-1.5 font-medium">
              <GitBranch className="size-3.5" /> {project.data.branch}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Latest score</p>
            <p className="font-mono text-xl font-semibold tabular-nums">{formatScore(latestScore)}</p>
            {latestCompleted && latestScore == null && <p className="text-xs text-muted-foreground">Latest run was not scored</p>}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Total runs</p>
            <p className="font-mono text-xl font-semibold tabular-nums">{projectRuns.length}</p>
          </CardContent>
        </Card>
      </div>

      {!project.data.isSample && project.data.mode !== "brd_only" && <LiveLoginCard project={project.data} />}

      <div>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Run history</h2>
        {projectRuns.length ? (
          <RecentRunsList runs={projectRuns} />
        ) : (
          <p className="text-sm text-muted-foreground">
            No runs yet.{" "}
            <Link href="/projects/new" className="text-primary hover:underline">
              Start one
            </Link>
            .
          </p>
        )}
      </div>
    </div>
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
    <Card>
      <CardContent className="flex flex-wrap items-center gap-3">
        <KeyRound className="size-4 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">Live-app test login</p>
          <p className="text-xs text-muted-foreground">
            {project.hasLiveAuth
              ? "A test account is stored encrypted and used only by the evaluation service. It is never shown again."
              : "None stored. To add one, submit this repository again from New evaluation with the login filled in."}
          </p>
        </div>
        {project.hasLiveAuth && (
          <Dialog open={open} onOpenChange={setOpen}>
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setOpen(true)}>
              <Trash2 className="size-3.5" /> Remove
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
                  {remove.isPending && <Loader2 className="size-3.5 animate-spin" />} Remove login
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </CardContent>
    </Card>
  );
}
