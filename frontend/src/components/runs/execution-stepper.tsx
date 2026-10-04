import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PipelineStage } from "@/lib/types";
import { PIPELINE_STAGES } from "@/lib/mock-data";

type LegacyStage = (typeof PIPELINE_STAGES)[number];

const STAGE_LABEL: Record<LegacyStage, string> = {
  discovery: "Discovery",
  testdata: "Test Data",
  semantic_map: "Semantic Map",
  script_generation: "Script Generation",
  ui_execution: "UI Execution",
  healing: "Healing",
  reporting: "Reporting",
};

export function ExecutionStepper({ currentStage, isComplete }: { currentStage: PipelineStage | null; isComplete: boolean }) {
  const currentIndex = currentStage ? PIPELINE_STAGES.indexOf(currentStage as LegacyStage) : -1;

  return (
    <ol className="space-y-1">
      {PIPELINE_STAGES.map((stage, i) => {
        const done = isComplete || i < currentIndex || (i === currentIndex && isComplete);
        const active = !isComplete && i === currentIndex;
        const pending = !done && !active;

        return (
          <li key={stage} className="flex items-center gap-3 py-1.5 text-sm">
            <span
              className={cn(
                "flex size-5 shrink-0 items-center justify-center rounded-full border text-[10px]",
                done && "border-success bg-success text-success-foreground",
                active && "border-primary bg-primary/15 text-primary",
                pending && "border-border text-muted-foreground"
              )}
            >
              {done ? <Check className="size-3" /> : active ? <span className="size-1.5 rounded-full bg-primary" /> : null}
            </span>
            <span className={cn(pending && "text-muted-foreground")}>{STAGE_LABEL[stage]}</span>
          </li>
        );
      })}
    </ol>
  );
}
