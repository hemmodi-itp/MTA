"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { AlertTriangle, Ban, Clock, FileText, Loader2, Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { KpiCard } from "@/components/shared/kpi-card";
import { EmptyState } from "@/components/shared/empty-state";
import { QualityScoreCard } from "@/components/reports/quality-score-card";
import { RecommendationCard } from "@/components/reports/recommendation-card";
import { PipelineSteps } from "@/components/runs/pipeline-steps";
import { ActivityLog } from "@/components/runs/activity-log";
import { AgentTestCases } from "@/components/runs/agent-test-cases";
import { RequirementsList } from "@/components/runs/requirements-list";
import { MarkdownLite } from "@/components/runs/markdown-lite";
import { AgentProfileCard } from "@/components/runs/agent-profile-card";
import { ComplianceCard } from "@/components/runs/compliance-card";
import { ComplianceSummary, TraceabilityMatrix } from "@/components/runs/traceability-matrix";
import { FinalReportPanel } from "@/components/runs/final-report-panel";
import { PipelineTiming } from "@/components/runs/pipeline-timing";
import { RunLogs } from "@/components/runs/run-logs";
import { FindingsList } from "@/components/runs/findings-list";
import { LiveAppPanel } from "@/components/runs/live-app-panel";
import { isActiveStatus, useRecommendations, useRunArtifacts, useRunProgress, useTestCases } from "@/lib/query/hooks";
import { stalledMinutes } from "@/lib/run-status";
import { scoreOf } from "@/lib/insights";
import type { Run } from "@/lib/types";

function duration(sec: number | null) {
  if (!sec) return "—";
  return sec >= 60 ? `${Math.floor(sec / 60)}m ${sec % 60}s` : `${sec}s`;
}

