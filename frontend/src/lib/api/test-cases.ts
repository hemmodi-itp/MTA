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

export async function fetchScenarios(runId?: string): Promise<Scenario[]> {
  return json(await fetch(withRunId("/api/scenarios", runId), { cache: "no-store" }));
}

export async function fetchRecommendations(runId?: string): Promise<Recommendation[]> {
  return json(await fetch(withRunId("/api/recommendations", runId), { cache: "no-store" }));
}
