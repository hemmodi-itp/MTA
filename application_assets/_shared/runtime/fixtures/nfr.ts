// nfr.ts — Phase 7 non-functional checks used by the generated NFR specs (tools/nonfunctional/*).
//
// Pure rules (unit-tested) + small in-page probes. Every check returns Findings; a generated spec fails on level
// 'fail' and records 'warn' findings as annotations. Nothing here sends an attack payload — the active security
// probes live in the generated security_active spec and run only when the project allows them.

import type { Page } from '@playwright/test';

export type Level = 'fail' | 'warn';
export interface Finding { rule: string; message: string; level: Level }

const f = (rule: string, message: string, level: Level = 'fail'): Finding => ({ rule, message, level });

// ── 7.1 accessibility: accepted-issues baseline, keyboard, form errors ──────────────────────────────────────────

export interface AxeViolation { id: string; impact?: string | null; help?: string; nodes?: unknown[] }
export interface AcceptedIssue { rule: string; url_template?: string; reason?: string }

/** axe violations -> findings: critical/serious fail, moderate/minor warn; accepted (rule [+ page]) issues are dropped. */
export function a11yFindings(violations: AxeViolation[], urlTemplate: string, accepted: AcceptedIssue[] = []): Finding[] {
  const isAccepted = (v: AxeViolation) =>
    accepted.some((a) => a.rule === v.id && (!a.url_template || a.url_template === urlTemplate));
  return violations.filter((v) => !isAccepted(v)).map((v) => f(
    `axe:${v.id}`, `${v.help ?? v.id} (${v.impact ?? 'unknown'}, ${v.nodes?.length ?? 0} node(s))`,
    v.impact === 'critical' || v.impact === 'serious' ? 'fail' : 'warn'));
}

export interface KeyboardResult {
  focusable: string[];
  reached: string[];
  invisible: string[];
  trapped: string | null;
}

/** Tab through the page (at most `maxTabs`): which interactive elements are reached, which show no focus, any trap. */
export async function keyboardWalk(page: Page, maxTabs = 80): Promise<KeyboardResult> {
  const focusable: string[] = await page.evaluate(() => {
    const sel = 'a[href], button, input:not([type=hidden]), select, textarea, [tabindex]:not([tabindex="-1"]), summary';
    const out: string[] = [];
    document.querySelectorAll(sel).forEach((el, i) => {
      const h = el as HTMLElement;
      const r = h.getBoundingClientRect();
      if ((h as HTMLButtonElement).disabled || r.width === 0 || r.height === 0 || h.closest('[inert], [aria-hidden=true]')) return;
      h.setAttribute('data-mta-kb', String(i));
      out.push(String(i));
    });
    return out;
  });
  const label = (k: string) => page.evaluate((key) => {
    const el = document.querySelector(`[data-mta-kb="${key}"]`) as HTMLElement | null;
    if (!el) return key;
    const name = el.getAttribute('aria-label') || (el.textContent || '').trim() || el.getAttribute('name') || el.id;
    return `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''} "${(name || '').slice(0, 40)}"`;
  }, k);
  const reached: string[] = [];
  const invisible: string[] = [];
  let trapped: string | null = null;
  let last: string | null = null;
  let same = 0;
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  for (let i = 0; i < maxTabs; i++) {
    await page.keyboard.press('Tab');
    const cur = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return null;
      const s = getComputedStyle(el);
      const ring = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none';
      return { key: el.getAttribute('data-mta-kb'), visible: el.matches(':focus-visible') && ring };
    });
    if (!cur || !cur.key) { last = null; continue; }
    if (cur.key === last) {
      if (++same >= 3 && focusable.length > 1) { trapped = await label(cur.key); break; }
      continue;
    }
    same = 0;
    if (reached.includes(cur.key)) break;            // wrapped around: every reachable element has been seen
    reached.push(cur.key);
    if (!cur.visible) invisible.push(cur.key);
    last = cur.key;
  }
  const names = async (keys: string[]) => Promise.all(keys.map(label));
  return { focusable: await names(focusable), reached: await names(reached), invisible: await names(invisible), trapped };
}

export function keyboardFindings(r: KeyboardResult): Finding[] {
  const out: Finding[] = [];
  const unreached = r.focusable.filter((x) => !r.reached.includes(x));
  if (r.trapped) out.push(f('keyboard-trap', `focus is trapped on ${r.trapped}`));
  for (const x of unreached) out.push(f('keyboard-unreachable', `${x} cannot be reached with Tab`));
  for (const x of r.invisible) out.push(f('focus-visible', `${x} shows no visible focus indicator`, 'warn'));
  return out;
}

export interface FormErrorState { announced: boolean; focusOnInvalid: boolean; invalidCount: number }

