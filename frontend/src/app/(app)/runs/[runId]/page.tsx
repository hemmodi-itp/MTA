"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { Ban, ExternalLink, GitBranch, Globe, Loader2, RotateCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ErrorState } from "@/components/shared/error-state";
import { StatusPill } from "@/components/shared/status-pill";
import { AgentRunView } from "@/components/runs/agent-run-view";
import { LegacyRunView } from "@/components/runs/legacy-run-view";
import { isActiveStatus, useCancelRun, useRerunProject, useRun } from "@/lib/query/hooks";
import type { Run, SubmissionMode } from "@/lib/types";

const MODE_LABEL: Record<SubmissionMode, string> = {
  brd_and_live: "BRD + live agent",
  live_only: "Live agent · BRD generated",
  brd_only: "BRD only · static review",
};

export default function RunDetailPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const router = useRouter();
  const run = useRun(runId);
  const rerun = useRerunProject();

  if (run.isLoading) return <Skeleton className="h-96 rounded-lg" />;
  if (run.isError || !run.data) return <ErrorState message="Run not found." onRetry={run.refetch} />;

  const data = run.data;
  const isAgentEval = data.mode !== null;

  async function onRerun() {
    try {
      const result = await rerun.mutateAsync(data.projectId);
      router.push(`/runs/${result.runId}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not start a new run");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1.5">
          <h1 className="text-xl font-semibold">{data.projectName}</h1>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <a href={data.githubUrl} target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-foreground">
              <GitBranch className="size-3.5" />
              {data.commitRef ? data.commitRef.slice(0, 7) : "repository"}
              <ExternalLink className="size-3" />
            </a>
            {data.liveUrl && (
              <a href={data.liveUrl} target="_blank" rel="noreferrer" className="flex max-w-xs items-center gap-1 truncate hover:text-foreground">
                <Globe className="size-3.5 shrink-0" />
                <span className="truncate">{data.liveUrl.replace(/^https?:\/\//, "")}</span>
              </a>
            )}
            {data.mode && <Badge variant="secondary" className="font-normal">{MODE_LABEL[data.mode]}</Badge>}
            {data.projectIsSample && <Badge variant="outline" className="font-normal">Sample project</Badge>}
            <span className="font-mono text-xs">Run {data.id}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill status={data.status} />
          {isActiveStatus(data.status) && !data.projectIsSample && <CancelRunButton run={data} />}
          {isAgentEval && !data.projectIsSample && !isActiveStatus(data.status) && (
            <Button size="sm" variant="outline" className="gap-1.5" onClick={onRerun} disabled={rerun.isPending}>
              {rerun.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <RotateCw className="size-3.5" />}
              Re-run
            </Button>
          )}
        </div>
      </div>

      {isAgentEval ? <AgentRunView run={data} /> : <LegacyRunView run={data} />}
    </div>
  );
}

/** Cancel with a confirm step. Queued runs stop at once; running ones at the service's next checkpoint. */
function CancelRunButton({ run }: { run: Run }) {
  const cancel = useCancelRun();
  const [open, setOpen] = useState(false);

  if (run.cancelRequested) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" /> Cancelling…
      </span>
    );
  }

  async function onConfirm() {
    try {
      const res = await cancel.mutateAsync(run.id);
      toast.success(res.status === "cancelled" ? "Run cancelled" : "Cancellation requested", {
        description: res.status === "cancelled" ? undefined : "The evaluation stops at its next checkpoint, usually within a minute.",
      });
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not cancel the run");
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setOpen(true)}>
        <Ban className="size-3.5" /> Cancel
      </Button>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Cancel this evaluation?</DialogTitle>
          <DialogDescription>
            {run.status === "queued"
              ? "The run hasn't started yet, so it is removed from the queue right away."
              : "MTA stops at the next checkpoint. Results gathered so far stay visible, but the run won't be scored."}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Keep running</Button>
          </DialogClose>
          <Button variant="destructive" className="gap-1.5" onClick={onConfirm} disabled={cancel.isPending}>
            {cancel.isPending && <Loader2 className="size-3.5 animate-spin" />} Cancel evaluation
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
