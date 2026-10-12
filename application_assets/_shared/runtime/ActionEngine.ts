import * as fs from 'fs';
import { expect, Locator, Page, test } from '@playwright/test';
import { Logger } from './Logger';
import { allowedHostsFromEnv, assertUrlAllowed, SafetyError } from './safety';
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

export class ActionEngine {

    constructor(
        private readonly page: Page,
        private readonly pageObject: Record<string, Locator>,
        private readonly pageErrors: string[] = [],
        private readonly safety: RuntimeSafety = { allowedHosts: allowedHostsFromEnv(), violations: [] }
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
            throw new Error(
                locatorName ? `[locator_key=${locatorName}] ${message}` : message
            );
        }
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
