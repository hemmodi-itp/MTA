import { Check, Loader2, Minus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RunStep } from "@/lib/types";

function elapsed(step: RunStep) {
  if (!step.startedAt) return null;
  const end = step.finishedAt ? new Date(step.finishedAt).getTime() : Date.now();
  const sec = Math.max(0, Math.round((end - new Date(step.startedAt).getTime()) / 1000));
  return sec >= 60 ? `${Math.floor(sec / 60)}m ${sec % 60}s` : `${sec}s`;
}

/** Live pipeline stepper driven by RunStep rows written by the Python pipeline. */
export function PipelineSteps({ steps }: { steps: RunStep[] }) {
  return (
    <ol className="space-y-1">
      {steps.map((step) => {
        const time = elapsed(step);
        return (
          <li key={step.key} className="flex gap-3 py-1.5 text-sm">
            <span
              className={cn(
                "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border text-[10px]",
                step.status === "success" && "border-success bg-success text-success-foreground",
                step.status === "running" && "border-primary bg-primary/15 text-primary",
                step.status === "failed" && "border-critical bg-critical text-white",
                (step.status === "pending" || step.status === "skipped") && "border-border text-muted-foreground"
              )}
            >
              {step.status === "success" && <Check className="size-3" />}
              {step.status === "running" && <Loader2 className="size-3 animate-spin" />}
              {step.status === "failed" && <X className="size-3" />}
              {step.status === "skipped" && <Minus className="size-3" />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className={cn((step.status === "pending" || step.status === "skipped") && "text-muted-foreground")}>
                  {step.label}
                </span>
                {time && <span className="shrink-0 font-mono text-[11px] tabular-nums text-muted-foreground">{time}</span>}
              </div>
              {step.detail && (
                <p
                  className={cn(
                    "mt-0.5 line-clamp-3 text-xs",
                    step.status === "failed" ? "text-critical" : "text-muted-foreground"
                  )}
                >
                  {step.detail}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
