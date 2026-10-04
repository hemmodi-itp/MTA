import { prisma } from "@/lib/db";
import { mapRun, RUN_SELECT } from "@/lib/api/server/mappers";
import { requireUser, visibleRuns } from "@/lib/api/server/access";
import { pageArgs, pageResponse, readPage } from "@/lib/api/server/pagination";

/** Visible runs, newest first. `?limit=` (default 200, max 500) and `?cursor=` page through older runs. */
export async function GET(request: Request) {
  const { user, response } = await requireUser();
  if (response) return response;
  const { page, response: bad } = readPage(new URL(request.url), 200, 500);
  if (bad) return bad;
  const runs = await prisma.run.findMany({
    where: visibleRuns(user.id),
    select: RUN_SELECT,
    orderBy: [{ startedAt: "desc" }, { id: "desc" }],
    ...pageArgs(page),
  });
  return pageResponse(runs, page, mapRun);
}
