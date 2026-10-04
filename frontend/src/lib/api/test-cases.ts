import type { TestCase, Scenario, Recommendation } from "@/lib/types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

function withRunId(path: string, runId?: string) {
  return runId ? `${path}?runId=${encodeURIComponent(runId)}` : path;
}

/** All tests of one run. */
export async function fetchTestCases(runId: string): Promise<TestCase[]> {
  return json(await fetch(withRunId("/api/test-cases", runId), { cache: "no-store" }));
}

/** One page of every visible test case; `nextCursor` is null on the last page. */
export async function fetchTestCasePage(cursor?: string): Promise<{ rows: TestCase[]; nextCursor: string | null }> {
  const res = await fetch(`/api/test-cases?limit=200${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`, { cache: "no-store" });
  const rows = await json<TestCase[]>(res);
  return { rows, nextCursor: res.headers.get("X-Next-Cursor") };
}

export async function fetchTestCase(id: string): Promise<TestCase | undefined> {
  const res = await fetch(`/api/test-cases/${id}`, { cache: "no-store" });
  if (res.status === 404) return undefined;
  return json(res);
}

export async function fetchScenarios(runId?: string): Promise<Scenario[]> {
  return json(await fetch(withRunId("/api/scenarios", runId), { cache: "no-store" }));
}

export async function fetchRecommendations(runId?: string): Promise<Recommendation[]> {
  return json(await fetch(withRunId("/api/recommendations", runId), { cache: "no-store" }));
}
