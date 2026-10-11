"use client";

import Link from "next/link";
import { AlertOctagon, ChevronRight, Compass } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { KpiCard } from "@/components/shared/kpi-card";
import { EmptyState } from "@/components/shared/empty-state";
import { Notice } from "@/components/shared/notice";
import { SectionCard } from "@/components/shared/section-card";
import { Stagger, StaggerItem } from "@/components/motion/stagger";
import { ProgressBar } from "@/components/motion/progress-bar";
import { ExecutionStepper } from "@/components/runs/execution-stepper";
import { LiveLogStream } from "@/components/runs/live-log-stream";
import { QualityScoreCard } from "@/components/reports/quality-score-card";
import { RecommendationCard } from "@/components/reports/recommendation-card";
import { TestResultTable } from "@/components/test-cases/test-result-table";
import { useScenarios, useTestCases, useRecommendations } from "@/lib/query/hooks";
import { PIPELINE_STAGES } from "@/lib/mock-data";
import { scoreOf } from "@/lib/insights";
import type { PipelineStage, Run } from "@/lib/types";

/** Run view for Playwright web-app runs (the original pipeline); agent evaluations use AgentRunView. */
export function LegacyRunView({ run: data }: { run: Run }) {
  const scenarios = useScenarios(data.id);
  const testCases = useTestCases(data.id);
  const recommendations = useRecommendations(data.id);

  const isRunning = data.status === "running" || data.status === "queued";
  const stageIndex = data.currentStage ? PIPELINE_STAGES.indexOf(data.currentStage as (typeof PIPELINE_STAGES)[number]) : -1;
  const progressPct = isRunning ? Math.round(((stageIndex + 1) / PIPELINE_STAGES.length) * 100) : 100;

  if (isRunning) {
    return (
      <SectionCard title="Execution progress">
        <div className="space-y-4">
          <ProgressBar value={progressPct} live label="Execution progress" />
          <div className="grid gap-4 sm:grid-cols-2">
            <ExecutionStepper currentStage={data.currentStage as PipelineStage | null} isComplete={false} />
            <LiveLogStream currentStage={data.currentStage} />
          </div>
        </div>
      </SectionCard>
    );
  }

  const executed = data.stats.passed + data.stats.failed || 1;
  return (
    <>
      <Stagger className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StaggerItem><KpiCard size="sm" label="Scenarios found" value={data.stats.scenariosFound} /></StaggerItem>
        <StaggerItem><KpiCard size="sm" label="Test cases" value={data.stats.testCasesGenerated} /></StaggerItem>
        <StaggerItem><KpiCard size="sm" label="Passed" value={data.stats.passed} valueTone="success" /></StaggerItem>
        <StaggerItem>
          <KpiCard size="sm" label="Failed" value={data.stats.failed} valueTone={data.stats.failed > 0 ? "critical" : undefined} sub={`${data.stats.criticalDefects} critical`} />
        </StaggerItem>
        <StaggerItem>
          <KpiCard size="sm" label="Healed" value={data.stats.healed} valueTone={data.stats.healed ? "violet" : undefined}
            sub={`${Math.round((data.stats.healed / executed) * 100)}% of executed`} />
        </StaggerItem>
        <StaggerItem><KpiCard size="sm" label="Coverage" value={data.stats.coveragePct} suffix="%" /></StaggerItem>
        <StaggerItem><KpiCard size="sm" label="Duplicates rejected" value={data.stats.duplicatesRejected} /></StaggerItem>
        <StaggerItem>
          <KpiCard size="sm" label="Duration" value={data.durationSec ? `${Math.floor(data.durationSec / 60)}m ${data.durationSec % 60}s` : "—"} />
        </StaggerItem>
      </Stagger>

      <QualityScoreCard
        score={scoreOf(data)}
        breakdown={data.qualityBreakdown}
        healingPenalty={4}
        riskLevel={data.stats.riskLevel}
        criticalDefects={data.stats.criticalDefects}
      />

      {data.stats.failed > 0 && (
        <Notice tone="critical" icon={AlertOctagon} title={`${data.stats.criticalDefects} critical failure${data.stats.criticalDefects === 1 ? "" : "s"} to review`}>
          They need a look before this build is production-ready.
        </Notice>
      )}

      <SectionCard title="Business scenarios discovered">
        {(scenarios.data ?? []).length ? (
          <Accordion type="single" collapsible className="w-full">
            {(scenarios.data ?? []).map((s) => (
              <AccordionItem key={s.id} value={s.id}>
                <AccordionTrigger className="text-sm hover:no-underline">
                  <span className="flex items-center gap-2">
                    {s.title}
                    <Badge variant="secondary" className="font-normal">{s.module}</Badge>
                  </span>
                </AccordionTrigger>
                <AccordionContent className="text-sm text-muted-foreground">
                  Confidence score: <span className="font-mono">{s.confidence.toFixed(2)}</span>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        ) : (
          <EmptyState size="inline" icon={Compass} title={scenarios.isLoading ? "Loading scenarios…" : "No scenarios recorded"}
            description={scenarios.isLoading ? undefined : "This run didn't store the business scenarios it discovered."} />
        )}
      </SectionCard>

      <section className="space-y-3">
        <h2 className="type-section-title">Test cases</h2>
        <TestResultTable data={testCases.data ?? []} />
      </section>

      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <h2 className="type-section-title">Recommendations</h2>
          <Link href="/reports" className="ml-auto inline-flex items-center gap-0.5 rounded-sm text-xs font-medium text-info-fg hover:underline">
            All reports <ChevronRight aria-hidden className="size-3" />
          </Link>
        </div>
        <Stagger className="space-y-2">
          {(recommendations.data ?? []).map((r, i) => (
            <StaggerItem key={r.id} index={i}><RecommendationCard recommendation={r} /></StaggerItem>
          ))}
        </Stagger>
      </section>
    </>
  );
}
