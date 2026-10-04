import { prisma } from "@/lib/db";
import { requireUser, visibleRuns } from "@/lib/api/server/access";
import { pageArgs, pageResponse, readPage } from "@/lib/api/server/pagination";

/** Scenarios of one run (`?runId=`) or of every visible run, paged with `?limit=` / `?cursor=`. */
export async function GET(request: Request) {
  const { user, response } = await requireUser();
  if (response) return response;
  const url = new URL(request.url);
  const runId = url.searchParams.get("runId") ?? undefined;
  const { page, response: bad } = readPage(url, runId ? 500 : 100, 500);
  if (bad) return bad;
  const rows = await prisma.scenario.findMany({
    where: { ...(runId ? { runId } : {}), run: visibleRuns(user.id) },
    orderBy: { id: "asc" },
    ...pageArgs(page),
  });
  return pageResponse(rows, page, (r) => r);
}
