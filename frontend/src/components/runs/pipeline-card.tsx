"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { MotionCard } from "@/components/motion/motion-card";
import { ProgressBar } from "@/components/motion/progress-bar";
import { Collapse } from "@/components/motion/collapse";
import { LiveDot } from "@/components/motion/live-dot";
import { PipelineSteps } from "@/components/runs/pipeline-steps";
import { PipelineTiming } from "@/components/runs/pipeline-timing";
import { ActivityLog } from "@/components/runs/activity-log";
import { cn } from "@/lib/utils";
import { STEP_STATUS, SEMANTIC_TONE } from "@/lib/status";
import type { RunProgress } from "@/lib/types";

const SEGMENT: Record<string, string> = {
  success: "bg-success", warning: "bg-warning", critical: "bg-critical", info: "bg-primary", neutral: "bg-muted-foreground/30",
};

/**
 * The pipeline: progress, the step timeline and the live log. Open while the run is live or after it failed (that is
 * where the attention is); a finished run shows a one-line summary with a step strip and opens on request.
 */
export function PipelineCard({ progress, active, failed }: { progress: RunProgress; active: boolean; failed: boolean }) {
  const steps = progress.steps;
  const [open, setOpen] = useState(active || failed);
  const done = steps.filter((s) => s.status === "success" || s.status === "skipped").length;
  const pct = steps.length ? Math.round((done / steps.length) * 100) : 0;
  const running = steps.find((s) => s.status === "running");
  const counts = {
    success: steps.filter((s) => s.status === "success").length,
    failed: steps.filter((s) => s.status === "failed").length,
    skipped: steps.filter((s) => s.status === "skipped").length,
  };

  return (
    <MotionCard interactive={false} className="flex min-w-0 flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 pt-5">
        <h2 className="flex items-center gap-2 type-section-title">
          {active && <LiveDot />}
          Pipeline
          {active && running && <span className="font-normal text-muted-foreground">· {running.label}</span>}
        </h2>
        <div className="ml-auto flex items-center gap-4">
          <PipelineTiming progress={progress} active={active} />
          {active && <span className="text-xs font-semibold tabular-nums text-info-fg">{pct}%</span>}
          {!active && steps.length > 0 && (
            <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
              className="inline-flex items-center gap-1 rounded-md text-xs font-medium text-muted-foreground transition-colors duration-(--dur-micro) hover:text-foreground">
              {open ? "Hide steps" : "Show steps"}
              <ChevronDown aria-hidden className={cn("size-3.5 transition-transform duration-(--dur-micro) ease-enter", open && "rotate-180")} />
            </button>
          )}
        </div>
      </div>

      <div className="space-y-4 p-5 pt-4">
        {active ? (
          <ProgressBar value={Math.max(pct, 3)} live label="Evaluation progress" />
        ) : (
          steps.length > 0 && (
            <div className="space-y-2">
              {/* one segment per step, in order: the run at a glance */}
              <div className="flex h-1.5 gap-0.5 overflow-hidden rounded-full" role="img"
                aria-label={`${counts.success} steps done, ${counts.failed} failed, ${counts.skipped} skipped of ${steps.length}`}>
                {steps.map((s) => (
                  <span key={s.key} title={`${s.label}: ${STEP_STATUS[s.status][1]}`}
                    className={cn("flex-1 first:rounded-l-full last:rounded-r-full", SEGMENT[SEMANTIC_TONE[STEP_STATUS[s.status][0]]])} />
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                {counts.success} of {steps.length} steps done
                {counts.failed > 0 && <> · <span className="text-critical-fg">{counts.failed} failed</span></>}
                {counts.skipped > 0 && <> · {counts.skipped} skipped</>}
              </p>
            </div>
          )
        )}

        {steps.length === 0 ? (
          <p className="text-sm text-muted-foreground">Queued. The steps appear as soon as the evaluation service picks up the run.</p>
        ) : (
          <Collapse open={open || active}>
            <div className="grid gap-4 *:min-w-0 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:items-start">
              <PipelineSteps steps={steps} />
              <ActivityLog events={progress.events} live={active} className="h-80 lg:sticky lg:top-20 lg:h-[30rem]" />
            </div>
          </Collapse>
        )}
      </div>
    </MotionCard>
  );
}
