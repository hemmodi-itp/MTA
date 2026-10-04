import type { Prisma, Project } from "@prisma/client";
import { prisma } from "@/lib/db";
import { ACTIVE_RUN_STATUSES } from "@/lib/run-status";

export const BACKEND_URL = process.env.AQP_BACKEND_URL ?? "http://127.0.0.1:8100";

/** Headers for every call to the evaluation service: the shared service token whenever AQP_BACKEND_TOKEN is set. */
export function backendHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return { ...extra, ...(process.env.AQP_BACKEND_TOKEN ? { "X-AQP-Token": process.env.AQP_BACKEND_TOKEN } : {}) };
}

/**
 * Serialise "check for an active run, then create one" per key across concurrent requests (and processes):
 * a transaction-scoped Postgres advisory lock, released at commit/rollback.
 */
export async function lockKey(tx: Prisma.TransactionClient, key: string) {
  await tx.$queryRaw`SELECT 1 FROM pg_advisory_xact_lock(424242, hashtext(${key}))`;
}

/** The project's queued or in-flight run, if any. */
export function findActiveRun(tx: Prisma.TransactionClient, projectId: string) {
  return tx.run.findFirst({
    where: { projectId, status: { in: [...ACTIVE_RUN_STATUSES] } },
    orderBy: { startedAt: "desc" },
    select: { id: true },
  });
}

/**
 * Inside a transaction that already holds `lockKey(tx, "project:<id>")`: the active run if there is one, otherwise a
 * new queued run (settings snapshotted from the project).
 */
export async function queueRunLocked(tx: Prisma.TransactionClient, project: Project): Promise<{ runId: string; alreadyRunning: boolean }> {
  const active = await findActiveRun(tx, project.id);
  if (active) return { runId: active.id, alreadyRunning: true };
  const created = await tx.run.create({
    data: {
      projectId: project.id,
      status: "queued",
      mode: project.mode,
      liveUrl: project.mode === "brd_only" ? null : project.liveUrl,
      brdPath: project.mode === "live_only" ? null : project.brdPath,
    },
    select: { id: true },
  });
  await tx.project.update({ where: { id: project.id }, data: { lastRunStatus: "queued" } });
  return { runId: created.id, alreadyRunning: false };
}

/** Nudge the Python service to start a queued run. It also polls for queued runs, so a failed nudge only delays it. */
export async function nudgeBackend(runId: string): Promise<boolean> {
  let backendReachable = true;
  try {
    const res = await fetch(`${BACKEND_URL}/runs/${runId}/start`, {
      method: "POST",
      headers: backendHeaders(),
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
    });
    backendReachable = res.ok;
  } catch {
    backendReachable = false;
  }

  if (!backendReachable) {
    await prisma.runEvent.create({
      data: {
        runId,
        level: "warning",
        message:
          "The MTA evaluation service is not reachable yet. This run is queued and will start automatically " +
          "once the service is running (python -m uvicorn api.server:app --port 8100).",
      },
    });
  }
  return backendReachable;
}

/**
 * Queue a new evaluation run for a project — unless one is already queued or running, in which case that run is
 * returned with `alreadyRunning: true` (one active run per project, race-free under the project's advisory lock).
 */
export async function startEvaluationRun(project: Project): Promise<{ runId: string; backendReachable: boolean; alreadyRunning: boolean }> {
  const { runId, alreadyRunning } = await prisma.$transaction(async (tx) => {
    await lockKey(tx, `project:${project.id}`);
    return queueRunLocked(tx, project);
  });
  if (alreadyRunning) return { runId, backendReachable: true, alreadyRunning };
  return { runId, backendReachable: await nudgeBackend(runId), alreadyRunning };
}
