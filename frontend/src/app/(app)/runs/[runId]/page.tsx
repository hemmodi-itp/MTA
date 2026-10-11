"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { Ban, Check, Copy, ExternalLink, GitBranch, Globe, Loader2, RotateCw } from "lucide-react";
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
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader, PageHeaderSkeleton } from "@/components/shared/page-header";
import { RunBodySkeleton } from "@/components/shared/skeletons";
import { StatusPill } from "@/components/shared/status-pill";
import { AgentRunView } from "@/components/runs/agent-run-view";
import { LegacyRunView } from "@/components/runs/legacy-run-view";
import { isActiveStatus, useCancelRun, useRerunProject, useRun } from "@/lib/query/hooks";
import { shortName } from "@/lib/insights";
import type { Run, SubmissionMode } from "@/lib/types";

const MODE_LABEL: Record<SubmissionMode, string> = {
  brd_and_live: "BRD + live agent",
  live_only: "Live agent · BRD generated",
  brd_only: "BRD only · static review",
};

/** The run id, shortened, with a one-click copy of the full id. */
function RunId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Couldn't copy the run id");
    }
  };
  return (
    <button type="button" onClick={copy} title={id} aria-label={`Copy run id ${id}`}
      className="inline-flex items-center gap-1 rounded-md font-mono text-xs transition-colors duration-(--dur-micro) hover:text-foreground">
      Run {id.slice(0, 8)}
      {copied ? <Check aria-hidden className="size-3 text-success-fg" /> : <Copy aria-hidden className="size-3" />}
      <span className="sr-only" aria-live="polite">{copied ? "Copied" : ""}</span>
    </button>
  );
}

export default function RunDetailPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const router = useRouter();
  const run = useRun(runId);
  const rerun = useRerunProject();

  if (run.isLoading) {
    return (
      <>
        <PageHeaderSkeleton meta actions />
        <RunBodySkeleton />
      </>
    );
  }
  if (run.isError || !run.data) {
    return <ErrorState title="Run not found" message="It may have been deleted, or it belongs to another account." onRetry={run.refetch} />;
  }

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
    <>
      <PageHeader
        breadcrumb={[{ label: "Runs", href: "/runs" }, { label: shortName(data.projectName) }]}
        title={data.projectName}
        adornment={<StatusPill status={data.status} />}
        meta={
          <>
            <a href={data.githubUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-sm transition-colors duration-(--dur-micro) hover:text-foreground">
              <GitBranch aria-hidden className="size-3.5" />
              {data.commitRef ? data.commitRef.slice(0, 7) : "repository"}
              <ExternalLink aria-hidden className="size-3" />
            </a>
            {data.liveUrl && (
              <a href={data.liveUrl} target="_blank" rel="noreferrer" className="inline-flex max-w-xs min-w-0 items-center gap-1 rounded-sm transition-colors duration-(--dur-micro) hover:text-foreground">
                <Globe aria-hidden className="size-3.5 shrink-0" />
                <span className="truncate">{data.liveUrl.replace(/^https?:\/\//, "")}</span>
              </a>
            )}
            {data.mode && <Badge variant="secondary" className="font-normal">{MODE_LABEL[data.mode]}</Badge>}
            {data.projectIsSample && <Badge variant="outline" className="font-normal">Sample project</Badge>}
            <RunId id={data.id} />
          </>
        }
        actions={
          <>
            {isActiveStatus(data.status) && !data.projectIsSample && <CancelRunButton run={data} />}
            {isAgentEval && !data.projectIsSample && !isActiveStatus(data.status) && (
              <Button variant="outline" className="gap-1.5" onClick={onRerun} disabled={rerun.isPending}>
                {rerun.isPending ? <Loader2 aria-hidden className="size-3.5 animate-spin" /> : <RotateCw aria-hidden className="size-3.5" />}
                Re-run
              </Button>
            )}
          </>
        }
      />

      {isAgentEval ? <AgentRunView run={data} /> : <LegacyRunView run={data} />}
    </>
  );
}

/** Cancel with a confirm step. Queued runs stop at once; running ones at the service's next checkpoint. */
function CancelRunButton({ run }: { run: Run }) {
  const cancel = useCancelRun();
  const [open, setOpen] = useState(false);

  if (run.cancelRequested) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground" role="status">
        <Loader2 aria-hidden className="size-3.5 animate-spin" /> Cancelling…
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
      <Button variant="outline" className="gap-1.5" onClick={() => setOpen(true)}>
        <Ban aria-hidden className="size-3.5" /> Cancel
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
            {cancel.isPending && <Loader2 aria-hidden className="size-3.5 animate-spin" />} Cancel evaluation
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
