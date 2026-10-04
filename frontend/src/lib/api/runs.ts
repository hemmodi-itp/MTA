import type { ActivityEvent, Run, RunArtifacts, RunLogs, RunProgress } from "@/lib/types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

export async function fetchRuns(): Promise<Run[]> {
  return json(await fetch("/api/runs", { cache: "no-store" }));
}

export async function fetchRun(id: string): Promise<Run | undefined> {
  const res = await fetch(`/api/runs/${id}`, { cache: "no-store" });
  if (res.status === 404) return undefined;
  return json(res);
}

export async function fetchRunProgress(id: string): Promise<RunProgress> {
  return json(await fetch(`/api/runs/${id}/progress`, { cache: "no-store" }));
}

export async function fetchActivity(): Promise<ActivityEvent[]> {
  return json(await fetch("/api/activity", { cache: "no-store" }));
}

/** The run log; with `after` (an event id) only the lines after it. Throws LogCursorError when the server rejects `after`. */
export async function fetchRunLogs(id: string, after?: string): Promise<RunLogs> {
  const res = await fetch(`/api/runs/${id}/logs${after ? `?after=${encodeURIComponent(after)}` : ""}`, { cache: "no-store" });
  if (res.status === 400 && after) throw new LogCursorError();
  return json(res);
}

export class LogCursorError extends Error {
  constructor() {
    super("Log cursor no longer valid");
  }
}

export interface CancelRunResult {
  status: string;
  cancelRequested: boolean;
}

export async function cancelRun(id: string): Promise<CancelRunResult> {
  const res = await fetch(`/api/runs/${id}/cancel`, { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error ?? `Request failed: ${res.status}`);
  return body;
}

export async function fetchRunArtifacts(id: string): Promise<RunArtifacts> {
  return json(await fetch(`/api/runs/${id}/artifacts`, { cache: "no-store" }));
}
