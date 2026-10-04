import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@/lib/db";
import { requireUser, visibleProjects, visibleRuns } from "@/lib/api/server/access";
import { BACKEND_URL, backendHeaders } from "@/lib/api/server/evaluation";

const body = z.object({
  question: z.string().trim().min(1).max(2000),
  runId: z.string().max(64).optional(),
  projectId: z.string().max(64).optional(),
  history: z.array(z.object({ role: z.enum(["user", "assistant"]), content: z.string().max(4000) })).max(12).optional(),
});

type Json = Record<string, unknown> | null;
const j = (v: unknown) => (v ?? null) as Json;

/**
 * MTA Copilot. Builds the grounding context here — from runs this user may see, never anything else — and asks
 * the evaluation service (Gemini) to answer from it. Scope: one run (when on a run page), one project, or the portfolio.
 */
export async function POST(request: Request) {
  const { user, response } = await requireUser();
  if (response) return response;
  const parsed = body.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ error: "Ask a question (up to 2000 characters)." }, { status: 400 });
  const { question, runId, projectId, history } = parsed.data;

  const { scope, context } = runId
    ? await runContext(runId, user.id)
    : projectId
      ? await projectContext(projectId, user.id)
      : await portfolioContext(user.id);
  if (!context) return NextResponse.json({ error: "That run or project isn't available to you." }, { status: 404 });

  try {
    const res = await fetch(`${BACKEND_URL}/copilot`, {
      method: "POST",
      headers: backendHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ question, context, scope, history: history ?? [] }),
      signal: AbortSignal.timeout(90_000),
      cache: "no-store",
    });
    const out = await res.json().catch(() => ({}));
    if (!res.ok) return NextResponse.json({ error: out.detail ?? "The Copilot is unavailable right now." }, { status: 502 });
    return NextResponse.json({ answer: out.answer as string, scope });
  } catch {
    return NextResponse.json({ error: "The MTA evaluation service is not reachable. Start it on port 8100 and try again." }, { status: 503 });
  }
}

async function runContext(runId: string, userId: string) {
  const run = await prisma.run.findFirst({
    where: { id: runId, ...visibleRuns(userId) },
    select: {
      id: true, status: true, mode: true, liveUrl: true, startedAt: true, finishedAt: true, summary: true, errorMessage: true,
      complianceScore: true, ciLow: true, ciHigh: true, verificationDepth: true, gates: true, scorecard: true,
      passed: true, failed: true, skipped: true, brdSource: true, brdPath: true,
      passFail: true, brdCompliance: true, finalReport: true, appClassification: true, runtimeProfile: true,
      project: { select: { name: true, githubUrl: true } },
      recommendations: { select: { severity: true, summary: true }, take: 15 },
      requirements: { select: { code: true, title: true, priority: true, verdict: true, score: true }, orderBy: { code: "asc" } },
    },
  });
  if (!run) return { scope: "run", context: null };
  const pf = j(run.passFail) as { counts?: unknown; tests?: { test_code: string; title: string; criterion_code: string; verdict: string; score: number | null; reasons: string[] }[] } | null;
  const bc = j(run.brdCompliance) as { discrepancies?: { kind: string; criterion_code: string; detail: string }[]; evidence_mix?: unknown; counts?: unknown } | null;
  const fr = (j(run.finalReport) as { data?: { decision?: unknown; summary?: string[]; limitations?: string[] } } | null)?.data;
  const prof = j(run.runtimeProfile) as { login?: unknown; needs_credentials?: boolean; pages_inspected?: number } | null;
  const lines = [
    `RUN ${run.id} of project ${run.project.name} (${run.project.githubUrl}); status ${run.status}; mode ${run.mode}; live URL ${run.liveUrl ?? "none"}; BRD ${run.brdPath ?? run.brdSource ?? "none"}`,
    `Started ${run.startedAt.toISOString()}${run.finishedAt ? `, finished ${run.finishedAt.toISOString()}` : ""}${run.errorMessage ? `; error: ${run.errorMessage}` : ""}`,
    `Compliance ${run.complianceScore ?? "n/a"} (90% interval ${run.ciLow ?? "?"}–${run.ciHigh ?? "?"}); runtime verification depth ${run.verificationDepth ?? "n/a"}`,
    `Tests: ${run.passed} passed, ${run.failed} failed, ${run.skipped} inconclusive/not run`,
    `Gates: ${JSON.stringify(run.gates ?? [])}`,
    `Quality scorecard: ${JSON.stringify(run.scorecard ?? {})}`,
    `Application type: ${JSON.stringify((j(run.appClassification) as { app_type?: string } | null)?.app_type ?? null)}; live login: ${JSON.stringify(prof?.login ?? null)}; needs credentials: ${prof?.needs_credentials ?? false}`,
    fr ? `Final report decision: ${JSON.stringify(fr.decision)}\nSummary: ${(fr.summary ?? []).join(" ")}\nLimitations: ${(fr.limitations ?? []).join(" | ")}` : "",
    `Requirements:\n${run.requirements.map((r) => `- ${r.code} ${r.title} [${r.priority}] → ${r.verdict ?? "pending"} (${r.score != null ? Math.round(r.score * 100) + "%" : "n/a"})`).join("\n")}`,
    pf?.tests ? `Runtime test verdicts:\n${pf.tests.slice(0, 40).map((t) => `- ${t.test_code} (${t.criterion_code}) ${t.title}: ${t.verdict}${t.score != null ? ` ${t.score}` : ""} — ${(t.reasons ?? [])[0] ?? ""}`).join("\n")}` : "",
    bc?.discrepancies?.length ? `Code vs runtime discrepancies:\n${bc.discrepancies.map((d) => `- ${d.kind} ${d.criterion_code}: ${d.detail}`).join("\n")}` : "",
    run.recommendations.length ? `Recommendations:\n${run.recommendations.map((r) => `- [${r.severity}] ${r.summary}`).join("\n")}` : "",
    run.summary ? `Run summary: ${run.summary}` : "",
  ];
  return { scope: `run · ${run.project.name}`, context: lines.filter(Boolean).join("\n") };
}

