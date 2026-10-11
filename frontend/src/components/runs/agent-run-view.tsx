"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Ban, Clock, FileText, Lightbulb, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { KpiCard } from "@/components/shared/kpi-card";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { Notice } from "@/components/shared/notice";
import { SectionCard } from "@/components/shared/section-card";
import { RunBodySkeleton } from "@/components/shared/skeletons";
import { Stagger, StaggerItem } from "@/components/motion/stagger";
import { MotionCard } from "@/components/motion/motion-card";
import { QualityScoreCard } from "@/components/reports/quality-score-card";
import { RecommendationCard } from "@/components/reports/recommendation-card";
import { PipelineCard } from "@/components/runs/pipeline-card";
import { AgentTestCases } from "@/components/runs/agent-test-cases";
import { RequirementsList } from "@/components/runs/requirements-list";
import { MarkdownLite } from "@/components/runs/markdown-lite";
import { AgentProfileCard } from "@/components/runs/agent-profile-card";
import { ComplianceCard } from "@/components/runs/compliance-card";
import { ComplianceSummary, TraceabilityMatrix } from "@/components/runs/traceability-matrix";
import { FinalReportPanel } from "@/components/runs/final-report-panel";
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

/** First clause of a raw service error ("BRD step failed: ClientError: …" → "BRD step failed"), for the headline. */
function errorHeadline(message: string) {
  const first = message.split(/:\s/)[0].trim();
  return first.length > 0 && first.length <= 120 ? first : "The evaluation service reported an error";
}

