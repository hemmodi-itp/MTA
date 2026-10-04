import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { mapRun, RUN_SELECT } from "@/lib/api/server/mappers";
import { notFound, requireUser, visibleRuns } from "@/lib/api/server/access";

export async function GET(_request: Request, { params }: { params: Promise<{ runId: string }> }) {
  const { user, response } = await requireUser();
  if (response) return response;
  const { runId } = await params;
  const run = await prisma.run.findFirst({
    where: { id: runId, ...visibleRuns(user.id) },
    select: RUN_SELECT,
  });
  if (!run) return notFound();
  return NextResponse.json(mapRun(run));
}
