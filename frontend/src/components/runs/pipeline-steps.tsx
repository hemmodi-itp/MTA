"use client";

import { AnimatePresence, m } from "framer-motion";
import { Check, Minus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { transition } from "@/lib/motion";
import { STEP_STATUS, TONE_CLASS, SEMANTIC_TONE } from "@/lib/status";
import type { RunStep, StepStatus } from "@/lib/types";

function elapsed(step: RunStep) {
  if (!step.startedAt) return null;
  const end = step.finishedAt ? new Date(step.finishedAt).getTime() : Date.now();
  const sec = Math.max(0, Math.round((end - new Date(step.startedAt).getTime()) / 1000));
  return sec >= 60 ? `${Math.floor(sec / 60)}m ${sec % 60}s` : `${sec}s`;
}

const toneOf = (status: StepStatus) => SEMANTIC_TONE[STEP_STATUS[status][0]];

/** The step's status circle. A new status swaps in with a quick scale + fade, so a step completing is visible. */
function StepGlyph({ status }: { status: StepStatus }) {
  const done = status === "success" || status === "failed";
  return (
    <span className={cn("relative flex size-6 shrink-0 items-center justify-center", TONE_CLASS[toneOf(status)])}>
      {status === "running" && <span aria-hidden className="absolute inset-0 rounded-full tone-fill opacity-40 animate-pulse-ring" />}
      <AnimatePresence initial={false} mode="popLayout">
        <m.span
          key={status}
          initial={{ scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1, transition: transition.micro }}
          exit={{ scale: 0.6, opacity: 0, transition: transition.exit }}
          className={cn(
            "relative flex size-6 items-center justify-center rounded-full border",
            done && "tone-fill border-transparent text-white dark:text-background",
            status === "running" && "tone-tint tone-border tone-text border-2 bg-card",
            (status === "pending" || status === "skipped") && "border-border bg-card text-muted-foreground"
          )}
        >
          {status === "success" && <Check aria-hidden className="size-3.5" strokeWidth={3} />}
          {status === "failed" && <X aria-hidden className="size-3.5" strokeWidth={3} />}
          {status === "skipped" && <Minus aria-hidden className="size-3.5" />}
          {status === "running" && <span aria-hidden className="size-2 rounded-full tone-fill" />}
        </m.span>
      </AnimatePresence>
    </span>
  );
}

/** Live pipeline timeline driven by RunStep rows written by the Python pipeline; the running step is highlighted. */
export function PipelineSteps({ steps }: { steps: RunStep[] }) {
  return (
    <ol className="relative" aria-label="Pipeline steps">
      {steps.map((step, i) => {
        const time = elapsed(step);
        const running = step.status === "running";
        const quiet = step.status === "pending" || step.status === "skipped";
        return (
          <li
            key={step.key}
            aria-current={running ? "step" : undefined}
            className={cn(
              "relative flex gap-3 rounded-xl px-2 py-2 transition-colors duration-(--dur-panel)",
              running && "bg-primary/[0.06] ring-1 ring-primary/20"
            )}
          >
            {/* connector to the next step */}
            {i < steps.length - 1 && (
              <span aria-hidden className={cn("absolute top-9 bottom-[-4px] left-[19px] w-px",
                step.status === "success" ? "bg-success/40" : "bg-border")} />
            )}
            <StepGlyph status={step.status} />
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex items-baseline justify-between gap-2">
                <span className={cn("text-sm", running ? "font-medium" : quiet && "text-muted-foreground")}>
                  {step.label}
                  <span className="sr-only">: {STEP_STATUS[step.status][1]}</span>
                </span>
                {time && <span className="shrink-0 font-mono text-2xs text-muted-foreground tabular-nums">{time}</span>}
              </div>
              {/* every row keeps a detail line, so a step gaining one doesn't push the page down */}
              <p className={cn("mt-0.5 line-clamp-2 min-h-4 text-xs",
                step.status === "failed" ? "text-critical-fg" : running ? "text-info-fg" : "text-muted-foreground")}>
                {step.detail ?? (step.status === "pending" ? "Waiting" : "")}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
