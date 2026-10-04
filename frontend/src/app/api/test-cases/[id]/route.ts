import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { mapTestCase } from "@/lib/api/server/mappers";
import { notFound, requireUser, visibleRuns } from "@/lib/api/server/access";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { user, response } = await requireUser();
  if (response) return response;
  const { id } = await params;
  const testCase = await prisma.testCase.findFirst({ where: { id, run: visibleRuns(user.id) } });
  if (!testCase) return notFound();
  return NextResponse.json(mapTestCase(testCase));
}
