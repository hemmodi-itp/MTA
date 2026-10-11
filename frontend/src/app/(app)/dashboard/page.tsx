"use client";

import { useMemo } from "react";
import Link from "next/link";
import { Gauge, Plus, Radar, ShieldAlert, TestTubes } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BriefHero } from "@/components/dashboard/brief-hero";
import { HealthScores } from "@/components/dashboard/health-scores";
import { RiskHeatmap } from "@/components/dashboard/risk-heatmap";
import { ComplianceTrend } from "@/components/dashboard/compliance-trend";
import { InsightsFeed } from "@/components/dashboard/insights-feed";
import { ActivityTimeline } from "@/components/dashboard/activity-timeline";
import { StatusOverview } from "@/components/dashboard/status-overview";
import { PerformanceMatrix } from "@/components/dashboard/performance-matrix";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { KpiCard } from "@/components/shared/kpi-card";
import { PageHeader, PageHeaderSkeleton } from "@/components/shared/page-header";
import { SectionCard } from "@/components/shared/section-card";
import { CardSkeleton, KpiRowSkeleton } from "@/components/shared/skeletons";
import { LiveDot } from "@/components/motion/live-dot";
import { Stagger } from "@/components/motion/stagger";
import { band } from "@/lib/insights";
import { BAND_TONE } from "@/lib/status";
import { brief, insights, portfolioKpis, projectHealth, sparkline } from "@/lib/insights";
import { useProjects, useRuns } from "@/lib/query/hooks";

const newEvaluation = (
  <Button asChild size="lg" className="gap-1.5">
    <Link href="/projects/new"><Plus aria-hidden /> New evaluation</Link>
  </Button>
);