/** The run's one-paragraph summary from the pipeline. */
function Summary({ text }: { text: string }) {
  return (
    <MotionCard interactive={false} className="flex gap-3 p-5 text-sm">
      <Sparkles aria-hidden className="mt-0.5 size-4 shrink-0 text-info-fg" />
      <p className="text-pretty">{text}</p>
    </MotionCard>
  );
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

  // One loading state for the whole body: every section below depends on these, and showing them piecemeal would
  // flash zeros (0 requirements) and push the tabs down as each one arrives.
  if (progress.isLoading || artifacts.isLoading || tests.isLoading) return <RunBodySkeleton />;

  const criticalFindings = findings.filter((f) => f.severity === "critical" || f.severity === "high").length;

  return (
    <div className="space-y-6">
      {run.status === "failed" && run.errorMessage && (
        <ErrorState
          title="The evaluation stopped"
          message={<>{errorHeadline(run.errorMessage)}. The steps below show where it stopped; you can re-run it once the cause is fixed.</>}
          details={run.errorMessage}
        />
      )}

      {run.status === "cancelled" && (
        <Notice icon={Ban} title="The evaluation was cancelled">
          {run.errorMessage ?? "Cancelled by the user"}. Anything gathered before it stopped is shown below; the run is not scored.
        </Notice>
      )}

      {stalled != null && (
        <Notice tone="warning" icon={Clock} title={`No progress from the evaluation service for ${stalled} min`}>
          The service may have stopped or lost its connection. If nothing changes, it marks the run as failed automatically
          and you can re-run it.
        </Notice>
      )}

      {completed && run.compliance && (
        <>
          <ComplianceCard c={run.compliance} />
          {run.summary && <Summary text={run.summary} />}
          <Stagger className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
            <StaggerItem><KpiCard size="sm" label="Requirements" value={requirements.length} sub={`${criteria.length} acceptance criteria`} /></StaggerItem>
            <StaggerItem><KpiCard size="sm" label="Criteria proven" value={provenCriteria} valueTone="success" sub="verified, or implemented in code" /></StaggerItem>
            <StaggerItem><KpiCard size="sm" label="Insufficient evidence" value={unknownCriteria} valueTone={unknownCriteria ? "warning" : undefined} sub="criteria nothing could prove" /></StaggerItem>
            <StaggerItem>
              <KpiCard size="sm" label="Runtime tests"
                value={notDeployed ? "—" : `${run.stats.passed}/${run.stats.passed + run.stats.failed}`}
                sub={notDeployed ? "agent not deployed: verified from code" : "passed / executed"} />
            </StaggerItem>
            <StaggerItem>
              <KpiCard size="sm" label="Findings" value={findings.length} valueTone={findings.some((f) => f.severity === "critical") ? "critical" : undefined}
                sub={`${criticalFindings} critical or high`} />
            </StaggerItem>
            <StaggerItem><KpiCard size="sm" label="Duration" value={duration(run.durationSec)} /></StaggerItem>
          </Stagger>
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
          {run.summary && <Summary text={run.summary} />}
          <Stagger className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
            <StaggerItem><KpiCard size="sm" label="Requirements" value={run.stats.scenariosFound} /></StaggerItem>
            <StaggerItem><KpiCard size="sm" label="Test cases" value={run.stats.testCasesGenerated} /></StaggerItem>
            <StaggerItem><KpiCard size="sm" label="Passed" value={run.stats.passed} valueTone="success" /></StaggerItem>
            <StaggerItem>
              <KpiCard size="sm" label="Failed" value={run.stats.failed} valueTone={run.stats.failed > 0 ? "critical" : undefined}
                sub={`${run.stats.criticalDefects} critical`} />
            </StaggerItem>
            <StaggerItem><KpiCard size="sm" label="Requirement coverage" value={run.stats.coveragePct} suffix="%" /></StaggerItem>
            <StaggerItem><KpiCard size="sm" label="Duration" value={duration(run.durationSec)} /></StaggerItem>
          </Stagger>
        </>
      )}

      {progress.data && <PipelineCard progress={progress.data} active={active} failed={run.status === "failed"} />}

      <Tabs key={artifacts.data?.finalReport ? "with-report" : "no-report"} defaultValue={artifacts.data?.finalReport ? "report" : "tests"}>
        {/* one scrolling row on small screens instead of wrapping into several */}
        <div className="no-scrollbar overflow-x-auto border-b border-border">
          <TabsList variant="line" className="w-max justify-start gap-1">
            {artifacts.data?.finalReport && <TabsTrigger value="report">Report</TabsTrigger>}
            <TabsTrigger value="tests">Test cases <Count n={testRows.length} /></TabsTrigger>
            <TabsTrigger value="requirements">{evidenceModel ? "Traceability" : "Requirements"} <Count n={requirements.length} /></TabsTrigger>
            {evidenceModel && <TabsTrigger value="live">Live app</TabsTrigger>}
            {evidenceModel && <TabsTrigger value="findings">Findings <Count n={findings.length} /></TabsTrigger>}
            <TabsTrigger value="logs">Logs</TabsTrigger>
            <TabsTrigger value="brd">BRD</TabsTrigger>
            <TabsTrigger value="profile">Agent profile</TabsTrigger>
            {completed && <TabsTrigger value="recommendations">Recommendations <Count n={recs.data?.length ?? 0} /></TabsTrigger>}
          </TabsList>
        </div>

        <TabsContent value="tests" className="space-y-2 pt-2">
          {evidenceModel && notDeployed && testRows.length > 0 && (
            <p className="rounded-xl border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
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
            <SectionCard
              title="Business Requirements Document"
              action={
                artifacts.data.brdSource === "generated_live" ? (
                  <Badge className="gap-1 font-normal" variant="secondary"><Sparkles className="size-3" /> Generated by Gemini from the live app</Badge>
                ) : artifacts.data.brdSource === "generated" ? (
                  <Badge className="gap-1 font-normal" variant="secondary"><Sparkles className="size-3" /> Generated by Gemini from the code</Badge>
                ) : (
                  <Badge className="max-w-60 gap-1 font-normal" variant="secondary"><FileText className="size-3" /> <span className="truncate">{artifacts.data.brdPath}</span></Badge>
                )
              }
              bodyClassName="max-h-[640px] overflow-y-auto"
            >
              <MarkdownLite source={artifacts.data.brdContent} />
            </SectionCard>
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
          <TabsContent value="recommendations" className="pt-2">
            {(recs.data ?? []).length ? (
              <Stagger className="space-y-2">
                {(recs.data ?? []).map((r, i) => (
                  <StaggerItem key={r.id} index={i}><RecommendationCard recommendation={r} /></StaggerItem>
                ))}
              </Stagger>
            ) : (
              <EmptyState icon={Lightbulb} title="No recommendations" description="Nothing to suggest for this run." />
            )}
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}

function Count({ n }: { n: number }) {
  if (!n) return null;
  return <span className="rounded-full bg-muted px-1.5 text-2xs font-semibold text-muted-foreground tabular-nums">{n}</span>;
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
