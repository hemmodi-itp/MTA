import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { mapProject } from "@/lib/api/server/mappers";
import { notFound, requireUser, visibleProjects } from "@/lib/api/server/access";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { user, response } = await requireUser();
  if (response) return response;
  const { id } = await params;
  const project = await prisma.project.findFirst({ where: { id, ...visibleProjects(user.id) } });
  if (!project) return notFound();
  return NextResponse.json(mapProject(project));
}
