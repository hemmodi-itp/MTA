import { NextResponse } from "next/server";
import type { Prisma } from "@prisma/client";
import { getCurrentUser, type CurrentUser } from "@/lib/auth/session";

/**
 * Per-user visibility: a user sees the shared sample (demo) projects plus the projects
 * they submitted themselves — never another user's. Every API route that reads project,
 * run or test data filters through these helpers.
 */
export function visibleProjects(userId: string): Prisma.ProjectWhereInput {
  return { OR: [{ isSample: true }, { userId }] };
}

export function visibleRuns(userId: string): Prisma.RunWhereInput {
  return { project: visibleProjects(userId) };
}

type AuthResult = { user: CurrentUser; response?: never } | { user?: never; response: NextResponse };

/** Resolve the signed-in user, or a 401 response to return as-is. */
export async function requireUser(): Promise<AuthResult> {
  const user = await getCurrentUser();
  if (!user) return { response: NextResponse.json({ error: "Please log in again." }, { status: 401 }) };
  return { user };
}

/** 404 rather than 403 for things the user can't see, so ids of other users' runs don't leak. */
export const notFound = () => NextResponse.json(null, { status: 404 });
