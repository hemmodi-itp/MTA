import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { notFound, requireUser } from "@/lib/api/server/access";
import { ACTIVE_RUN_STATUSES } from "@/lib/run-status";
import type { RunStatus } from "@/lib/types";

const CANCELLED_MESSAGE = "Cancelled by the user";
const IN_FLIGHT: RunStatus[] = ACTIVE_RUN_STATUSES.filter((s) => s !== "queued");

/**
 * Cancel a run (owner only; sample and other users' runs 404).
 *   queued  → cancelled now (the service only ever claims queued runs, with a conditional UPDATE, so this can't race it)
 *   active  → cancelRequested = true; the service stops at its next checkpoint and sets status "cancelled"
 *   finished → 409
 */
export async function POST(_request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { user, response } = await requireUser();
  if (response) return response;
  const { runId } = await params;
  const run = await prisma.run.findFirst({
    where: { id: runId, project: { userId: user.id } },
    select: { id: true, projectId: true, startedAt: true },
  });
  if (!run) return notFound();

  const now = new Date();
  const dequeued = await prisma.run.updateMany({
    where: { id: run.id, status: "queued" },
    data: { status: "cancelled", finishedAt: now, errorMessage: CANCELLED_MESSAGE, cancelRequested: true },
  });
  if (dequeued.count) {
    await prisma.$transaction([
      prisma.runEvent.create({ data: { runId: run.id, level: "warning", message: `${CANCELLED_MESSAGE} before it started.` } }),
      // only if this is the project's newest run, so an older cancelled run never masks a newer result
      prisma.project.updateMany({
        where: { id: run.projectId, runs: { none: { startedAt: { gt: run.startedAt } } } },
        data: { lastRunStatus: "cancelled" },
      }),
    ]);
    return NextResponse.json({ status: "cancelled", cancelRequested: true });
  }

  const requested = await prisma.run.updateMany({
    where: { id: run.id, status: { in: IN_FLIGHT }, cancelRequested: false },
    data: { cancelRequested: true },
  });
  if (requested.count) {
    await prisma.runEvent.create({
      data: { runId: run.id, level: "warning", message: "Cancellation requested. The evaluation stops at its next checkpoint." },
    });
  }

  const current = await prisma.run.findUniqueOrThrow({ where: { id: run.id }, select: { status: true, cancelRequested: true } });
  if (!(IN_FLIGHT as string[]).includes(current.status) && current.status !== "cancelled") {
    return NextResponse.json({ error: `This run has already ${current.status === "failed" ? "failed" : "finished"}.` }, { status: 409 });
  }
  return NextResponse.json({ status: current.status, cancelRequested: current.cancelRequested }, { status: 202 });
}
