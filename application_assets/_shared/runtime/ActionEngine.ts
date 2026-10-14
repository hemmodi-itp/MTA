import * as fs from 'fs';
import * as path from 'path';
import { APIRequestContext, expect, Locator, Page, test } from '@playwright/test';
import { Logger } from './Logger';
import { allowedHostsFromEnv, assertUrlAllowed, SafetyError } from './safety';
import type { ConsoleGuard } from './fixtures/consoleGuard';
import type { NetworkLog } from './fixtures/network';
import { Schema, validateSchema } from './fixtures/jsonSchema';
import { classifyStep, DestructivePolicy, LocatorEntryLike, PlanStep, refusalMessage, Rules } from './destructive';

export interface VerifyOptions {
    soft?: boolean;
}

/**
 * Phase 0 safety rails at run time. `allowedHosts` comes from MTA_ALLOWED_HOSTS
 * (null = not enforced); `violations` is filled by the test fixture when the
 * top-level page lands on a host outside the list (redirect, link click) — the
 * next action then fails instead of carrying on against a foreign site.
 */
export interface RuntimeSafety {
    allowedHosts: string[] | null;
    violations: string[];
    /** Violations already raised by an action (the safety fixture fails the test at teardown for the rest). */
    reported?: number;
    /** Phase 4.4: destructive-action guard (tools/safety/destructive_rules.yaml + the project's policy). */
    destructive?: {
        policy: DestructivePolicy;
        rules: Rules | null;
        entryOf: (key: string) => LocatorEntryLike | null | undefined;
    };
}

export interface WaitOptions {
    timeout?: number;
    intervals?: number[];
}

function annotate(type: string, description: string): void {
    try {
        test.info().annotations.push({ type, description });
    } catch {
        // outside a running test (unit tests, flows called from a script) — the log line is enough
    }
}

/** Phase 5 oracle sources (fixtures/testFixture.ts); absent when an ActionEngine is built without them. */
export interface OracleSources {
    network?: NetworkLog;
    consoleGuard?: ConsoleGuard;
    dialogs?: string[];
    /** The `api` fixture (the test's auth + baseURL) — verifyApiState. */
    api?: APIRequestContext;
    /** application_assets/projects/<project> — resolves verifyResponseSchema schemaRef paths. */
    projectDir?: string | null;
    /** locator_map.json entry of a key (Phase 6.1 identity probe reads its `_fingerprint`). */
    entryOf?: (key: string) => { _fingerprint?: Record<string, unknown> } | null | undefined;
}

const CLIENT_ERROR_RESOURCE = /^Failed to load resource: the server responded with a status of 4\d\d\b/;
const NOT_FOUND = /element\(s\) not found|waiting for|Timeout \d+ms exceeded|resolved to 0 elements/i;
let fingerprintSource: string | null | undefined;

/** fixtures/fingerprint.js — the same identity function Python's healing uses (read once per worker). */
function fingerprintJs(): string | null {
    if (fingerprintSource === undefined) {
        try {
            fingerprintSource = fs.readFileSync(path.join(__dirname, 'fixtures', 'fingerprint.js'), 'utf8');
        } catch {
            fingerprintSource = null;
        }
    }
    return fingerprintSource;
}

/**
 * In-page check: is an element with this identity (same role/tag, similar accessible name or same label, visible)
 * on the page? Name similarity = character-bigram Dice coefficient (>= 0.4).
 */
export function probeExpression(fpSource: string, fingerprint: Record<string, unknown>): string {
    return `(() => {
${fpSource}
  const want = ${JSON.stringify(fingerprint)};
  const norm = (t) => String(t || '').replace(/\\s+/g, ' ').trim().toLowerCase();
  const grams = (t) => { const s = norm(t); const out = []; for (let i = 0; i < s.length - 1; i++) out.push(s.slice(i, i + 2)); return out; };
  const dice = (a, b) => {
    if (!norm(a) || !norm(b)) return 0;
    if (norm(a) === norm(b)) return 1;
    const ga = grams(a), gb = grams(b).slice(); let hit = 0;
    for (const g of ga) { const i = gb.indexOf(g); if (i >= 0) { hit++; gb.splice(i, 1); } }
    return (2 * hit) / (ga.length + grams(b).length || 1);
  };
  for (const el of document.querySelectorAll('body *')) {
    if (!el.getClientRects().length) continue;
    const fp = mtaFingerprint(el);
    const sameKind = want.role ? fp.role === want.role : fp.tag === want.tag;
    if (!sameKind) continue;
    if (dice(want.name, fp.name) >= 0.4 || (want.label && norm(want.label) === norm(fp.label))) return true;
  }
  return false;
})()`;
}

/** verifyApiState expectations; every given field must hold. `path` is a dot path into the JSON body ("items.0.name"). */
export interface ApiExpect {
    status?: number | string;
    bodyContains?: string;
    bodyNotContains?: string;
    path?: string;
    equals?: unknown;
    length?: number;
}

