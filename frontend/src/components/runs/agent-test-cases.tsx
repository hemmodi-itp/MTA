"use client";

import { useState } from "react";
import { FlaskConical } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { StatusPill } from "@/components/shared/status-pill";
import { EmptyState } from "@/components/shared/empty-state";
import { cn } from "@/lib/utils";
import type { TestCase } from "@/lib/types";

type Filter = "all" | "agent_specific" | "general" | "failed" | "inconclusive" | "not_executed";

function scoreTone(score?: number) {
  if (score == null) return "text-muted-foreground";
  if (score >= 70) return "text-success";
  if (score >= 40) return "text-warning-foreground dark:text-warning";
  return "text-critical";
}

/**
 * Generated tests with the prompt sent, expected behaviour, the agent's actual reply and
 * Gemini's verdict. Rows fill in live while the execution step runs.
 */
export function AgentTestCases({ tests }: { tests: TestCase[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const counts = {
    all: tests.length,
    agent_specific: tests.filter((t) => t.category === "agent_specific").length,
    general: tests.filter((t) => t.category === "general").length,
    failed: tests.filter((t) => t.status === "failed").length,
    inconclusive: tests.filter((t) => t.status === "inconclusive").length,
    not_executed: tests.filter((t) => t.status === "not_executed").length,
  };
  const shown = tests.filter((t) =>
    filter === "all" ? true : filter === "agent_specific" || filter === "general" ? t.category === filter : t.status === filter
  );

  if (tests.length === 0) {
    return (
      <EmptyState
        icon={FlaskConical}
        title="No test cases yet"
        description="Gemini generates them from the BRD once the requirements are extracted."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        {(
          [
            ["all", "All"],
            ["agent_specific", "Agent-specific"],
            ["general", "General"],
            ["failed", "Failed"],
            ["inconclusive", "Inconclusive"],
            ["not_executed", "Not executed"],
          ] as [Filter, string][]
        ).filter(([key]) => key === "all" || counts[key] > 0 || key === filter).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
              filter === key ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:bg-muted"
            )}
          >
            {label} <span className="tabular-nums opacity-70">{counts[key]}</span>
          </button>
        ))}
      </div>

      <Accordion type="multiple" className="rounded-lg border border-border">
        {shown.map((t) => (
          <AccordionItem key={t.id} value={t.id} className="px-4">
            <AccordionTrigger className="gap-3 text-sm hover:no-underline">
              <span className="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-left">
                <span className="font-medium">{t.scenarioTitle}</span>
                {t.requirementRef && <Badge variant="outline" className="font-mono font-normal">{t.requirementRef}</Badge>}
                <Badge variant="secondary" className="font-normal">{t.variantType.replace("_", " ")}</Badge>
              </span>
              {t.judgeScore != null && (
                <span className={cn("font-mono text-xs tabular-nums", scoreTone(t.judgeScore))}>{t.judgeScore}</span>
              )}
              <StatusPill status={t.status} />
            </AccordionTrigger>
            <AccordionContent className="space-y-3 pb-4 text-sm">
              {t.brdReference && (
                <Section label="BRD requirement verified">
                  <blockquote className="border-l-2 border-primary/50 pl-3 text-xs italic text-muted-foreground">
                    “{t.brdReference}”
                  </blockquote>
                  {t.acceptanceCriterion && (
                    <p className="mt-1 text-xs"><span className="text-muted-foreground">Acceptance criterion: </span>{t.acceptanceCriterion}</p>
                  )}
                </Section>
              )}
              <Section label="Prompt sent to the agent">
                <p className="whitespace-pre-wrap rounded-md bg-muted px-3 py-2 font-mono text-xs">{t.input}</p>
              </Section>
              {t.expected && <Section label="Expected behaviour">{t.expected}</Section>}
              {(t.status === "inconclusive" || t.status === "not_executed") && t.errorSummary && (
                <Section label={t.status === "inconclusive" ? "Why it is inconclusive" : "Why it was not executed"}>
                  <span className="text-muted-foreground">{t.errorSummary}</span>
                </Section>
              )}
              {t.actualOutput ? (
                <Section label={`Agent reply${t.durationMs ? ` · ${(t.durationMs / 1000).toFixed(1)}s` : ""}`}>
                  <p className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded-md border border-border px-3 py-2 text-xs">
                    {t.actualOutput}
                  </p>
                </Section>
              ) : t.errorSummary && t.status !== "inconclusive" && t.status !== "not_executed" ? (
                <Section label="Execution">
                  <span className="text-muted-foreground">{t.errorSummary}</span>
                </Section>
              ) : null}
              {t.judgeReasoning && (
                <Section label={`Gemini verdict${t.judgeScore != null ? ` · ${t.judgeScore}/100` : ""}`}>
                  <span className={t.status === "failed" ? "text-critical" : undefined}>{t.judgeReasoning}</span>
                </Section>
              )}
            </AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <div>{children}</div>
    </div>
  );
}
