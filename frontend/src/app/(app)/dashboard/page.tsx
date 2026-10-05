"use client";

import { useMemo } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Gauge, Plus, Radar, ShieldAlert, TestTubes } from "lucide-react";
import { BriefHero } from "@/components/dashboard/brief-hero";
import { KpiTile } from "@/components/dashboard/kpi-tile";
import { Section } from "@/components/dashboard/section";
import { HealthScores } from "@/components/dashboard/health-scores";
import { RiskHeatmap } from "@/components/dashboard/risk-heatmap";
import { ComplianceTrend } from "@/components/dashboard/compliance-trend";
import { InsightsFeed } from "@/components/dashboard/insights-feed";
import { ActivityTimeline } from "@/components/dashboard/activity-timeline";
import { StatusOverview } from "@/components/dashboard/status-overview";
import { PerformanceMatrix } from "@/components/dashboard/performance-matrix";
import { ErrorState } from "@/components/shared/error-state";
import { stagger } from "@/lib/motion";
import { brief, insights, portfolioKpis, projectHealth, sparkline } from "@/lib/insights";
import { useProjects, useRuns } from "@/lib/query/hooks";

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="shimmer h-36 rounded-2xl" />)}</div>
      <div className="grid gap-4 xl:grid-cols-3"><div className="shimmer h-80 rounded-2xl xl:col-span-2" /><div className="shimmer h-80 rounded-2xl" /></div>
      <div className="shimmer h-56 rounded-2xl" />
    </div>
  );
}

function EmptyPortfolio() {
  return (
    <div className="flex flex-col items-center gap-4 rounded-2xl border border-dashed border-border px-6 py-16 text-center">
      <motion.div animate={{ y: [0, -6, 0], rotate: [0, 4, -4, 0] }} transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
        className="flex size-16 items-center justify-center rounded-2xl bg-gradient-to-br from-primary/20 to-violet/20 text-primary">
        <Radar className="size-8" />
      </motion.div>
      <div>
        <p className="text-lg font-semibold">No completed evaluations yet</p>
        <p className="mt-1 max-w-md text-sm text-muted-foreground">Submit a repository with its BRD and live URL. MTA traces every requirement to code, tests the live app and scores compliance.</p>
      </div>
      <Link href="/projects/new" className="inline-flex h-10 items-center gap-2 rounded-xl bg-gradient-to-r from-primary to-violet px-4 text-sm font-semibold text-white shadow-lg shadow-primary/25">
        <Plus className="size-4" /> New evaluation
      </Link>
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

  if (projectsQ.isError || runsQ.isError) return <ErrorState onRetry={() => { projectsQ.refetch(); runsQ.refetch(); }} />;
  if (projectsQ.isLoading || runsQ.isLoading) return <DashboardSkeleton />;

  const { health, kpis } = view;
  const worst = health[0];
  const chips = [
    ...(worst ? [{ label: `Open ${worst.name}`, href: `/runs/${worst.run.id}` }] : []),
    ...(kpis.active ? [{ label: `${kpis.active} running`, href: "/runs?status=running" }] : []),
    { label: "All runs", href: "/runs" },
  ];

  return (
    <motion.div variants={stagger(0.07)} initial="hidden" animate="show" className="space-y-6">
      {health.length === 0 ? <EmptyPortfolio /> : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <KpiTile label="BRD compliance" value={kpis.compliance != null ? Math.round(kpis.compliance) : null} suffix="/100" icon={Gauge}
              tone={kpis.compliance == null ? "primary" : kpis.compliance >= 75 ? "good" : kpis.compliance >= 50 ? "warn" : "bad"}
              delta={kpis.complianceDelta} sub={`average of ${health.length} project${health.length > 1 ? "s" : ""}, latest run each`} spark={kpis.spark} />
            <KpiTile label="Runtime verified" value={kpis.depth != null ? Math.round(kpis.depth * 100) : null} suffix="%" icon={Radar} tone="violet"
              sub="of runtime-verifiable criteria proven on the live app" />
            <KpiTile label="Runtime pass rate" value={kpis.passRate != null ? Math.round(kpis.passRate) : null} suffix="%" icon={TestTubes}
              tone={kpis.passRate == null ? "primary" : kpis.passRate >= 80 ? "good" : kpis.passRate >= 50 ? "warn" : "bad"}
              sub={`${kpis.passed} passed · ${kpis.failed} failed · ${kpis.other} other`} />
            <KpiTile label="Blocking gates" value={kpis.blockers} icon={ShieldAlert} tone={kpis.blockers ? "bad" : "good"}
              sub={kpis.blockers ? `across ${kpis.blockedProjects} project${kpis.blockedProjects > 1 ? "s" : ""}` : "nothing blocks release"} />
          </div>

          <div className="grid gap-4 xl:grid-cols-5">
            <Section title="Compliance trend" hint="Daily average BRD compliance of completed evaluations (line) and evaluation volume (bars), last 14 days." className="xl:col-span-3">
              <ComplianceTrend data={view.trend} />
            </Section>
            <Section title="Project health" hint="Latest BRD compliance per project, riskiest first. Change is versus the project's previous run." className="xl:col-span-2">
              <HealthScores items={health} />
            </Section>
          </div>

          <div className="grid gap-4 xl:grid-cols-5">
            <Section title="Risk heatmap" hint="Projects × quality dimensions from the latest run. Red < 50, amber 50–75, green ≥ 75." className="xl:col-span-3">
              <RiskHeatmap items={health} />
            </Section>
            <Section title="AI insights" hint="Risks, regressions and recommendations generated from your latest evaluations." className="xl:col-span-2"
              action={<span className="rounded-full bg-primary/12 px-2 py-0.5 text-[11px] font-semibold text-primary">{view.insights.length}</span>}>
              <InsightsFeed items={view.insights} />
            </Section>
          </div>

          <div className="grid gap-4 xl:grid-cols-12">
            <Section title="Status overview" hint="All your runs by outcome." className="xl:col-span-3">
              <StatusOverview runs={view.runs} />
            </Section>
            <Section title="Performance matrix" hint="Latest run per project: compliance, runtime test outcomes, verification depth and duration." className="xl:col-span-5">
              <PerformanceMatrix items={health} />
            </Section>
            <Section title="Live activity" hint="Newest pipeline events across your evaluations; updates every few seconds." className="xl:col-span-4"
              bodyClassName="max-h-[340px] overflow-y-auto"
              action={<span className="relative flex size-2"><span className="absolute inset-0 animate-[pulse-ring_1.8s_cubic-bezier(0.2,0,0,1)_infinite] rounded-full bg-success" /><span className="relative size-2 rounded-full bg-success" /></span>}>
              <ActivityTimeline />
            </Section>
          </div>
        </>
      )}

      <BriefHero headline={view.brief.headline} lines={view.brief.lines} chips={chips} />
    </motion.div>
  );
}
