import type { Project } from "@/lib/types";
import type { NewProjectInput } from "@/lib/validation/project";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

/** Error from the API carrying per-field messages the form can display. */
export class ApiError extends Error {
  constructor(message: string, public fieldErrors: Record<string, string[] | undefined> = {}) {
    super(message);
  }
}

export async function fetchProjects(): Promise<Project[]> {
  return json(await fetch("/api/projects", { cache: "no-store" }));
}

export async function fetchProject(id: string): Promise<Project | undefined> {
  const res = await fetch(`/api/projects/${id}`, { cache: "no-store" });
  if (res.status === 404) return undefined;
  return json(res);
}

export type CreateProjectInput = NewProjectInput;

export interface StartRunResult {
  runId: string;
  backendReachable?: boolean;
  alreadyRunning?: boolean;
}

export async function createProject(input: CreateProjectInput): Promise<StartRunResult & { project: Project }> {
  const res = await fetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(body.error ?? `Request failed: ${res.status}`, body.fieldErrors ?? {});
  return body;
}

export async function rerunProject(projectId: string): Promise<StartRunResult> {
  const res = await fetch(`/api/projects/${projectId}/runs`, { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(body.error ?? `Request failed: ${res.status}`);
  return body;
}

/** Remove the project's stored live-app test account (owner only). */
export async function deleteLiveAuth(projectId: string): Promise<Project> {
  const res = await fetch(`/api/projects/${projectId}/live-auth`, { method: "DELETE" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(body?.error ?? "Could not remove the test login.");
  return body;
}
