import { prisma } from "@/lib/db";
import { mapTestCase } from "@/lib/api/server/mappers";
import { requireUser, visibleRuns } from "@/lib/api/server/access";
import { pageArgs, pageResponse, readPage } from "@/lib/api/server/pagination";

/**
 * Test cases. With `?runId=` the run's tests (one page of up to 2000 covers any real run);
 * without it, every visible test in pages of `?limit=` (default 200, max 500) — follow the X-Next-Cursor header.
 */
export async function GET(request: Request) {
  const { user, response } = await requireUser();
  if (response) return response;
  const url = new URL(request.url);
  const runId = url.searchParams.get("runId") ?? undefined;
  const { page, response: bad } = readPage(url, runId ? 2000 : 200, runId ? 2000 : 500);
  if (bad) return bad;
  const rows = await prisma.testCase.findMany({
    where: { ...(runId ? { runId } : {}), run: visibleRuns(user.id) },
    orderBy: [{ scenarioTitle: "asc" }, { id: "asc" }],
    ...pageArgs(page),
  });
  return pageResponse(rows, page, mapTestCase);
}