/** After a submit with every field empty: is an error announced (role=alert / aria-live, or the browser's native
 *  validation message) and is focus on an invalid field? */
export async function formErrorState(page: Page): Promise<FormErrorState> {
  return page.evaluate(() => {
    const live = [...document.querySelectorAll('[role=alert], [aria-live=assertive], [aria-live=polite]')]
      .some((el) => (el.textContent || '').trim().length > 0 && (el as HTMLElement).offsetParent !== null);
    const invalid = [...document.querySelectorAll('input, select, textarea')]
      .filter((el) => el.getAttribute('aria-invalid') === 'true' || (el as HTMLInputElement).matches(':invalid'));
    // the browser's own constraint validation (form without novalidate) shows and announces its message itself
    const native = invalid.some((el) => !(el as HTMLInputElement).form?.noValidate && !!(el as HTMLInputElement).validationMessage);
    const active = document.activeElement;
    return { announced: live || native, focusOnInvalid: !!active && invalid.includes(active as Element), invalidCount: invalid.length };
  });
}

export function formErrorFindings(s: FormErrorState, form: string): Finding[] {
  const out: Finding[] = [];
  if (!s.announced) out.push(f('form-error-announced', `${form}: a rejected submit shows no role=alert / aria-live message`));
  if (s.invalidCount && !s.focusOnInvalid) out.push(f('form-error-focus', `${form}: focus does not move to the first invalid field`, 'warn'));
  return out;
}

// ── 7.3 performance budgets ─────────────────────────────────────────────────────────────────────────────────────

export type PerfBudget = Partial<Record<'ttfb_ms' | 'fcp_ms' | 'lcp_ms' | 'load_ms' | 'transfer_bytes' | 'requests' | 'cls', number>>;

/** Over a budget -> fail; worse than the baseline by more than `regressionPct` % -> `regressionLevel`. */
export function perfFindings(metrics: Record<string, number | null | string>, budget: PerfBudget = {},
  baseline: Record<string, number | null> | null = null, regressionPct = 50, regressionLevel: Level = 'warn'): Finding[] {
  const out: Finding[] = [];
  for (const [k, limit] of Object.entries(budget)) {
    const v = metrics[k];
    if (typeof v === 'number' && typeof limit === 'number' && v > limit) out.push(f(`budget:${k}`, `${k} ${v} > budget ${limit}`));
  }
  for (const [k, base] of Object.entries(baseline ?? {})) {
    const v = metrics[k];
    if (typeof v !== 'number' || typeof base !== 'number' || base <= 0) continue;
    if (k.endsWith('_ms') && v < 100) continue;          // tiny absolute values: noise, not a regression
    const pct = ((v - base) / base) * 100;
    if (pct > regressionPct) {
      out.push(f(`regression:${k}`, `${k} ${v} is ${Math.round(pct)}% worse than the baseline ${base}`, regressionLevel));
    }
  }
  return out;
}

// ── 7.4 passive security additions ──────────────────────────────────────────────────────────────────────────────

