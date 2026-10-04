import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { notFound, requireUser, visibleRuns } from "@/lib/api/server/access";
import { mapRunEvent, mapRunStep } from "@/lib/api/server/mappers";
import { isActiveStatus } from "@/lib/run-status";
import type { RunProgress } from "@/lib/types";

const MAX_EVENTS = 400;
const HISTORY_ROWS = 300; // recent finished steps used for the time-remaining estimate (RunStep status+finishedAt index)
const ESTIMATE_TTL_MS = 60_000;

/** Live pipeline state for the run view — polled every few seconds while active. */
export async function GET(_request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { user, response } = await requireUser();
  if (response) return response;
  const { runId } = await params;
  const run = await prisma.run.findFirst({
    where: { id: runId, ...visibleRuns(user.id) },
    select: {
      status: true,
      currentStage: true,
      projectId: true,
      startedAt: true,
      finishedAt: true,
      steps: { orderBy: { position: "asc" } },
      events: { orderBy: { createdAt: "desc" }, take: MAX_EVENTS },
    },
  });
  if (!run) return notFound();

  const body: RunProgress = {
    status: run.status,
    currentStage: run.currentStage,
    startedAt: run.startedAt.toISOString(),
    finishedAt: run.finishedAt ? run.finishedAt.toISOString() : null,
    steps: run.steps.map(mapRunStep),
    events: run.events.reverse().map(mapRunEvent),
    estimates: isActiveStatus(run.status) ? await stepEstimates(run.projectId) : {},
  };
  return NextResponse.json(body);
}

// Medians move slowly, and every open run view polls this: compute once a minute per project, not per poll.
const estimateCache = new Map<string, { at: number; value: Promise<Record<string, number>> }>();

function stepEstimates(projectId: string): Promise<Record<string, number>> {
  const now = Date.now();
  const hit = estimateCache.get(projectId);
  if (hit && now - hit.at < ESTIMATE_TTL_MS) return hit.value;
  for (const [key, entry] of estimateCache) if (now - entry.at >= ESTIMATE_TTL_MS) estimateCache.delete(key);
  const value = computeStepEstimates(projectId).catch((err) => {
    estimateCache.delete(projectId);
    throw err;
  });
  estimateCache.set(projectId, { at: now, value });
  return value;
}

/** Median duration (seconds) per step over recent completed runs — the same repo's runs first (same app, same
 *  test volume), all runs only for steps that repo has no history for. Durations only, no run data. */
async function computeStepEstimates(projectId: string): Promise<Record<string, number>> {
  const where = { status: "success" as const, startedAt: { not: null }, finishedAt: { not: null } };
  const select = { key: true, startedAt: true, finishedAt: true } as const;
  const project = await prisma.project.findUnique({ where: { id: projectId }, select: { githubUrl: true } });
  const [own, all] = await Promise.all([
    prisma.runStep.findMany({ where: { ...where, run: { status: "completed", project: { githubUrl: project?.githubUrl } } },
      orderBy: { finishedAt: "desc" }, take: HISTORY_ROWS, select }),
    prisma.runStep.findMany({ where: { ...where, run: { status: "completed" } }, orderBy: { finishedAt: "desc" }, take: HISTORY_ROWS, select }),
  ]);
  return { ...medians(all, 10), ...medians(own, 5) };
}

function medians(rows: { key: string; startedAt: Date | null; finishedAt: Date | null }[], per: number) {
  const byKey: Record<string, number[]> = {};
  for (const r of rows) {
    const list = (byKey[r.key] ??= []);
    if (list.length < per) list.push((r.finishedAt!.getTime() - r.startedAt!.getTime()) / 1000);
  }
  const out: Record<string, number> = {};
  for (const [key, list] of Object.entries(byKey)) {
    const sorted = [...list].sort((a, b) => a - b);
    out[key] = Math.round(sorted[Math.floor(sorted.length / 2)]);
  }
  return out;
}
