import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { mapProject } from "@/lib/api/server/mappers";
import { notFound, requireUser } from "@/lib/api/server/access";

/**
 * Remove the project's stored live-app test account. Owner only (samples have no owner); other users' projects 404.
 * Runs that are already in flight keep the login they loaded at start; later runs go without one.
 */
export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { user, response } = await requireUser();
  if (response) return response;
  const { id } = await params;
  const { count } = await prisma.project.updateMany({ where: { id, userId: user.id }, data: { liveAuth: null } });
  if (!count) return notFound();
  const project = await prisma.project.findUniqueOrThrow({ where: { id } });
  return NextResponse.json(mapProject(project));
}
