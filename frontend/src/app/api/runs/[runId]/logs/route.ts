import { NextResponse } from "next/server";
import type { Prisma } from "@prisma/client";
import { prisma } from "@/lib/db";
import { notFound, requireUser, visibleRuns } from "@/lib/api/server/access";
import { mapRunEvent } from "@/lib/api/server/mappers";
import type { RunLogs } from "@/lib/types";

const MAX_EVENTS = 10_000; // first load
const MAX_INCREMENT = 2_000; // per poll; the next poll picks up the rest
const ID_RE = /^[A-Za-z0-9_-]{1,64}$/;
const ISO_RE = /^\d{4}-\d{2}-\d{2}T/;

const badAfter = () =>
  NextResponse.json({ error: "`after` must be the id of an event of this run or an ISO timestamp." }, { status: 400 });

/**
 * The run's log (RunEvent rows, oldest first) for the Logs tab.
 *   ?after=<event id>   only lines after that event — what the client polls with, appending locally
 *   ?after=<ISO time>   only lines newer than that instant
 * Ordered by (createdAt, id) so lines written in the same millisecond are neither skipped nor repeated.
 */
export async function GET(request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { user, response } = await requireUser();
  if (response) return response;
  const { runId } = await params;
  const after = new URL(request.url).searchParams.get("after");

  const run = await prisma.run.findFirst({
    where: { id: runId, ...visibleRuns(user.id) },
    select: { status: true, startedAt: true, finishedAt: true },
  });
  if (!run) return notFound();

  let where: Prisma.RunEventWhereInput = { runId };
  if (after) {
    if (ISO_RE.test(after)) {
      const at = new Date(after);
      if (Number.isNaN(at.getTime())) return badAfter();
      where = { runId, createdAt: { gt: at } };
    } else {
      if (!ID_RE.test(after)) return badAfter();
      const anchor = await prisma.runEvent.findFirst({ where: { id: after, runId }, select: { id: true, createdAt: true } });
      if (!anchor) return badAfter();
      where = { runId, OR: [{ createdAt: { gt: anchor.createdAt } }, { createdAt: anchor.createdAt, id: { gt: anchor.id } }] };
    }
  }

  const events = await prisma.runEvent.findMany({
    where,
    orderBy: [{ createdAt: "asc" }, { id: "asc" }],
    take: after ? MAX_INCREMENT : MAX_EVENTS,
  });
  const body: RunLogs = {
    status: run.status,
    startedAt: run.startedAt.toISOString(),
    finishedAt: run.finishedAt ? run.finishedAt.toISOString() : null,
    events: events.map(mapRunEvent),
  };
  return NextResponse.json(body);
}
