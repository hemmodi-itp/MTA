// consoleGuard.ts — new console errors vs the Phase 2 baseline (Phase 4.4 `consoleGuard` fixture).
//
// The fixture collects console.error messages and page errors (uncaught exceptions) from every page of the test's
// context. At teardown each one is compared with test_comprehension/baseline.json: an error is KNOWN when the same
// normalised text was recorded for a baseline state whose URL path equals the page's path (origin and query are
// ignored); anything else is NEW. execution.console_guard decides what a new error does:
//   off  — nothing is collected
//   warn — (default) annotation `console_new_error` per new error + console-errors.json attachment; status unchanged
//   fail — as warn, and the test fails at teardown listing the new errors
// No baseline file -> warn-only, with a note saying so. Phase 5's verifyNoNewConsoleErrors reads newErrors().

import fs from 'fs';

export type ConsoleGuardMode = 'off' | 'warn' | 'fail';

export interface ConsoleEntry {
  kind: 'console' | 'pageerror';
  text: string;
  url: string;
}

export interface BaselineIndex {
  available: boolean;
  path: string;
  note?: string;
  byPath: Map<string, Set<string>>;
}

const ANSI = /\x1b\[[0-9;]*m/g;

export function normalizeText(text: string): string {
  return String(text ?? '').replace(ANSI, '').replace(/\s+/g, ' ').trim();
}

/** '/products/new' for 'http://host:1/products/new/?x=1#y'; '' when unparsable. */
export function urlPath(url: string): string {
  try {
    const p = new URL(url).pathname.replace(/\/+$/, '');
    return p || '/';
  } catch {
    return '';
  }
}

function entryText(e: unknown): string {
  if (typeof e === 'string') return e;
  if (e && typeof e === 'object') {
    const o = e as Record<string, unknown>;
    return String(o.text ?? o.message ?? '');
  }
  return '';
}

export function indexBaseline(doc: unknown, path = '<baseline>'): BaselineIndex {
  const byPath = new Map<string, Set<string>>();
  const states = doc && typeof doc === 'object' ? (doc as Record<string, any>).states : null;
  if (!states || typeof states !== 'object') {
    return { available: false, path, note: `consoleGuard: ${path} has no states — new-error check is warn-only`, byPath };
  }
  for (const state of Object.values(states) as Array<Record<string, any>>) {
    const key = urlPath(String(state?.url ?? ''));
    const set = byPath.get(key) ?? new Set<string>();
    for (const e of [...(state?.console_errors ?? []), ...(state?.page_errors ?? [])]) {
      const t = normalizeText(entryText(e));
      if (t) set.add(t);
    }
    byPath.set(key, set);
  }
  return { available: true, path, byPath };
}

export function loadBaseline(file: string, read: (f: string) => string | null = defaultRead): BaselineIndex {
  const text = read(file);
  if (text === null) {
    return { available: false, path: file, note: `consoleGuard: no baseline.json at ${file} — new-error check is warn-only`, byPath: new Map() };
  }
  try {
    return indexBaseline(JSON.parse(text), file);
  } catch {
    return { available: false, path: file, note: `consoleGuard: ${file} is not valid JSON — new-error check is warn-only`, byPath: new Map() };
  }
}

function defaultRead(file: string): string | null {
  try {
    return fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null;
  } catch {
    return null;
  }
}

export function isKnown(entry: ConsoleEntry, baseline: BaselineIndex): boolean {
  return baseline.byPath.get(urlPath(entry.url))?.has(normalizeText(entry.text)) ?? false;
}

export class ConsoleGuard {
  private readonly entries: ConsoleEntry[] = [];
  private readonly expected: RegExp[] = [];

  constructor(readonly baseline: BaselineIndex, readonly mode: ConsoleGuardMode) {}

  /**
   * Phase 5 fault injection: console errors the test itself provoked (a mocked 503, going offline) are expected,
   * not new. Only `console` entries can match; page errors (uncaught exceptions) always count.
   */
  expectConsoleError(pattern: RegExp): void {
    this.expected.push(pattern);
  }

  private isExpected(e: ConsoleEntry): boolean {
    return e.kind === 'console' && this.expected.some((re) => re.test(e.text));
  }

  /** The mode that applies: fail without a baseline is downgraded to warn. */
  get effectiveMode(): ConsoleGuardMode {
    return this.mode === 'fail' && !this.baseline.available ? 'warn' : this.mode;
  }

  record(entry: ConsoleEntry): void {
    if (this.mode === 'off') return;
    this.entries.push({ ...entry, text: normalizeText(entry.text) });
  }

  errors(): ConsoleEntry[] {
    return [...this.entries];
  }

  newErrors(): ConsoleEntry[] {
    return this.entries.filter((e) => !isKnown(e, this.baseline) && !this.isExpected(e));
  }

  knownErrors(): ConsoleEntry[] {
    return this.entries.filter((e) => isKnown(e, this.baseline) || this.isExpected(e));
  }

  /** The failure message for mode fail, or null. */
  failureMessage(): string | null {
    if (this.effectiveMode !== 'fail') return null;
    const fresh = this.newErrors();
    if (!fresh.length) return null;
    const lines = fresh.slice(0, 10).map((e) => `  - [${e.kind}] ${urlPath(e.url) || e.url}: ${e.text.slice(0, 300)}`);
    return `consoleGuard: ${fresh.length} new console error(s) not in baseline.json:\n${lines.join('\n')}`;
  }
}