async function projectContext(projectId: string, userId: string) {
  const project = await prisma.project.findFirst({ where: { id: projectId, ...visibleProjects(userId) }, select: { id: true, name: true } });
  if (!project) return { scope: "project", context: null };
  const latest = await prisma.run.findFirst({ where: { projectId, ...visibleRuns(userId) }, orderBy: { startedAt: "desc" }, select: { id: true } });
  if (!latest) return { scope: `project · ${project.name}`, context: `Project ${project.name} has no runs yet.` };
  const ctx = await runContext(latest.id, userId);
  const history = await prisma.run.findMany({ where: { projectId, ...visibleRuns(userId) }, orderBy: { startedAt: "desc" }, take: 10,
    select: { id: true, status: true, startedAt: true, complianceScore: true } });
  return { scope: `project · ${project.name}`,
    context: `${ctx.context}\nRun history (newest first): ${history.map((h) => `${h.id} ${h.status} ${h.startedAt.toISOString().slice(0, 16)} compliance ${h.complianceScore ?? "n/a"}`).join("; ")}` };
}

async function portfolioContext(userId: string) {
  const projects = await prisma.project.findMany({
    where: visibleProjects(userId),
    select: {
      name: true, isSample: true, mode: true, liveUrl: true,
      runs: { orderBy: { startedAt: "desc" }, take: 3,
        select: { id: true, status: true, startedAt: true, finishedAt: true, complianceScore: true, verificationDepth: true, gates: true,
          passed: true, failed: true, skipped: true, errorMessage: true } },
    },
  });
  const lines = projects.map((p) => {
    const runs = p.runs.map((r) => {
      const gates = ((r.gates ?? []) as { gate: string; level: string }[]).filter((g) => g.level !== "pass").map((g) => `${g.level}:${g.gate}`);
      return `  - run ${r.id} ${r.status} ${r.startedAt.toISOString().slice(0, 16)} compliance ${r.complianceScore ?? "n/a"} depth ${r.verificationDepth ?? "n/a"} tests ${r.passed}/${r.failed}/${r.skipped} (pass/fail/other)${gates.length ? ` gates ${gates.join(", ")}` : ""}${r.errorMessage ? ` error: ${r.errorMessage.slice(0, 160)}` : ""}`;
    });
    return `PROJECT ${p.name}${p.isSample ? " (sample)" : ""} · mode ${p.mode} · live ${p.liveUrl ?? "none"}\n${runs.join("\n") || "  (no runs)"}`;
  });
  return { scope: "portfolio", context: `Today is ${new Date().toISOString().slice(0, 10)}.\n${lines.join("\n")}` };
}