function DashboardSkeleton() {
  return (
    <div role="status" className="space-y-4">
      <span className="sr-only">Loading the dashboard…</span>
      <KpiRowSkeleton count={4} className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4" />
      <div className="grid gap-4 xl:grid-cols-5">
        <CardSkeleton className="h-[340px] xl:col-span-3" />
        <CardSkeleton className="h-[340px] xl:col-span-2" />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const projectsQ = useProjects();
  const runsQ = useRuns();

  const view = useMemo(() => {
    const runs = runsQ.data ?? [];
    const projects = projectsQ.data ?? [];
    const health = projectHealth(runs);
    const kpis = portfolioKpis(runs, health);
    return { runs, projects, health, kpis, trend: sparkline(runs), insights: insights(runs, health), brief: brief(runs, health, kpis) };
  }, [runsQ.data, projectsQ.data]);

  const loading = projectsQ.isLoading || runsQ.isLoading;
  const { health, kpis } = view;
  const header = (
    <PageHeader
      title="Dashboard"
      description={loading || !health.length
        ? "Portfolio health, risks and live activity across your evaluations."
        : `Latest evaluation of each of your ${health.length} project${health.length > 1 ? "s" : ""}: compliance, runtime evidence and what needs attention.`}
      actions={newEvaluation}
    />
  );

  if (projectsQ.isError || runsQ.isError) {
    return <>{header}<ErrorState onRetry={() => { projectsQ.refetch(); runsQ.refetch(); }} /></>;
  }
  if (loading) return <><PageHeaderSkeleton actions /><DashboardSkeleton /></>;

  const worst = health[0];
  const chips = [
    ...(worst ? [{ label: `Open ${worst.name}`, href: `/runs/${worst.run.id}` }] : []),
    ...(kpis.active ? [{ label: `${kpis.active} running`, href: "/runs?status=running" }] : []),
    { label: "All runs", href: "/runs" },
  ];

  return (
    <>
      {header}
      {health.length === 0 ? (
        <EmptyState icon={Radar} title="No completed evaluations yet"
          description="Submit a repository with its BRD and live URL. MTA traces every requirement to code, tests the live app and scores compliance."
          actionLabel="New evaluation" actionHref="/projects/new" />
      ) : (
        <Stagger step={0.05} className="space-y-4">
          {/* grid children get min-w-0 so a wide heatmap or table scrolls inside its card instead of widening the page */}
          <div className="grid grid-cols-2 gap-3 *:min-w-0 sm:gap-4 xl:grid-cols-4">
            
              <KpiCard label="BRD compliance" value={kpis.compliance != null ? Math.round(kpis.compliance) : null} suffix="/100" icon={Gauge}
                tone={kpis.compliance == null ? "info" : BAND_TONE[band(kpis.compliance)]}
                delta={kpis.complianceDelta} sub={`average of ${health.length} project${health.length > 1 ? "s" : ""}, latest run each`} spark={kpis.spark} />
            
            
              <KpiCard label="Runtime verified" value={kpis.depth != null ? Math.round(kpis.depth * 100) : null} suffix="%" icon={Radar} tone="violet"
                sub="of runtime-verifiable criteria proven on the live app" />
            
            
              <KpiCard label="Runtime pass rate" value={kpis.passRate != null ? Math.round(kpis.passRate) : null} suffix="%" icon={TestTubes}
                tone={kpis.passRate == null ? "info" : kpis.passRate >= 80 ? "success" : kpis.passRate >= 50 ? "warning" : "critical"}
                sub={`${kpis.passed} passed · ${kpis.failed} failed · ${kpis.other} other`} />
            
            
              <KpiCard label="Blocking gates" value={kpis.blockers} icon={ShieldAlert} tone={kpis.blockers ? "critical" : "success"}
                valueTone={kpis.blockers ? "critical" : undefined}
                sub={kpis.blockers ? `across ${kpis.blockedProjects} project${kpis.blockedProjects > 1 ? "s" : ""}` : "nothing blocks release"} />
            
          </div>

          <div className="grid gap-4 *:min-w-0 xl:grid-cols-5">
            <SectionCard title="Compliance trend" className="xl:col-span-3" hint="Daily average BRD compliance of completed evaluations (line) and evaluation volume (bars), last 14 days.">
                <ComplianceTrend data={view.trend} />
              </SectionCard>
            
            <SectionCard title="Project health" className="xl:col-span-2" hint="Latest BRD compliance per project, riskiest first. Change is versus the project's previous run.">
                <HealthScores items={health} />
              </SectionCard>
            
          </div>

          <div className="grid gap-4 *:min-w-0 xl:grid-cols-5">
            <SectionCard title="Risk heatmap" className="xl:col-span-3" hint="Projects × quality dimensions from the latest run. Red < 50, amber 50–75, green ≥ 75.">
                <RiskHeatmap items={health} />
              </SectionCard>
            
            <SectionCard title="AI insights" className="xl:col-span-2" hint="Risks, regressions and recommendations generated from your latest evaluations."
                action={<span className="rounded-full bg-primary/12 px-2 py-0.5 text-2xs font-semibold text-info-fg tabular-nums">{view.insights.length}</span>}>
                <InsightsFeed items={view.insights} />
              </SectionCard>
            
          </div>

          <div className="grid gap-4 *:min-w-0 lg:grid-cols-2 2xl:grid-cols-12">
            <SectionCard title="Status overview" className="2xl:col-span-3" hint="All your runs by outcome.">
                <StatusOverview runs={view.runs} />
              </SectionCard>
            
            <SectionCard title="Performance matrix" className="2xl:col-span-5" hint="Latest run per project: compliance, runtime test outcomes, verification depth and duration.">
                <PerformanceMatrix items={health} />
              </SectionCard>
            
            <SectionCard title="Live activity" className="lg:col-span-2 2xl:col-span-4" hint="Newest pipeline events across your evaluations; updates every few seconds."
                bodyClassName="max-h-[340px] overflow-y-auto" action={<LiveDot tone="success" />}>
                <ActivityTimeline />
              </SectionCard>
            
          </div>
        </Stagger>
      )}

      <BriefHero headline={view.brief.headline} lines={view.brief.lines} chips={chips} />
    </>
  );
}