export type StorageKind = 'cookie' | 'localStorage' | 'sessionStorage';
export type StorageRule = 'present' | 'absent' | 'equals' | 'contains' | 'httpOnly' | 'secure' | 'sameSite';

export interface MockRouteOptions {
    status?: number;
    body?: unknown;
    contentType?: string;
    delayMs?: number;
}

function patternToRegExp(pattern: string): RegExp {
    return new RegExp(pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*'));
}

/** 200 matches 200; "2xx" matches 200-299. */
export function statusMatches(actual: number | null, expected: number | string): boolean {
    if (actual === null) return false;
    if (typeof expected === 'number') return actual === expected;
    const m = /^([1-5])xx$/i.exec(expected.trim());
    return m ? Math.floor(actual / 100) === Number(m[1]) : actual === Number(expected);
}

export function jsonAtPath(value: unknown, dotPath: string): unknown {
    let cur: any = value;
    for (const part of dotPath.split('.').filter(Boolean)) {
        if (cur === null || cur === undefined) return undefined;
        cur = cur[/^\d+$/.test(part) && Array.isArray(cur) ? Number(part) : part];
    }
    return cur;
}

export class ActionEngine {

    /** Phase 6.1: identity-probe results of this test (also recorded as `locator_probe` annotations). */
    readonly probes: string[] = [];

    /** rememberCount baselines, per locator key (verifyCountChangedBy). */
    private readonly counts = new Map<string, number>();

    constructor(
        private readonly page: Page,
        private readonly pageObject: Record<string, Locator>,
        private readonly pageErrors: string[] = [],
        private readonly safety: RuntimeSafety = { allowedHosts: allowedHostsFromEnv(), violations: [] },
        private readonly oracles: OracleSources = {}
    ) { }

    /**
     * Resolves a locator_key by property lookup on the active Page-object
     * instance (test_creation/pages.ts) — the Page-factory class is the
     * automation center; LocatorManager is an implementation detail used
     * only inside those classes' getters, not called from here directly.
     */
    private resolve(name: string): Locator {
        const locator = this.pageObject[name];
        if (!locator) {
            throw new Error(`ActionEngine: '${name}' is not a property on the active Page object`);
        }
        return locator;
    }

    /**
     * Every action/assertion routes through here so failures are tagged with
     * `[locator_key=...]` — HealingAgent correlates a failure back to the
     * exact locator_map.json entry to repair without parsing generated TS.
     */
    private async run<T>(
        locatorName: string | null,
        action: string,
        value: string | undefined,
        fn: () => Promise<T>,
        step?: PlanStep
    ): Promise<T> {

        Logger.step(action, locatorName ?? undefined, value);

        if (this.safety.violations.length) {
            this.safety.reported = this.safety.violations.length;
            throw new SafetyError(
                `page left safety.allowed_hosts [${(this.safety.allowedHosts ?? []).join(', ')}]: ` +
                this.safety.violations.join(', ')
            );
        }
        if (step) this.guardDestructive(step);

        try {
            const result = await fn();
            Logger.success(
                locatorName ? `${action} on ${locatorName} completed` : `${action} completed`
            );
            return result;
        } catch (err: unknown) {
            const message = err instanceof Error ? err.message : String(err);
            if (locatorName && NOT_FOUND.test(message)) await this.probeIdentity(locatorName);
            throw new Error(
                locatorName ? `[locator_key=${locatorName}] ${message}` : message
            );
        }
    }

    /**
     * Phase 6.1: the element for `key` was not found. Is an element with its recorded identity on the page (the locator
     * drifted — a test defect) or not (the expected element is missing — likely the product)? Recorded as a
     * `locator_probe` annotation that triage reads. Never throws.
     */
    private async probeIdentity(key: string): Promise<void> {
        const fp = this.oracles.entryOf?.(key)?._fingerprint;
        const src = fingerprintJs();
        let note: string;
        if (!fp || !src) {
            note = `${key}: no recorded identity`;
        } else {
            const present = await Promise.race([
                this.page.evaluate(probeExpression(src, fp)).catch(() => null),
                new Promise((r) => setTimeout(() => r(null), 3_000)),
            ]);
            note = present === null ? `${key}: probe failed`
                : present ? `${key}: an element with the same identity is on the page — the locator drifted`
                : `${key}: no element with this identity on the page`;
        }
        this.probes.push(note);
        annotate('locator_probe', note);
    }

    /** Phase 4.4: refuse a destructive step unless safety.allow_destructive + a non-prod environment allow it. */
    private guardDestructive(step: PlanStep): void {
        const guard = this.safety.destructive;
        if (!guard || !guard.policy.enforced || guard.policy.allowed || !guard.rules) return;
        const verdict = classifyStep(step, guard.entryOf, guard.rules);
        if (verdict.destructive) {
            throw new SafetyError(refusalMessage(step, verdict, guard.policy));
        }
    }

    async navigate(url?: string): Promise<void> {
        await this.run(null, 'Navigate', url, async () => {
            // Phase 0 safety rail: an absolute URL outside safety.allowed_hosts
            // fails the step (relative URLs resolve against the allow-listed baseURL).
            assertUrlAllowed(url, this.safety.allowedHosts);
            // '' (not '/') as the no-arg default: per WHATWG URL resolution,
            // goto('/') against a baseURL with its own path (e.g.
            // https://aws.amazon.com/partners/) discards that path and lands
            // on the origin root instead of the module's page — goto('')
            // resolves to baseURL unchanged. Verified: new URL('', base) ===
            // base, new URL('/', base) === base's origin only.
            //
            // waitUntil: 'domcontentloaded' rather than 'networkidle' — a
            // chat/streaming SPA (e.g. an app with a long-poll or websocket
            // connection) never truly goes network-idle, so gating
            // navigation itself on it hit the full 30s navigationTimeout on
            // a real project. The best-effort networkidle wait below still
            // gives typical (non-streaming) pages a chance to settle before
            // the first action, but bounded so a page that never idles
            // can't block the whole test.
            await this.page.goto(url ?? '', { waitUntil: 'domcontentloaded' });
            await this.page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {});
        }, { action: 'navigate', value: url });
    }

    async click(name: string): Promise<void> {
        await this.run(name, 'Click', undefined, async () => {
            const locator = this.resolve(name);
            // target="_blank" links (often labelled "Opens in a new window")
            // open a second tab and leave the original page untouched — a
            // plain .click() then lets that new tab sit there, and on a real
            // project this left the original page in a state where the next
            // locator's actionability wait timed out. Detect it up front and
            // explicitly close the popup so subsequent actions continue
            // against the original page as intended.
            const target = await locator.getAttribute('target').catch(() => null);
            if (target === '_blank') {
                const [popup] = await Promise.all([
                    this.page.context().waitForEvent('page', { timeout: 5_000 }).catch(() => null),
                    locator.click(),
                ]);
                if (popup) {
                    await popup.waitForLoadState('domcontentloaded').catch(() => {});
                    await popup.close().catch(() => {});
                }
            } else {
                await locator.click();
            }
        }, { action: 'click', locator_key: name });
    }

    async doubleClick(name: string): Promise<void> {
        await this.run(name, 'Double Click', undefined, async () => {
            await this.resolve(name).dblclick();
        }, { action: 'doubleClick', locator_key: name });
    }

    async hover(name: string): Promise<void> {
        await this.run(name, 'Hover', undefined, async () => {
            await this.resolve(name).hover();
        });
    }

    async enterText(name: string, value: string): Promise<void> {
        await this.run(name, 'Enter Text', value, async () => {
            await this.resolve(name).fill(value);
        });
    }

    async clearAndEnterText(name: string, value: string): Promise<void> {
        await this.run(name, 'Clear And Enter Text', value, async () => {
            const locator = this.resolve(name);
            await locator.clear();
            await locator.fill(value);
        });
    }

    async pressKey(name: string | null, key: string): Promise<void> {
        await this.run(name, 'Press Key', key, async () => {
            if (name) {
                await this.resolve(name).press(key);
            } else {
                await this.page.keyboard.press(key);
            }
        }, { action: 'pressKey', locator_key: name, value: key });
    }

    async checkCheckbox(name: string): Promise<void> {
        await this.run(name, 'Check Checkbox', undefined, async () => {
            await this.resolve(name).check();
        }, { action: 'checkCheckbox', locator_key: name });
    }

    async uncheckCheckbox(name: string): Promise<void> {
        await this.run(name, 'Uncheck Checkbox', undefined, async () => {
            await this.resolve(name).uncheck();
        }, { action: 'uncheckCheckbox', locator_key: name });
    }

    async selectDropdownByText(name: string, text: string): Promise<void> {
        await this.run(name, 'Select Dropdown By Text', text, async () => {
            await this.resolve(name).selectOption({ label: text });
        }, { action: 'selectDropdownByText', locator_key: name, value: text });
    }

    async selectDropdownByValue(name: string, value: string): Promise<void> {
        await this.run(name, 'Select Dropdown By Value', value, async () => {
            await this.resolve(name).selectOption(value);
        }, { action: 'selectDropdownByValue', locator_key: name, value });
    }

    async scrollIntoView(name: string): Promise<void> {
        await this.run(name, 'Scroll Into View', undefined, async () => {
            await this.resolve(name).scrollIntoViewIfNeeded();
        });
    }

    async waitForElement(
        name: string,
        state: 'visible' | 'hidden' | 'attached' | 'detached' = 'visible'
    ): Promise<void> {
        await this.run(name, 'Wait For Element', state, async () => {
            await this.resolve(name).waitFor({ state });
        });
    }

    /**
     * A fixed sleep — kept only for human-authored flows.json (Phase 4.6: generated plans may not use it).
     * Logged as a warning and recorded as a test annotation; prefer waitForElement / waitUntil / pollUntil.
     */
    async waitForTimeout(ms: number): Promise<void> {
        const note = `fixed sleep waitForTimeout(${ms}) — prefer a web-first wait (waitForElement, waitUntil, pollUntil)`;
        Logger.warn(note);
        annotate('warning', note);
        await this.run(null, 'Wait For Timeout', String(ms), async () => {
            await this.page.waitForTimeout(ms);
        });
    }

    // ── Phase 4.6: web-first waiting for eventual consistency (runtime API, not LLM vocabulary) ──

    /** Retries `fn` until it stops throwing (expect(fn).toPass) — e.g. a list that updates asynchronously. */
    async waitUntil(description: string, fn: () => Promise<unknown> | unknown, opts: WaitOptions = {}): Promise<void> {
        await this.run(null, 'Wait Until', description, async () => {
            await expect(async () => { await fn(); }, description).toPass({ timeout: opts.timeout, intervals: opts.intervals });
        });
    }

    /** Polls `fn` until its value equals `expected` (expect.poll). */
    async pollUntil<T>(description: string, fn: () => Promise<T> | T, expected: T, opts: WaitOptions = {}): Promise<void> {
        await this.run(null, 'Poll Until', description, async () => {
            await expect.poll(async () => fn(), { message: description, timeout: opts.timeout, intervals: opts.intervals })
                .toEqual(expected);
        });
    }

    /** Waits for the page URL (string, glob or RegExp) — page.waitForURL. */
    async waitForUrl(url: string | RegExp, opts: { timeout?: number } = {}): Promise<void> {
        await this.run(null, 'Wait For URL', String(url), async () => {
            await this.page.waitForURL(url, { timeout: opts.timeout });
        });
    }

    async waitForLoadState(state: 'load' | 'domcontentloaded' | 'networkidle' = 'load'): Promise<void> {
        await this.run(null, 'Wait For Load State', state, async () => {
            await this.page.waitForLoadState(state);
        });
    }

    async dragAndDrop(sourceName: string, targetName: string): Promise<void> {
        await this.run(sourceName, 'Drag And Drop', targetName, async () => {
            await this.resolve(sourceName).dragTo(this.resolve(targetName));
        }, { action: 'dragAndDrop', locator_key: sourceName, target_locator_key: targetName });
    }

    async uploadFile(name: string, filePath: string): Promise<void> {
        await this.run(name, 'Upload File', filePath, async () => {
            if (!fs.existsSync(filePath)) {
                throw new Error(
                    `Upload fixture not found: '${filePath}'. TestDataAgent referenced this file `
                    + `name but never generated it on disk — either add it under a real fixtures `
                    + `directory or check test_data.json for this scenario.`
                );
            }
            await this.resolve(name).setInputFiles(filePath);
        });
    }

    async verifyVisible(name: string, message?: string, opts?: VerifyOptions): Promise<void> {
        await this.run(name, 'Verify Visible', message, async () => {
            const assertion = opts?.soft ? expect.soft(this.resolve(name), message) : expect(this.resolve(name), message);
            await assertion.toBeVisible();
        });
    }

    async verifyHidden(name: string, message?: string, opts?: VerifyOptions): Promise<void> {
        await this.run(name, 'Verify Hidden', message, async () => {
            const assertion = opts?.soft ? expect.soft(this.resolve(name), message) : expect(this.resolve(name), message);
            await assertion.toBeHidden();
        });
    }

    async verifyText(name: string, expectedText: string, message?: string, opts?: VerifyOptions): Promise<void> {
        await this.run(name, 'Verify Text', expectedText, async () => {
            const assertion = opts?.soft ? expect.soft(this.resolve(name), message) : expect(this.resolve(name), message);
            await assertion.toHaveText(expectedText);
        });
    }

    async verifyContainsText(name: string, expectedText: string, message?: string, opts?: VerifyOptions): Promise<void> {
        await this.run(name, 'Verify Contains Text', expectedText, async () => {
            const assertion = opts?.soft ? expect.soft(this.resolve(name), message) : expect(this.resolve(name), message);
            await assertion.toContainText(expectedText);
        });
    }

    async verifyValue(name: string, expectedValue: string, message?: string, opts?: VerifyOptions): Promise<void> {
        await this.run(name, 'Verify Value', expectedValue, async () => {
            const assertion = opts?.soft ? expect.soft(this.resolve(name), message) : expect(this.resolve(name), message);
            await assertion.toHaveValue(expectedValue);
        });
    }

    async verifyEnabled(name: string, message?: string, opts?: VerifyOptions): Promise<void> {
        await this.run(name, 'Verify Enabled', message, async () => {
            const assertion = opts?.soft ? expect.soft(this.resolve(name), message) : expect(this.resolve(name), message);
            await assertion.toBeEnabled();
        });
    }

    async verifyDisabled(name: string, message?: string, opts?: VerifyOptions): Promise<void> {
        await this.run(name, 'Verify Disabled', message, async () => {
            const assertion = opts?.soft ? expect.soft(this.resolve(name), message) : expect(this.resolve(name), message);
            await assertion.toBeDisabled();
        });
    }

    async verifyChecked(name: string, message?: string, opts?: VerifyOptions): Promise<void> {
        await this.run(name, 'Verify Checked', message, async () => {
            const assertion = opts?.soft ? expect.soft(this.resolve(name), message) : expect(this.resolve(name), message);
            await assertion.toBeChecked();
        });
    }

    async verifyCount(name: string, count: number, message?: string, opts?: VerifyOptions): Promise<void> {
        await this.run(name, 'Verify Count', String(count), async () => {
            const assertion = opts?.soft ? expect.soft(this.resolve(name), message) : expect(this.resolve(name), message);
            await assertion.toHaveCount(count);
        });
    }

    async verifyUrl(expectedUrl: string | RegExp, message?: string, opts?: VerifyOptions): Promise<void> {
        await this.run(null, 'Verify URL', String(expectedUrl), async () => {
            const assertion = opts?.soft ? expect.soft(this.page, message) : expect(this.page, message);
            await assertion.toHaveURL(expectedUrl);
        });
    }

    /**
     * Substring/contains variant of verifyUrl — for apps that redirect to a
     * sub-path (e.g. "/" -> "/app") where the exact destination isn't the
     * meaningful assertion, just that navigation reached the expected area.
     */
    async verifyUrlContains(substring: string, message?: string, opts?: VerifyOptions): Promise<void> {
        await this.run(null, 'Verify URL Contains', substring, async () => {
            const assertion = opts?.soft ? expect.soft(this.page, message) : expect(this.page, message);
            await assertion.toHaveURL(new RegExp(substring.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
        });
    }

    async verifyTitle(expectedTitle: string | RegExp, message?: string, opts?: VerifyOptions): Promise<void> {
        await this.run(null, 'Verify Title', String(expectedTitle), async () => {
            const assertion = opts?.soft ? expect.soft(this.page, message) : expect(this.page, message);
            await assertion.toHaveTitle(expectedTitle);
        });
    }

    /**
     * Substring/contains variant of verifyTitle — for apps whose <title>
     * carries an extra prefix/suffix (e.g. "Gemini" rendered as "Google
     * Gemini") where the meaningful assertion is "contains", not exact match.
     */
    async verifyTitleContains(substring: string, message?: string, opts?: VerifyOptions): Promise<void> {
        await this.run(null, 'Verify Title Contains', substring, async () => {
            const assertion = opts?.soft ? expect.soft(this.page, message) : expect(this.page, message);
            await assertion.toHaveTitle(new RegExp(substring.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
        });
    }

    /**
     * Asserts no page-level JS error or unhandled rejection was observed
     * since the test started (collected by fixtures/testFixture.ts's
     * `page.on('pageerror', ...)` listener into pageErrors).
     */
    async verifyNoPageErrors(message = 'No JS errors should occur on this page'): Promise<void> {
        await this.run(null, 'Verify No Page Errors', undefined, async () => {
            expect(this.pageErrors, message).toHaveLength(0);
        });
    }

    /**
     * Phase 5: a request matching method + urlPattern ('*' wildcard) was made — and, if given, one such request got
     * `status` (a number or "2xx") and had a request body containing `bodyContains`.
     */
    async verifyRequest(method: string, urlPattern: string, status?: number | string, message?: string,
                        bodyContains?: string): Promise<void> {
        await this.run(null, 'Verify Request', `${method} ${urlPattern}`, async () => {
            const log = this.requireNetwork();
            const re = patternToRegExp(urlPattern);
            const what = `${method} ${urlPattern}`;
            // the response may still be in flight right after the triggering click
            await expect.poll(() => {
                const hits = log.entries({ method, url: re })
                    .filter((h) => status === undefined || statusMatches(h.status, status))
                    .filter((h) => bodyContains === undefined || (h.post_data ?? '').includes(bodyContains));
                return hits.length;
            }, {
                message: message ?? `Expected a ${what} request` + (status !== undefined ? ` with status ${status}` : '')
                    + (bodyContains !== undefined ? ` whose body contains '${bodyContains}'` : ''),
                timeout: 5_000,
            }).toBeGreaterThan(0);
        });
    }

    /** Phase 5: no request matching method + urlPattern was made (negative tests: nothing was submitted). */
    async verifyNoRequest(method: string, urlPattern: string, message?: string): Promise<void> {
        await this.run(null, 'Verify No Request', `${method} ${urlPattern}`, async () => {
            const hits = this.requireNetwork().entries({ method, url: patternToRegExp(urlPattern) });
            expect(hits.length, message ?? `Expected no ${method} request matching ${urlPattern}`).toBe(0);
        });
    }

    /** Phase 5: aria-invalid="true" or the native :invalid state. */
    async verifyFieldInvalid(name: string, message?: string): Promise<void> {
        await this.run(name, 'Verify Field Invalid', undefined, async () => {
            const loc = this.resolve(name);
            await expect(async () => {
                const invalid = await loc.evaluate((el) =>
                    el.getAttribute('aria-invalid') === 'true' || (el as HTMLElement).matches(':invalid'));
                expect(invalid, message ?? `Expected '${name}' to be invalid`).toBe(true);
            }).toPass({ timeout: 5_000 });
        });
    }

    /** Phase 5: no alert/confirm/prompt/beforeunload dialog fired during the test (XSS check). */
    async verifyNoDialog(message = 'No JS dialog should have fired'): Promise<void> {
        await this.run(null, 'Verify No Dialog', undefined, async () => {
            expect(this.oracles.dialogs ?? [], message).toHaveLength(0);
        });
    }

    /** Phase 5: the payload is not executable — no new <script>, no inline event-handler attribute containing it. */
    async verifyNotInjected(payloadMarker: string, message?: string): Promise<void> {
        await this.run(null, 'Verify Not Injected', payloadMarker, async () => {
            const found = await this.page.evaluate((marker) => {
                const scripts = [...document.querySelectorAll('script')].filter((s) => (s.textContent ?? '').includes(marker));
                const handlers = [...document.querySelectorAll('*')].filter((el) =>
                    [...el.attributes].some((a) => /^on/i.test(a.name) && a.value.includes(marker)));
                return scripts.length + handlers.length;
            }, payloadMarker);
            expect(found, message ?? `Payload '${payloadMarker}' must be rendered as text, not as script/handler`).toBe(0);
        });
    }

    /**
     * Phase 5: no console error / page error beyond the Phase 2 baseline (appended by the renderer to every test).
     * The browser's "Failed to load resource: ... status of 4xx" lines are not counted: a 4xx answer is often the
     * expected outcome (a rejected form, a denied page) and the request oracles assert statuses. 5xx answers, JS
     * console errors and uncaught page errors still fail the check.
     */
    async verifyNoNewConsoleErrors(message = 'No new console errors should occur'): Promise<void> {
        await this.run(null, 'Verify No New Console Errors', undefined, async () => {
            const guard = this.oracles.consoleGuard;
            if (!guard) return;
            const fresh = guard.newErrors()
                .filter((e) => !(e.kind === 'console' && CLIENT_ERROR_RESOURCE.test(e.text)))
                .map((e) => `[${e.kind}] ${e.text.slice(0, 200)}`);
            expect(fresh, message).toEqual([]);
        });
    }

    /** Phase 5: the native validationMessage, or the text of aria-errormessage / aria-describedby, contains `contains`. */
    async verifyValidationMessage(name: string, contains: string, message?: string): Promise<void> {
        await this.run(name, 'Verify Validation Message', contains, async () => {
            const loc = this.resolve(name);
            await expect(async () => {
                const texts = await loc.evaluate((el) => {
                    const out: string[] = [];
                    const native = (el as HTMLInputElement).validationMessage;
                    if (native) out.push(native);
                    for (const attr of ['aria-errormessage', 'aria-describedby']) {
                        for (const id of (el.getAttribute(attr) ?? '').split(/\s+/).filter(Boolean)) {
                            const ref = el.ownerDocument.getElementById(id);
                            if (ref?.textContent) out.push(ref.textContent.trim());
                        }
                    }
                    return out;
                });
                const hit = texts.some((t) => t.toLowerCase().includes(contains.toLowerCase()));
                expect(hit, message ?? `Expected a validation message on '${name}' containing '${contains}'; ` +
                    `found ${JSON.stringify(texts)}`).toBe(true);
            }).toPass({ timeout: 5_000 });
        });
    }

    /** Phase 5: structural assertion — the element's accessibility tree matches the YAML snapshot. */
    async verifyAriaSnapshot(name: string, snapshot: string, message?: string): Promise<void> {
        await this.run(name, 'Verify Aria Snapshot', undefined, async () => {
            await expect(this.resolve(name), message).toMatchAriaSnapshot(snapshot);
        });
    }

    /** Phase 5: remembers how many elements `name` matches now — the baseline for verifyCountChangedBy. */
    async rememberCount(name: string): Promise<void> {
        await this.run(name, 'Remember Count', undefined, async () => {
            this.counts.set(name, await this.resolve(name).count());
        });
    }

    /** Phase 5: the element count changed by exactly `delta` since rememberCount (CRUD, double-submit; 0 = nothing created). */
    async verifyCountChangedBy(name: string, delta: number, message?: string): Promise<void> {
        await this.run(name, 'Verify Count Changed By', String(delta), async () => {
            const base = this.counts.get(name);
            if (base === undefined) throw new Error(`verifyCountChangedBy('${name}') needs an earlier rememberCount('${name}')`);
            await expect.poll(() => this.resolve(name).count(), {
                message: message ?? `Expected the count of '${name}' to change by ${delta} (from ${base})`, timeout: 5_000,
            }).toBe(base + delta);
        });
    }

    /** Phase 5: clicking `name` starts a download whose file name matches `nameRegex` and is at least `minBytes`. */
    async verifyDownload(name: string, nameRegex?: string, minBytes?: number, message?: string): Promise<void> {
        await this.run(name, 'Verify Download', nameRegex, async () => {
            const [download] = await Promise.all([
                this.page.waitForEvent('download', { timeout: 15_000 }),
                this.resolve(name).click(),
            ]);
            const fileName = download.suggestedFilename();
            if (nameRegex) {
                expect(fileName, message ?? `Download name '${fileName}' should match /${nameRegex}/`).toMatch(new RegExp(nameRegex));
            }
            const file = await download.path();
            const size = file ? fs.statSync(file).size : 0;
            expect(size, message ?? `Download '${fileName}' should be at least ${minBytes ?? 1} byte(s)`)
                .toBeGreaterThanOrEqual(minBytes ?? 1);
        }, { action: 'click', locator_key: name });
    }

    /** Phase 5: clicking `name` opens a new tab whose URL contains `urlContains`; the tab is closed afterwards. */
    async verifyNewTab(name: string, urlContains: string, message?: string): Promise<void> {
        await this.run(name, 'Verify New Tab', urlContains, async () => {
            const [popup] = await Promise.all([
                this.page.context().waitForEvent('page', { timeout: 10_000 }),
                this.resolve(name).click(),
            ]);
            try {
                await popup.waitForLoadState('domcontentloaded').catch(() => {});
                await expect(popup, message ?? `New tab URL should contain '${urlContains}'`)
                    .toHaveURL(new RegExp(urlContains.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
            } finally {
                await popup.close().catch(() => {});
            }
        }, { action: 'click', locator_key: name });
    }

    /** Phase 5: a cookie / localStorage / sessionStorage entry meets `rule` (session and security checks). */
    async verifyStorage(kind: StorageKind, key: string, rule: StorageRule, value?: string, message?: string): Promise<void> {
        await this.run(null, 'Verify Storage', `${kind} ${key} ${rule}${value !== undefined ? ` ${value}` : ''}`, async () => {
            const msg = message ?? `${kind} '${key}' should be ${rule}${value !== undefined ? ` '${value}'` : ''}`;
            if (kind === 'cookie') {
                const cookie = (await this.page.context().cookies()).find((c) => c.name === key);
                if (rule === 'absent') { expect(cookie, msg).toBeUndefined(); return; }
                expect(cookie, msg).toBeDefined();
                if (rule === 'equals') expect(cookie!.value, msg).toBe(value);
                if (rule === 'contains') expect(cookie!.value, msg).toContain(value ?? '');
                if (rule === 'httpOnly') expect(cookie!.httpOnly, msg).toBe(true);
                if (rule === 'secure') expect(cookie!.secure, msg).toBe(true);
                if (rule === 'sameSite') expect(cookie!.sameSite, msg).not.toBe('None');
                return;
            }
            if (['httpOnly', 'secure', 'sameSite'].includes(rule)) throw new Error(`verifyStorage: '${rule}' applies to cookies only`);
            const stored = await this.page.evaluate(([k, store]) =>
                (store === 'localStorage' ? window.localStorage : window.sessionStorage).getItem(k), [key, kind] as const);
            if (rule === 'absent') { expect(stored, msg).toBeNull(); return; }
            expect(stored, msg).not.toBeNull();
            if (rule === 'equals') expect(stored, msg).toBe(value);
            if (rule === 'contains') expect(stored, msg).toContain(value ?? '');
        });
    }

    /** Phase 5: a response matching urlPattern exists and every matching JSON body satisfies the schema. */
    async verifyResponseSchema(urlPattern: string, schema: Schema | string, message?: string): Promise<void> {
        await this.run(null, 'Verify Response Schema', urlPattern, async () => {
            const resolved = typeof schema === 'string' ? this.loadSchema(schema) : schema;
            const log = this.requireNetwork();
            const re = patternToRegExp(urlPattern);
            await expect.poll(async () => (await log.responseBodies({ url: re })).length, {
                message: message ?? `Expected a JSON response matching ${urlPattern}`, timeout: 5_000,
            }).toBeGreaterThan(0);
            const problems: string[] = [];
            for (const r of await log.responseBodies({ url: re })) {
                let body: unknown;
                try {
                    body = JSON.parse(r.body ?? '');
                } catch {
                    problems.push(`${r.method} ${r.url}: body is not JSON (or was not readable)`);
                    continue;
                }
                problems.push(...validateSchema(body, resolved).map((p) => `${r.method} ${r.url}: ${p}`));
            }
            expect(problems, message ?? `Responses matching ${urlPattern} should match the schema`).toEqual([]);
        });
    }

    /** Phase 5 grey-box: checks backend state through the `api` fixture (same user and base URL as the page). */
    async verifyApiState(method: string, url: string, expected: ApiExpect, message?: string): Promise<void> {
        await this.run(null, 'Verify Api State', `${method} ${url}`, async () => {
            const api = this.oracles.api;
            if (!api) throw new Error('ActionEngine: api oracle unavailable (no api fixture)');
            const what = `${method} ${url}`;
            const res = await api.fetch(url, { method, failOnStatusCode: false });
            const text = await res.text();
            if (expected.status !== undefined) {
                expect(statusMatches(res.status(), expected.status),
                    message ?? `${what} returned ${res.status()}, expected ${expected.status}`).toBe(true);
            }
            if (expected.bodyContains !== undefined) expect(text, message ?? `${what} body`).toContain(expected.bodyContains);
            if (expected.bodyNotContains !== undefined) expect(text, message ?? `${what} body`).not.toContain(expected.bodyNotContains);
            if (expected.path !== undefined) {
                let json: unknown;
                try {
                    json = JSON.parse(text);
                } catch {
                    throw new Error(`${what}: body is not JSON, cannot read '${expected.path}'`);
                }
                const at = jsonAtPath(json, expected.path);
                if (expected.equals !== undefined) expect(at, message ?? `${what} ${expected.path}`).toEqual(expected.equals);
                if (expected.length !== undefined) {
                    expect(Array.isArray(at) || typeof at === 'string' ? (at as any).length : undefined,
                        message ?? `${what} ${expected.path} length`).toBe(expected.length);
                }
            }
        });
    }

    // ── Phase 5 / 7.6: fault injection and time control ──

    /** Answers requests matching urlPattern with `status`/`body` (after `delayMs`); only `delayMs` = slow it down. */
    async mockRoute(urlPattern: string, opts: MockRouteOptions = {}): Promise<void> {
        await this.run(null, 'Mock Route', urlPattern, async () => {
            annotate('fault_injection', `mockRoute ${urlPattern} ${JSON.stringify(opts)}`);
            if (opts.status !== undefined && opts.status >= 400) {
                this.oracles.consoleGuard?.expectConsoleError(
                    new RegExp(`Failed to load resource: the server responded with a status of ${opts.status}\\b`));
            }
            this.oracles.network?.markMocked(patternToRegExp(urlPattern));
            await this.page.route(patternToRegExp(urlPattern), async (route) => {
                if (opts.delayMs) await new Promise((r) => setTimeout(r, opts.delayMs));
                if (opts.status === undefined && opts.body === undefined) {
                    await route.continue();
                    return;
                }
                const body = opts.body === undefined ? '' : typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body);
                await route.fulfill({
                    status: opts.status ?? 200,
                    body,
                    contentType: opts.contentType ?? (typeof opts.body === 'object' ? 'application/json' : 'text/plain'),
                });
            });
        });
    }

    async setOffline(offline: boolean): Promise<void> {
        await this.run(null, 'Set Offline', String(offline), async () => {
            annotate('fault_injection', `setOffline ${offline}`);
            if (offline) this.oracles.consoleGuard?.expectConsoleError(/Failed to load resource: net::ERR_INTERNET_DISCONNECTED/);
            await this.page.context().setOffline(offline);
        });
    }

    /** Freezes Date.now() / new Date() at `isoTime` (timers keep running) — expiry, scheduling, "today" logic. */
    async setClock(isoTime: string): Promise<void> {
        await this.run(null, 'Set Clock', isoTime, async () => {
            const at = new Date(isoTime);
            if (Number.isNaN(at.getTime())) throw new Error(`setClock: '${isoTime}' is not a valid date/time`);
            await this.page.clock.setFixedTime(at);
        });
    }

    private loadSchema(ref: string): Schema {
        const base = this.oracles.projectDir;
        const file = path.isAbsolute(ref) ? ref : base ? path.join(base, ref) : ref;
        if (!fs.existsSync(file)) throw new Error(`verifyResponseSchema: schema file '${file}' not found`);
        return JSON.parse(fs.readFileSync(file, 'utf8'));
    }

    private requireNetwork(): NetworkLog {
        if (!this.oracles.network) throw new Error('ActionEngine: network oracle unavailable (execution.network is off)');
        return this.oracles.network;
    }

    async takeScreenshot(fileName: string): Promise<void> {
        await this.run(null, 'Take Screenshot', fileName, async () => {
            await this.page.screenshot({ path: `test-results/${fileName}.png`, fullPage: true });
        });
    }

    async goBack(): Promise<void> {
        await this.run(null, 'Go Back', undefined, async () => {
            await this.page.goBack();
        });
    }

    async reload(): Promise<void> {
        await this.run(null, 'Reload', undefined, async () => {
            await this.page.reload();
        });
    }
}
