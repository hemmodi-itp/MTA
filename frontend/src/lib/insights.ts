/**
 * Portfolio analytics for the dashboard — derived only from the runs the user can see (no mock data).
 * Deterministic: the "AI brief" and insights are rules over real numbers, so they can be trusted and explained.
 */
import type { Run } from "@/lib/types";
import { ACTIVE_RUN_STATUSES, isActiveStatus } from "@/lib/run-status";

export const ACTIVE_STATUSES = ACTIVE_RUN_STATUSES;
export const isActive = (r: Run) => isActiveStatus(r.status);

export const shortName = (name: string) => name.split("/").pop() ?? name;

/**
 * The run's headline score, or null when it was not scored. The evidence-weighted compliance score when there is one;
 * otherwise only the quality score of runs from before compliance scoring (no scoringVersion) that actually got one.
 * A finished run without a compliance score is "not scored" — the 0 older rows carry in qualityScore is not a score.
 */
export const scoreOf = (r: Run): number | null => {
  if (r.compliance?.score != null) return r.compliance.score;
  if (r.status !== "completed" || r.compliance?.scoringVersion) return null;
  return r.stats.qualityScore > 0 ? r.stats.qualityScore : null;
};
/** "53", or "—" for an unscored run. */
export const formatScore = (score: number | null | undefined) => (score == null ? "—" : String(Math.round(score)));
export type Band = "good" | "warn" | "bad" | "none";
export const band = (v: number | null | undefined): Band => (v == null ? "none" : v >= 75 ? "good" : v >= 50 ? "warn" : "bad");

export interface ProjectHealth {
  projectId: string;
  name: string;
  run: Run;
  previous: Run | null;
  score: number | null;
  delta: number | null;
  depth: number | null;
  blocks: number;
  warns: number;
  history: { at: string; score: number }[];
}

/** Latest completed run per project (newest first) + its previous run and score history. */
export function projectHealth(runs: Run[]): ProjectHealth[] {
  const byProject = new Map<string, Run[]>();
  for (const r of [...runs].sort((a, b) => b.startedAt.localeCompare(a.startedAt))) {
    if (r.status !== "completed") continue;
    const list = byProject.get(r.projectId) ?? [];
    list.push(r);
    byProject.set(r.projectId, list);
  }
  return [...byProject.values()].map((list) => {
    const [run, previous] = list;
    const score = scoreOf(run);
    const prev = previous ? scoreOf(previous) : null;
    const gates = run.compliance?.gates ?? [];
    return {
      projectId: run.projectId, name: shortName(run.projectName), run, previous: previous ?? null, score,
      delta: score != null && prev != null ? Math.round((score - prev) * 10) / 10 : null,
      depth: run.compliance?.verificationDepth ?? null,
      blocks: gates.filter((g) => g.level === "block").length,
      warns: gates.filter((g) => g.level === "warn").length,
      history: list.map((r) => ({ at: r.finishedAt ?? r.startedAt, score: scoreOf(r) })).filter((h): h is { at: string; score: number } => h.score != null).reverse(),
    };
  }).sort((a, b) => (a.score ?? 101) - (b.score ?? 101));
}

const avg = (xs: number[]) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null);

export function portfolioKpis(runs: Run[], health: ProjectHealth[]) {
  const latest = health.map((h) => h.run);
  const scores = health.map((h) => h.score).filter((s): s is number => s != null);
  const prevScores = health.map((h) => (h.previous ? scoreOf(h.previous) : h.score)).filter((s): s is number => s != null);
  const depths = health.map((h) => h.depth).filter((d): d is number => d != null);
  const passed = latest.reduce((s, r) => s + r.stats.passed, 0);
  const failed = latest.reduce((s, r) => s + r.stats.failed, 0);
  const other = latest.reduce((s, r) => s + r.stats.skipped, 0);
  const weekAgo = Date.now() - 7 * 86_400_000;
  const compliance = avg(scores);
  const prevCompliance = avg(prevScores);
  return {
    compliance,
    complianceDelta: compliance != null && prevCompliance != null ? Math.round((compliance - prevCompliance) * 10) / 10 : null,
    depth: avg(depths),
    passRate: passed + failed ? (100 * passed) / (passed + failed) : null,
    passed, failed, other,
    blockers: health.reduce((s, h) => s + h.blocks, 0),
    blockedProjects: health.filter((h) => h.blocks > 0).length,
    active: runs.filter(isActive).length,
    runsThisWeek: runs.filter((r) => new Date(r.startedAt).getTime() >= weekAgo).length,
    spark: health.length ? sparkline(runs) : [],
  };
}

/** Daily average compliance over completed runs (for KPI sparklines and the trend chart). */
export function sparkline(runs: Run[], days = 14) {
  const out: { day: string; score: number | null; runs: number }[] = [];
  const now = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    const day = runs.filter((r) => r.status === "completed" && (r.finishedAt ?? r.startedAt).slice(0, 10) === key);
    const scores = day.map(scoreOf).filter((s): s is number => s != null);
    out.push({ day: key, score: scores.length ? Math.round(avg(scores)!) : null, runs: day.length });
  }
  // carry the last known value forward so the line reads as a level, not gaps
  let last: number | null = null;
  return out.map((p) => { if (p.score != null) last = p.score; return { ...p, level: p.score ?? last }; });
}

export const HEAT_DIMENSIONS: { key: string; label: string }[] = [
  { key: "compliance", label: "BRD compliance" },
  { key: "depth", label: "Runtime verified" },
  { key: "security", label: "Security" },
  { key: "workflow", label: "Workflow" },
  { key: "performance", label: "Performance" },
  { key: "agent_design", label: "Agent design" },
  { key: "architecture", label: "Architecture" },
  { key: "production_readiness", label: "Prod. readiness" },
];

