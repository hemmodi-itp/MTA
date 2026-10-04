"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { PipelineStage } from "@/lib/types";

// Canned lines for the legacy Playwright pipeline only — agent evaluations use ActivityLog (real RunEvent rows).
const STAGE_LOG_LINES: Partial<Record<PipelineStage, string[]>> = {
  discovery: ["Starting DOM scan…", "Element scan complete — 61 elements found", "24 business scenarios discovered"],
  testdata: ["Generating 10-variant test data taxonomy…", "coverage_pct=73% — within target"],
  semantic_map: ["Mapping scenarios to DOM elements…", "Clustered 6 functional groups"],
  script_generation: ["Rendering .spec.ts files…", "142 test cases generated"],
  ui_execution: ["Running: npx playwright test --project=chromium", "134 passed, 8 failed"],
  healing: ["HealingAgent: analyzing 8 failures…", "3 fixed, 5 mark_not_healable"],
  reporting: ["Aggregating results…", "Report written to reports/html/"],
};

export function LiveLogStream({ currentStage }: { currentStage: PipelineStage | null }) {
  // Adjust state during render when the prop changes (React's documented alternative
  // to calling setState from inside an effect) — see react.dev "Adjusting state when a prop changes".
  const [prevStage, setPrevStage] = useState<PipelineStage | null>(null);
  const [stagesSeen, setStagesSeen] = useState<PipelineStage[]>([]);

  if (currentStage !== prevStage) {
    setPrevStage(currentStage);
    if (currentStage) setStagesSeen((seen) => [...seen, currentStage]);
  }

  const lines = useMemo(
    () => stagesSeen.flatMap((stage) => [`▶ ${stage}`, ...(STAGE_LOG_LINES[stage] ?? [])]),
    [stagesSeen]
  );

  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  return (
    <ScrollArea className="h-[280px] rounded-lg border border-border bg-muted/30">
      <div className="space-y-1 p-4 font-mono text-xs text-muted-foreground">
        {lines.length === 0 && <p>Waiting for the run to start…</p>}
        {lines.map((line, i) => (
          <p key={i} className={line.startsWith("▶") ? "font-semibold text-foreground" : ""}>
            {line}
          </p>
        ))}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
