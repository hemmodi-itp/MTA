// safety.ts — runtime host allow-list (Phase 0.5), mirroring tools/safety/hosts.py.
//
// UIExecutionAgent sets MTA_ALLOWED_HOSTS (comma-separated host[:port] /
// *.suffix entries) from project.yaml `safety.allowed_hosts` (or the hosts of
// the project's own URLs). A navigation outside the list fails the step.
// When the variable is absent (a hand-run `npx playwright test`), nothing is
// enforced, and a single warning is printed.

export class SafetyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SafetyError';
  }
}

// chrome-error: is the browser's own page for a load that failed (offline, refused) — not a foreign host
const NEUTRAL_SCHEMES = new Set(['about:', 'data:', 'blob:', 'chrome-error:']);
const WEB_SCHEMES = new Set(['http:', 'https:']);

export function parseAllowedHosts(raw: string | undefined): string[] | null {
  if (raw === undefined) return null;
  return raw
    .split(',')
    .map((h) => h.trim().toLowerCase())
    .filter(Boolean);
}

function hostMatches(hostname: string, port: string, allowed: string[]): boolean {
  const host = hostname.toLowerCase();
  for (const entry of allowed) {
    let aHost = entry;
    let aPort = '';
    const m = entry.match(/^(.*):(\d+)$/);
    if (m) {
      aHost = m[1];
      aPort = m[2];
    }
    if (aPort && aPort !== port) continue;
    if (aHost.startsWith('*.')) {
      const suffix = aHost.slice(1);
      if (host.endsWith(suffix) && host !== aHost.slice(2)) return true;
    } else if (host === aHost) {
      return true;
    }
  }
  return false;
}

/** True when `url` (absolute, or relative to `baseUrl`) stays inside `allowed`. */
export function isUrlAllowed(url: string | undefined, allowed: string[] | null, baseUrl?: string): boolean {
  if (allowed === null) return true; // not enforced
  const text = (url ?? '').trim();
  let parsed: URL;
  try {
    parsed = new URL(text, baseUrl || undefined);
  } catch {
    // Relative with no base to resolve against: it resolves against the
    // configured baseURL at goto() time, which is itself allow-listed.
    return !/^[a-z][a-z0-9+.-]*:/i.test(text);
  }
  if (NEUTRAL_SCHEMES.has(parsed.protocol)) return true;
  if (!WEB_SCHEMES.has(parsed.protocol)) return false;
  return hostMatches(parsed.hostname, parsed.port, allowed);
}

let warned = false;

/** Allow-list from the environment; warns once when it is not configured. */
export function allowedHostsFromEnv(env: Record<string, string | undefined> = process.env): string[] | null {
  const allowed = parseAllowedHosts(env.MTA_ALLOWED_HOSTS);
  if (allowed === null && !warned) {
    warned = true;
    // eslint-disable-next-line no-console
    console.warn('[MTA safety] MTA_ALLOWED_HOSTS is not set — host allow-list not enforced for this run');
  }
  return allowed;
}

export function assertUrlAllowed(url: string | undefined, allowed: string[] | null, baseUrl?: string): void {
  if (!isUrlAllowed(url, allowed, baseUrl)) {
    throw new SafetyError(
      `navigation to '${url}' is outside safety.allowed_hosts [${(allowed ?? []).join(', ')}]`,
    );
  }
}
