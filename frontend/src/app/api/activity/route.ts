import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { requireUser, visibleRuns } from "@/lib/api/server/access";

/** The newest pipeline events across the user's visible runs, for the dashboard's live activity timeline. */
export async function GET() {
  const { user, response } = await requireUser();
  if (response) return response;
  const events = await prisma.runEvent.findMany({
    where: { run: visibleRuns(user.id), level: { in: ["success", "warning", "error"] } },
    orderBy: { createdAt: "desc" },
    take: 40,
    select: { id: true, createdAt: true, level: true, stage: true, message: true,
      run: { select: { id: true, project: { select: { name: true } } } } },
  });
  return NextResponse.json(events.map((e) => ({
    id: e.id, createdAt: e.createdAt.toISOString(), level: e.level, stage: e.stage, message: e.message,
    runId: e.run.id, projectName: e.run.project.name,
  })));
}
