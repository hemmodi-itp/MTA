export type RepoCheck =
  | { ok: true; fullName: string; defaultBranch: string | null; verified: boolean }
  | { ok: false; error: string };

export function parseRepo(url: string): { owner: string; repo: string } | null {
  const m = url.trim().match(/^https:\/\/(?:www\.)?github\.com\/([^/]+)\/([^/]+?)(?:\.git)?\/?$/);
  return m ? { owner: m[1], repo: m[2] } : null;
}

/**
 * Confirms the repo is public before a run is queued, so the user gets instant feedback.
 * GitHub answers 404 for both private and missing repos. When GitHub can't be asked
 * (rate limit, network), we let it through unverified — RepoFetchAgent re-checks.
 */
export async function checkPublicRepo(url: string): Promise<RepoCheck> {
  const parsed = parseRepo(url);
  if (!parsed) return { ok: false, error: "Not a GitHub repository URL." };
  const fullName = `${parsed.owner}/${parsed.repo}`;

  const headers: Record<string, string> = { Accept: "application/vnd.github+json", "User-Agent": "agentic-qa-platform" };
  if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;

  try {
    const res = await fetch(`https://api.github.com/repos/${fullName}`, {
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (res.status === 404) {
      return { ok: false, error: `${fullName} was not found or is private. MTA can only evaluate public repositories.` };
    }
    if (!res.ok) return { ok: true, fullName, defaultBranch: null, verified: false };
    const data = (await res.json()) as { private?: boolean; full_name?: string; default_branch?: string };
    if (data.private) return { ok: false, error: `${fullName} is private. MTA can only evaluate public repositories.` };
    return { ok: true, fullName: data.full_name ?? fullName, defaultBranch: data.default_branch ?? null, verified: true };
  } catch {
    return { ok: true, fullName, defaultBranch: null, verified: false };
  }
}
