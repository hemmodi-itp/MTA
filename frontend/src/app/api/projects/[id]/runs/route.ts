import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { startEvaluationRun } from "@/lib/api/server/evaluation";
import { checkLiveUrl } from "@/lib/api/server/url-safety";
import { getCurrentUser } from "@/lib/auth/session";

/** Re-run the evaluation for an existing project with its saved settings (or return the run already in flight). */
export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "Please log in again." }, { status: 401 });

  const { id } = await params;
  // Only the owner can start runs; sample projects are read-only demos.
  const project = await prisma.project.findFirst({ where: { id, userId: user.id } });
  if (!project) {
    const sample = await prisma.project.findFirst({ where: { id, isSample: true }, select: { id: true } });
    return sample
      ? NextResponse.json({ error: "Sample projects are read-only. Submit your own agent to run an evaluation." }, { status: 403 })
      : NextResponse.json({ error: "Project not found." }, { status: 404 });
  }

  // DNS can change after submission: the saved live URL must still be a public target.
  if (project.mode !== "brd_only" && project.liveUrl) {
    const urlError = await checkLiveUrl(project.liveUrl);
    if (urlError) return NextResponse.json({ error: `Live URL rejected: ${urlError}` }, { status: 422 });
  }

  const { runId, backendReachable, alreadyRunning } = await startEvaluationRun(project);
  if (alreadyRunning) return NextResponse.json({ runId, alreadyRunning: true });
  return NextResponse.json({ runId, backendReachable }, { status: 201 });
}
