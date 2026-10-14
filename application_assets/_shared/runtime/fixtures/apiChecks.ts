// apiChecks.ts — helpers for the generated API specs (Phase 8.1, tools/whitebox/api_tests.py).

import { expect } from '@playwright/test';

export type StatusSpec = number | '2xx' | '3xx' | '4xx' | '5xx' | 'success' | '<500';

interface ResLike {
  status(): number;
  headers(): Record<string, string>;
  text(): Promise<string>;
}

/** 201 / "2xx" / "4xx" / "success" (2xx or 3xx) / "<500" (anything but a server error). */
export function statusOk(actual: number, spec: StatusSpec): boolean {
  if (typeof spec === 'number') return actual === spec;
  if (spec === 'success') return actual >= 200 && actual < 400;
  if (spec === '<500') return actual < 500;
  return Math.floor(actual / 100) === Number(spec[0]);
}

export async function expectStatus(res: ResLike, spec: StatusSpec | StatusSpec[], what: string): Promise<void> {
  const specs = Array.isArray(spec) ? spec : [spec];
  const got = res.status();
  const body = specs.some((s) => statusOk(got, s)) ? '' : (await res.text().catch(() => '')).slice(0, 300);
  expect(specs.some((s) => statusOk(got, s)), `${what}: got HTTP ${got}, expected ${specs.join(' or ')} ${body}`).toBe(true);
}

/** A redirect to the login page (a session-protected page asked for without a session). */
export function expectLoginRedirect(res: ResLike, what: string): void {
  const loc = res.headers()['location'] ?? '';
  expect(res.status() >= 300 && res.status() < 400 && /login/i.test(loc) || res.status() === 401,
    `${what}: expected a redirect to the login page or 401, got HTTP ${res.status()} ${loc}`).toBe(true);
}

/** Signed out: a redirect to the login page, or any 4xx — anything but doing what was asked. */
export function expectNotAllowed(res: ResLike, what: string): void {
  const s = res.status();
  const loc = res.headers()['location'] ?? '';
  const refused = (s >= 300 && s < 400 && /login/i.test(loc)) || (s >= 400 && s < 500);
  expect(refused, `${what}: expected a login redirect or a 4xx, got HTTP ${s} ${loc}`).toBe(true);
}

export async function expectJsonKeys(res: ResLike, keys: string[], what: string): Promise<void> {
  let body: any;
  try {
    body = JSON.parse(await res.text());
  } catch {
    throw new Error(`${what}: the response is not JSON`);
  }
  const missing = keys.filter((k) => body === null || typeof body !== 'object' || !(k in body));
  expect(missing, `${what}: response is missing key(s)`).toEqual([]);
}

/** Unique value for a created record (a re-run never collides with an earlier one). */
export function uniq(prefix: string, maxLength = 50): string {
  const tail = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;
  return `${prefix}${tail}`.slice(0, Math.max(maxLength, 1));
}

/** Text of exactly `n` characters, unique per call. */
export function sized(n: number): string {
  if (n <= 0) return '';
  const head = uniq('L', n);
  return (head + 'x'.repeat(n)).slice(0, n);
}

/** The top-level keys of each JSON error body — the generated spec warns when they differ between endpoints. */
export async function errorShape(res: ResLike): Promise<string> {
  try {
    const body = JSON.parse(await res.text());
    return body && typeof body === 'object' ? Object.keys(body).sort().join(',') : typeof body;
  } catch {
    return 'not-json';
  }
}
