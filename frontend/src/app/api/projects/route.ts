import { NextResponse } from "next/server";
import { z } from "zod";
import { prisma } from "@/lib/db";
import { mapProject } from "@/lib/api/server/mappers";
import { checkPublicRepo } from "@/lib/api/server/github";
import { lockKey, nudgeBackend, queueRunLocked } from "@/lib/api/server/evaluation";
import { checkLiveUrl } from "@/lib/api/server/url-safety";
import { getCurrentUser } from "@/lib/auth/session";
import { newProjectSchema } from "@/lib/validation/project";
import { encryptJson } from "@/lib/api/server/secrets";
import { requireUser, visibleProjects } from "@/lib/api/server/access";

/** Sample projects + the signed-in user's own projects. */
export async function GET() {
  const { user, response } = await requireUser();
  if (response) return response;
  const projects = await prisma.project.findMany({ where: visibleProjects(user.id), orderBy: { updatedAt: "desc" } });
  return NextResponse.json(projects.map(mapProject));
}

/**
 * Submit an agent repo for evaluation: validate, confirm the repo is public and the live URL is a public target,
 * upsert the Project (one per user + repo, DB-unique) and queue a Run for the Python pipeline — unless the project
 * already has a queued or running evaluation, which is returned instead (`alreadyRunning`). Both steps run under
 * advisory locks, so double submits can't create twin projects or twin runs.
 */
export async function POST(request: Request) {
  const user = await getCurrentUser();
  if (!user) return NextResponse.json({ error: "Please log in again." }, { status: 401 });

  const parsed = newProjectSchema.safeParse(await request.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Please fix the highlighted fields.", fieldErrors: z.flattenError(parsed.error).fieldErrors },
      { status: 400 }
    );
  }
  const input = parsed.data;
  const githubUrl = input.githubUrl.replace(/\.git$/, "").replace(/\/$/, "");

  const liveUrl = input.mode === "brd_only" ? null : input.liveUrl || null;
  if (liveUrl) {
    const urlError = await checkLiveUrl(liveUrl);
    if (urlError) return NextResponse.json({ error: urlError, fieldErrors: { liveUrl: [urlError] } }, { status: 422 });
  }

  const repo = await checkPublicRepo(githubUrl);
  if (!repo.ok) {
    return NextResponse.json({ error: repo.error, fieldErrors: { githubUrl: [repo.error] } }, { status: 422 });
  }

  let liveAuth: string | undefined;
  if (input.mode !== "brd_only" && input.liveUsername && input.livePassword) {
    try {
      // Only overwrite the stored test account when a new one is given; never store it in plaintext.
      liveAuth = encryptJson({ username: input.liveUsername, password: input.livePassword });
    } catch {
      return NextResponse.json(
        { error: "The test login can't be stored: the server has no AQP_SECRET_KEY configured. Leave it empty or ask an admin." },
        { status: 500 }
      );
    }
  }

  const data = {
    name: repo.fullName,
    githubUrl,
    branch: input.branch || repo.defaultBranch || "main",
    mode: input.mode,
    liveUrl,
    brdPath: input.mode === "live_only" ? null : input.brdPath || null,
    ...(liveAuth ? { liveAuth } : {}),
  };

  const { project, runId, alreadyRunning } = await prisma.$transaction(async (tx) => {
    await lockKey(tx, `repo:${user.id}:${githubUrl}`);
    const existing = await tx.project.findUnique({ where: { userId_githubUrl: { userId: user.id, githubUrl } }, select: { id: true } });
    const saved = existing
      ? await tx.project.update({ where: { id: existing.id }, data })
      : await tx.project.create({ data: { ...data, userId: user.id, lastRunStatus: "queued" } });
    await lockKey(tx, `project:${saved.id}`);
    return { project: saved, ...(await queueRunLocked(tx, saved)) };
  });

  // An evaluation of this repo is already queued/running: the new settings are saved for the next run.
  if (alreadyRunning) {
    return NextResponse.json({ project: mapProject(project), runId, alreadyRunning: true, backendReachable: true });
  }
  const backendReachable = await nudgeBackend(runId);
  return NextResponse.json({ project: mapProject(project), runId, backendReachable, alreadyRunning: false }, { status: 201 });
}