/** Live + final view of an agent-evaluation run (workflows/agent_evaluation.yaml). */
export function AgentRunView({ run }: { run: Run }) {
  const active = isActiveStatus(run.status);
  const queryClient = useQueryClient();
  const wasActive = useRef(active);
  // Polling stops the moment a run finishes, so the last poll can predate the final writes
  // (scores, recommendations, verdicts). Refetch everything once on the transition.
  useEffect(() => {
    if (wasActive.current && !active) {
      for (const key of [["runs", run.id], ["test-cases", run.id], ["recommendations", run.id]]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    }
    wasActive.current = active;
  }, [active, run.id, queryClient]);
  const progress = useRunProgress(run.id, run.status);
  const artifacts = useRunArtifacts(run.id, run.status);
  const tests = useTestCases(run.id, run.status);
  const recs = useRecommendations(run.id, run.status);

  const steps = progress.data?.steps ?? [];
  const events = progress.data?.events ?? [];
  const done = steps.filter((s) => s.status === "success" || s.status === "skipped").length;
  const pct = steps.length ? Math.round((done / steps.length) * 100) : 0;
  const testRows = tests.data ?? [];
  const requirements = artifacts.data?.requirements ?? [];
  const completed = run.status === "completed";
  const evidenceModel = run.compliance !== null || requirements.some((r) => r.criteria.length > 0);
  const findings = artifacts.data?.findings ?? [];
  const criteria = requirements.flatMap((r) => r.criteria);
  const provenCriteria = criteria.filter((c) => c.verdict === "verified_pass" || c.verdict === "implemented_static").length;
  const unknownCriteria = criteria.filter((c) => c.verdict === "insufficient_evidence").length;
  const notDeployed = run.mode === "brd_only";
  const stalled = useStalledMinutes(run, [
    events[events.length - 1]?.createdAt,
    ...steps.flatMap((s) => [s.startedAt, s.finishedAt]),
  ]);

  return (
    <div className="space-y-6">
      {run.status === "failed" && run.errorMessage && (
        <Card className="border-critical/40 bg-critical/5">
          <CardContent className="flex gap-3 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-critical" />
            <div>
              <p className="font-medium text-critical">The evaluation stopped</p>
              <p className="mt-1 whitespace-pre-wrap break-words">{run.errorMessage}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {run.status === "cancelled" && (
        <Card className="border-border bg-muted/40">
          <CardContent className="flex gap-3 text-sm">
            <Ban className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <div>
              <p className="font-medium">The evaluation was cancelled</p>
              <p className="mt-1 text-muted-foreground">
                {run.errorMessage ?? "Cancelled by the user"}. Anything gathered before it stopped is shown below; the run is not scored.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {stalled != null && (
        <Card className="border-warning/40 bg-warning/5">
          <CardContent className="flex gap-3 text-sm">
            <Clock className="mt-0.5 size-4 shrink-0 text-warning-foreground dark:text-warning" />
            <div>
              <p className="font-medium">No progress from the evaluation service for {stalled} min</p>
              <p className="mt-1 text-muted-foreground">
                The service may have stopped or lost its connection. If nothing changes, it marks the run as failed
                automatically and you can re-run it.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {completed && run.compliance && (
        <>
          <ComplianceCard c={run.compliance} />
          {run.summary && (
            <Card>
              <CardContent className="flex gap-3 text-sm">
                <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
                <p>{run.summary}</p>
              </CardContent>
            </Card>
          )}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <KpiCard label="Requirements" value={requirements.length} sub={`${criteria.length} acceptance criteria`} />
            <KpiCard label="Criteria proven" value={provenCriteria} tone="good" sub="verified or implemented in code" />
            <KpiCard label="Insufficient evidence" value={unknownCriteria} tone={unknownCriteria ? "warn" : "default"} />
            <KpiCard
              label="Runtime tests"
              value={notDeployed ? "—" : `${run.stats.passed}/${run.stats.passed + run.stats.failed}`}
              sub={notDeployed ? "agent not deployed: criteria verified from code" : "passed / executed"}
            />
            <KpiCard label="Findings" value={findings.length} tone={findings.some((f) => f.severity === "critical") ? "bad" : "default"}
              sub={`${findings.filter((f) => f.severity === "critical" || f.severity === "high").length} critical/high`} />
            <KpiCard label="Duration" value={duration(run.durationSec)} />
          </div>
        </>
      )}

      {completed && !run.compliance && (
        <>
          <QualityScoreCard
            title="Agent quality score"
            score={scoreOf(run)}
            breakdown={run.qualityBreakdown}
            riskLevel={run.stats.riskLevel}
            criticalDefects={run.stats.criticalDefects}
          />
          {run.summary && (
            <Card>
              <CardContent className="flex gap-3 text-sm">
                <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
                <p>{run.summary}</p>
              </CardContent>
            </Card>
          )}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <KpiCard label="Requirements" value={run.stats.scenariosFound} />
            <KpiCard label="Test cases" value={run.stats.testCasesGenerated} />
            <KpiCard label="Passed" value={run.stats.passed} tone="good" />
            <KpiCard
              label="Failed"
              value={run.stats.failed}
              tone={run.stats.failed > 0 ? "bad" : "default"}
              sub={`${run.stats.criticalDefects} critical`}
            />
            <KpiCard label="Requirement coverage" value={`${run.stats.coveragePct}%`} />
            <KpiCard label="Duration" value={duration(run.durationSec)} />
          </div>
        </>
      )}

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            {active && <Loader2 className="size-3.5 animate-spin text-primary" />}
            Pipeline
          </CardTitle>
          <span className="flex flex-wrap items-center justify-end gap-x-3">
            {progress.data && <PipelineTiming progress={progress.data} active={active} />}
            {active && <span className="font-mono text-xs tabular-nums text-muted-foreground">{pct}%</span>}
          </span>
        </CardHeader>
        <CardContent className="space-y-4">
          {active && (
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.max(pct, 3)}%` }} />
            </div>
          )}
          {progress.isLoading ? (
            <Skeleton className="h-72 rounded-lg" />
          ) : (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
              {steps.length ? (
                <PipelineSteps steps={steps} />
              ) : (
                <p className="text-sm text-muted-foreground">Queued. The steps appear as soon as the evaluation service picks up the run.</p>
              )}
              <ActivityLog events={events} live={active} />
            </div>
          )}
        </CardContent>
      </Card>

      <Tabs key={artifacts.data?.finalReport ? "with-report" : "no-report"} defaultValue={artifacts.data?.finalReport ? "report" : "tests"}>
        <TabsList className="flex-wrap">
          {artifacts.data?.finalReport && <TabsTrigger value="report">Report</TabsTrigger>}
          <TabsTrigger value="tests">Test cases {testRows.length ? `(${testRows.length})` : ""}</TabsTrigger>
          <TabsTrigger value="requirements">
            {evidenceModel ? "Traceability" : "Requirements"} {requirements.length ? `(${requirements.length})` : ""}
          </TabsTrigger>
          {evidenceModel && <TabsTrigger value="live">Live app</TabsTrigger>}
          {evidenceModel && <TabsTrigger value="findings">Findings {findings.length ? `(${findings.length})` : ""}</TabsTrigger>}
          <TabsTrigger value="logs">Logs</TabsTrigger>
          <TabsTrigger value="brd">BRD</TabsTrigger>
          <TabsTrigger value="profile">Agent profile</TabsTrigger>
          {completed && <TabsTrigger value="recommendations">Recommendations ({recs.data?.length ?? 0})</TabsTrigger>}
        </TabsList>

        <TabsContent value="tests" className="space-y-2 pt-2">
          {evidenceModel && notDeployed && testRows.length > 0 && (
            <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              These runtime tests are ready for when the agent is deployed. They are not part of the score: every criterion
              has been verified from the code instead (see Traceability).
            </p>
          )}
          <AgentTestCases tests={testRows} />
        </TabsContent>

        {artifacts.data?.finalReport && (
          <TabsContent value="report" className="pt-2">
            <FinalReportPanel runId={run.id} headline={artifacts.data.finalReport} />
          </TabsContent>
        )}

        <TabsContent value="logs" className="pt-2">
          <RunLogs runId={run.id} status={run.status} steps={steps} />
        </TabsContent>

        <TabsContent value="requirements" className="pt-2">
          {evidenceModel ? (
            <div className="space-y-4">
              {artifacts.data?.brdCompliance && <ComplianceSummary compliance={artifacts.data.brdCompliance} />}
              <TraceabilityMatrix requirements={requirements} runId={run.id} />
            </div>
          ) : (
            <RequirementsList requirements={requirements} tests={testRows} />
          )}
        </TabsContent>

        {evidenceModel && (
          <TabsContent value="live" className="pt-2">
            <LiveAppPanel
              profile={artifacts.data?.runtimeProfile ?? null}
              classification={artifacts.data?.appClassification ?? null}
              actionPlan={artifacts.data?.actionPlan ?? null}
              executionRun={artifacts.data?.executionRun ?? null}
              evidence={artifacts.data?.evidenceCollection ?? null}
              validation={artifacts.data?.outputValidation ?? null}
              passFail={artifacts.data?.passFail ?? null}
              runId={run.id}
              deployed={!notDeployed}
            />
          </TabsContent>
        )}

        {evidenceModel && (
          <TabsContent value="findings" className="pt-2">
            <FindingsList findings={findings} repoUrl={run.githubUrl} sha={run.commitRef} />
          </TabsContent>
        )}

        <TabsContent value="brd" className="pt-2">
          {artifacts.data?.brdContent ? (
            <Card>
              <CardHeader className="flex-row items-center gap-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Business Requirements Document</CardTitle>
                {artifacts.data.brdSource === "generated_live" ? (
                  <Badge className="gap-1 font-normal" variant="secondary">
                    <Sparkles className="size-3" /> Generated by Gemini from what the live app shows
                  </Badge>
                ) : artifacts.data.brdSource === "generated" ? (
                  <Badge className="gap-1 font-normal" variant="secondary">
                    <Sparkles className="size-3" /> Generated by Gemini from the code: no BRD in the repository
                  </Badge>
                ) : (
                  <Badge className="gap-1 font-normal" variant="secondary">
                    <FileText className="size-3" /> {artifacts.data.brdPath}
                  </Badge>
                )}
              </CardHeader>
              <CardContent className="max-h-[640px] overflow-y-auto">
                <MarkdownLite source={artifacts.data.brdContent} />
              </CardContent>
            </Card>
          ) : (
            <EmptyState icon={FileText} title="No BRD yet" description="MTA locates the BRD in the repository, or generates one with Gemini." />
          )}
        </TabsContent>

        <TabsContent value="profile" className="pt-2">
          {artifacts.data?.agentProfile ? (
            <AgentProfileCard profile={artifacts.data.agentProfile} />
          ) : (
            <EmptyState icon={Sparkles} title="Not analysed yet" description="Gemini reads the repository to work out what the agent does." />
          )}
        </TabsContent>

        {completed && (
          <TabsContent value="recommendations" className="space-y-2 pt-2">
            {(recs.data ?? []).map((r) => (
              <RecommendationCard key={r.id} recommendation={r} />
            ))}
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}

/** Minutes without a sign of life from the service (heartbeat, log line, step change), re-checked every 30 s. */
function useStalledMinutes(run: Run, signsOfLife: (string | null | undefined)[]) {
  const [now, setNow] = useState(() => Date.now());
  const active = isActiveStatus(run.status);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, [active]);
  return stalledMinutes(run, signsOfLife, now);
}