const STACK = [
  /Traceback \(most recent call last\)/, /\bat [\w$.<>]+ \([\w./\\:-]+:\d+:\d+\)/, /\bat (?:java|org|com|sun)\.[\w.$]+\(/,
  /Exception in thread/, /System\.\w+Exception/, /\bSQLSTATE\[/, /You have an error in your SQL syntax/i,
  /ORA-\d{5}/, /PG::\w+Error/, /sqlite3?\.\w*Error/i, /Warning: \w+\(\).*on line \d+/,
];

export function checkStackTrace(body: string, where = 'response'): Finding[] {
  const hit = STACK.find((re) => re.test(body || ''));
  return hit ? [f('stack-trace', `${where} leaks a stack trace / framework error (${hit.source.slice(0, 40)})`)] : [];
}

export function checkMixedContent(pageUrl: string, requestUrls: string[]): Finding[] {
  if (!/^https:/i.test(pageUrl)) return [];
  return [...new Set(requestUrls.filter((u) => /^http:/i.test(u)))]
    .map((u) => f('mixed-content', `https page loads ${u.slice(0, 120)} over http`));
}

export interface LinkLike { href: string; target: string | null; rel: string | null }

export function checkBlankTargets(links: LinkLike[]): Finding[] {
  return links.filter((l) => (l.target || '').toLowerCase() === '_blank' && !/noopener|noreferrer/i.test(l.rel || ''))
    .map((l) => f('target-blank', `link to ${l.href.slice(0, 100)} opens a new tab without rel="noopener"`, 'warn'));
}

export async function collectLinks(page: Page): Promise<LinkLike[]> {
  return page.evaluate(() => [...document.querySelectorAll('a[href]')].map((a) => ({
    href: (a as HTMLAnchorElement).href, target: a.getAttribute('target'), rel: a.getAttribute('rel') })));
}

/** The text a user sees for an error page should not be empty or a raw framework dump. */
export function checkErrorPage(status: number, text: string, where: string): Finding[] {
  const out: Finding[] = [];
  if (status >= 500) out.push(f('server-error', `${where} answered ${status}`));
  out.push(...checkStackTrace(text, where));
  if (!(text || '').trim()) out.push(f('blank-page', `${where} rendered an empty page`));
  return out;
}

// ── 7.5 responsive / compatibility ──────────────────────────────────────────────────────────────────────────────

export interface LayoutResult {
  viewport: number;
  scrollWidth: number;
  offenders: string[];
  smallTargets: string[];
  clipped: string[];
}

export async function layoutProbe(page: Page): Promise<LayoutResult> {
  return page.evaluate(() => {
    const doc = document.documentElement;
    const vw = doc.clientWidth;
    const desc = (el: Element) => `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${(el.getAttribute('data-testid') ? `[data-testid=${el.getAttribute('data-testid')}]` : '')}`;
    const offenders: string[] = [];
    const smallTargets: string[] = [];
    const clipped: string[] = [];
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.right > vw + 1 && offenders.length < 10) offenders.push(`${desc(el)} (right edge ${Math.round(r.right)}px)`);
      if (el.matches('a[href], button, input:not([type=hidden]), select, [role=button]') && (r.width < 24 || r.height < 24)
          && smallTargets.length < 20) smallTargets.push(`${desc(el)} ${Math.round(r.width)}x${Math.round(r.height)}`);
      const s = getComputedStyle(el);
      const he = el as HTMLElement;
      if ((s.overflowX === 'hidden' || s.overflowX === 'clip' || s.textOverflow === 'ellipsis')
          && he.scrollWidth > he.clientWidth + 1 && (he.textContent || '').trim() && clipped.length < 10) clipped.push(desc(el));
    }
    return { viewport: vw, scrollWidth: doc.scrollWidth, offenders, smallTargets, clipped };
  });
}

export function layoutFindings(r: LayoutResult, where: string): Finding[] {
  const out: Finding[] = [];
  if (r.scrollWidth > r.viewport + 1) {
    out.push(f('horizontal-overflow', `${where}: page is ${r.scrollWidth}px wide in a ${r.viewport}px viewport` +
      (r.offenders.length ? ` — ${r.offenders.slice(0, 3).join(', ')}` : '')));
  }
  for (const t of r.smallTargets) out.push(f('touch-target', `${where}: ${t} is smaller than 24x24 px`, 'warn'));
  for (const c of r.clipped) out.push(f('clipped-text', `${where}: text is clipped in ${c}`, 'warn'));
  return out;
}

// ── 7.7 i18n ────────────────────────────────────────────────────────────────────────────────────────────────────

/** Lengthen every visible text node by ~40% (text expansion of translations); returns how many were changed. */
export async function expandText(page: Page, factor = 0.4): Promise<number> {
  return page.evaluate((k) => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n = 0;
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const t = node.nodeValue || '';
      const parent = node.parentElement;
      if (!t.trim() || !parent || ['SCRIPT', 'STYLE', 'TEXTAREA', 'OPTION'].includes(parent.tagName)) continue;
      node.nodeValue = t + 'ẍ'.repeat(Math.ceil(t.trim().length * k));
      n++;
    }
    return n;
  }, factor);
}

/** Flip the document to right-to-left (RTL languages). */
export async function setRtl(page: Page): Promise<void> {
  await page.evaluate(() => document.documentElement.setAttribute('dir', 'rtl'));
}

export const NFC = 'café';          // é as one code point
export const NFD = 'café';         // e + combining acute accent

// ── shared ──────────────────────────────────────────────────────────────────────────────────────────────────────

interface InfoLike {
  outputPath: (...parts: string[]) => string;
  attach: (name: string, opts: { path: string; contentType: string }) => Promise<void>;
}

/** Findings as a file next to the trace and attached by path — the report and the quality gates read it. */
export async function attachFindings(testInfo: InfoLike, name: string, findings: unknown): Promise<void> {
  const fs = await import('fs');
  const file = testInfo.outputPath(name);
  fs.mkdirSync(require('path').dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(findings, null, 2), 'utf8');
  await testInfo.attach(name, { path: file, contentType: 'application/json' });
}

/** Record warn findings as annotations; return the failing ones (the spec asserts they are empty). */
export function split(findings: Finding[], annotations: Array<{ type: string; description: string }>, kind: string): Finding[] {
  for (const w of findings.filter((x) => x.level === 'warn')) annotations.push({ type: `${kind}-warning`, description: `${w.rule}: ${w.message}` });
  return findings.filter((x) => x.level === 'fail');
}
