"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { KpiCard } from "@/components/shared/kpi-card";
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
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Execution progress</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progressPct}%` }} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <ExecutionStepper currentStage={data.currentStage as PipelineStage | null} isComplete={false} />
            <LiveLogStream currentStage={data.currentStage} />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Scenarios found" value={data.stats.scenariosFound} />
        <KpiCard label="Test cases" value={data.stats.testCasesGenerated} />
        <KpiCard label="Passed" value={data.stats.passed} tone="good" />
        <KpiCard label="Failed" value={data.stats.failed} tone={data.stats.failed > 0 ? "bad" : "default"} sub={`${data.stats.criticalDefects} critical`} />
        <KpiCard label="Healed" value={data.stats.healed} sub={`${Math.round((data.stats.healed / (data.stats.passed + data.stats.failed || 1)) * 100)}% of executed`} />
        <KpiCard label="Coverage" value={`${data.stats.coveragePct}%`} />
        <KpiCard label="Duplicates rejected" value={data.stats.duplicatesRejected} />
        <KpiCard label="Duration" value={data.durationSec ? `${Math.floor(data.durationSec / 60)}m ${data.durationSec % 60}s` : "—"} />
      </div>

      <QualityScoreCard
        score={scoreOf(data)}
        breakdown={data.qualityBreakdown}
        healingPenalty={4}
        riskLevel={data.stats.riskLevel}
        criticalDefects={data.stats.criticalDefects}
      />

      {data.stats.failed > 0 && (
        <Card className="border-critical/40 bg-critical/5">
          <CardContent className="flex items-center justify-between">
            <p className="text-sm">
              <span className="font-medium">{data.stats.criticalDefects} critical failure(s)</span> need review before this
              is production-ready.
            </p>
            <Button asChild size="sm" variant="outline">
              <Link href="/test-cases">View failed tests</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Business scenarios discovered</CardTitle>
        </CardHeader>
        <CardContent>
          <Accordion type="single" collapsible className="w-full">
            {(scenarios.data ?? []).map((s) => (
              <AccordionItem key={s.id} value={s.id}>
                <AccordionTrigger className="text-sm">
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
        </CardContent>
      </Card>

      <div>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Test cases</h2>
        <TestResultTable data={testCases.data ?? []} />
      </div>

      <div>
        <h2 className="mb-2 flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
          Recommendations
          <Link href="/reports" className="ml-auto flex items-center gap-0.5 text-xs text-primary hover:underline">
            Full report <ChevronRight className="size-3" />
          </Link>
        </h2>
        <div className="space-y-2">
          {(recommendations.data ?? []).map((r) => (
            <RecommendationCard key={r.id} recommendation={r} />
          ))}
        </div>
      </div>
    </>
  );
}