export function heatRow(h: ProjectHealth): Record<string, number | null> {
  const sc = h.run.compliance?.scorecard ?? {};
  const row: Record<string, number | null> = { compliance: h.score, depth: h.depth != null ? Math.round(h.depth * 100) : null };
  for (const d of HEAT_DIMENSIONS.slice(2)) row[d.key] = typeof sc[d.key] === "number" ? sc[d.key] : null;
  return row;
}

export type InsightKind = "risk" | "trend-down" | "trend-up" | "recommendation" | "success";
export interface Insight { id: string; kind: InsightKind; title: string; body: string; href: string; weight: number }

export function insights(runs: Run[], health: ProjectHealth[]): Insight[] {
  const out: Insight[] = [];
  for (const h of health) {
    const gates = h.run.compliance?.gates ?? [];
    for (const g of gates.filter((x) => x.level === "block").slice(0, 2)) {
      out.push({ id: `${h.run.id}-${g.gate}`, kind: "risk", weight: 100, title: `${h.name}: ${g.gate.replace(/_/g, " ")}`, body: g.reason, href: `/runs/${h.run.id}` });
    }
    const login = gates.find((g) => g.gate === "live_behind_login" || g.gate === "live_login_failed");
    if (login) {
      out.push({ id: `${h.run.id}-login`, kind: "recommendation", weight: 80, title: `${h.name}: live app not tested`,
        body: login.gate === "live_login_failed" ? "The test account could not log in. Check it on the app's login page and re-run."
          : "The app is behind a login. Add a test account to the project so MTA can verify behaviour at runtime.", href: `/runs/${h.run.id}` });
    }
    if (h.delta != null && h.delta <= -5) {
      out.push({ id: `${h.run.id}-down`, kind: "trend-down", weight: 70, title: `${h.name} regressed ${Math.abs(h.delta)} points`,
        body: `Compliance fell from ${Math.round((h.score ?? 0) - h.delta)} to ${Math.round(h.score ?? 0)} since the previous run.`, href: `/runs/${h.run.id}` });
    } else if (h.delta != null && h.delta >= 5) {
      out.push({ id: `${h.run.id}-up`, kind: "trend-up", weight: 40, title: `${h.name} improved ${h.delta} points`,
        body: `Compliance rose to ${Math.round(h.score ?? 0)} since the previous run.`, href: `/runs/${h.run.id}` });
    }
    if (h.depth != null && h.depth < 0.3 && !login) {
      out.push({ id: `${h.run.id}-depth`, kind: "recommendation", weight: 50, title: `${h.name}: verified mostly from code`,
        body: `Only ${Math.round(h.depth * 100)}% of runtime-verifiable criteria were proven on the live app.`, href: `/runs/${h.run.id}` });
    }
    if (h.score != null && h.score >= 85 && h.blocks === 0) {
      out.push({ id: `${h.run.id}-ok`, kind: "success", weight: 20, title: `${h.name} is in good shape`,
        body: `Compliance ${Math.round(h.score)} with no blocking gates.`, href: `/runs/${h.run.id}` });
    }
  }
  const dayAgo = Date.now() - 86_400_000;
  for (const r of runs.filter((x) => x.status === "failed" && new Date(x.finishedAt ?? x.startedAt).getTime() > dayAgo).slice(0, 3)) {
    out.push({ id: `${r.id}-failed`, kind: "risk", weight: 90, title: `${shortName(r.projectName)}: evaluation failed`,
      body: r.errorMessage?.slice(0, 160) ?? "See the run log for details.", href: `/runs/${r.id}` });
  }
  return out.sort((a, b) => b.weight - a.weight).slice(0, 8);
}

/** The hero brief: one headline and up to three supporting sentences, all from real numbers. */
export function brief(runs: Run[], health: ProjectHealth[], kpis: ReturnType<typeof portfolioKpis>) {
  if (!health.length) {
    return runs.some(isActive)
      ? { headline: "Your first evaluation is running.", lines: ["Results, risks and recommendations appear here as soon as it finishes."] }
      : { headline: "Evaluate your first agent.", lines: ["Submit a GitHub repo with its BRD and live URL. MTA traces every requirement to code and tests the live app."] };
  }
  const attention = health.filter((h) => h.blocks > 0 || (h.score ?? 100) < 50);
  const worst = health[0];
  const headline = attention.length
    ? `${attention.length} evaluation${attention.length > 1 ? "s need" : " needs"} attention. ${worst.name} is the highest risk at ${worst.score != null ? Math.round(worst.score) : "—"}/100.`
    : `All ${health.length} evaluated project${health.length > 1 ? "s are" : " is"} clear of blocking gates.`;
  const lines: string[] = [];
  if (kpis.compliance != null) {
    lines.push(`Portfolio BRD compliance averages ${Math.round(kpis.compliance)}/100` +
      (kpis.complianceDelta ? `, ${kpis.complianceDelta > 0 ? "up" : "down"} ${Math.abs(kpis.complianceDelta)} since the previous runs.` : "."));
  }
  if (kpis.depth != null) {
    lines.push(`${Math.round(kpis.depth * 100)}% of runtime-verifiable criteria were proven on live apps; ${kpis.passed} runtime test${kpis.passed === 1 ? "" : "s"} passed and ${kpis.failed} failed.`);
  }
  if (worst.blocks) {
    const g = worst.run.compliance?.gates.find((x) => x.level === "block");
    if (g) lines.push(`${worst.name}: ${g.reason}`);
  }
  if (kpis.active) lines.push(`${kpis.active} evaluation${kpis.active > 1 ? "s are" : " is"} running now.`);
  return { headline, lines: lines.slice(0, 3) };
}
