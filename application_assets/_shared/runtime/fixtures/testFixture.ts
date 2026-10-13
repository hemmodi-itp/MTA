import fs from 'fs';
import path from 'path';
import { test as base, APIRequestContext, BrowserContext, Page } from '@playwright/test';
import { ActionEngine, RuntimeSafety } from '../ActionEngine';
import { allowedHostsFromEnv, isUrlAllowed, SafetyError } from '../safety';
import { resolveRoleStorageState } from '../auth/roles';
import { loadProjectYaml } from '../config/projectYaml';
import { ExecutionConfig, resolveExecutionConfig } from '../config/execution';
import { LocatorManager } from '../LocatorManager';
import { destructivePolicy, loadRules } from '../destructive';
import { TestData, runIdFromEnv } from './testData';
import { CleanupRegistry } from './cleanup';
import { guardApi } from './api';
import { ConsoleGuard, ConsoleGuardMode, loadBaseline } from './consoleGuard';
import { NetworkLog, NetworkMode, shouldAttachHar } from './network';
import { A11yScanOptions, axeScan } from './a11y';
import { collectPerf, PerfMetrics } from './perf';

type PageRegistry = Record<string, new (page: Page) => Record<string, unknown>>;

export interface Cleanup {
    /** Register a created entity; teardown deletes in reverse order — API first, UI fallback. */
    register(label: string, handlers: { api?: (api: APIRequestContext) => unknown; ui?: (page: Page) => unknown }): void;
}

export interface A11y {
    /** AxeBuilder results (Phase 7 adds the checks); throws a clear error while @axe-core/playwright is absent. */
    scan(options?: A11yScanOptions): Promise<any>;
}

export interface Perf {
    collect(): Promise<PerfMetrics>;
    attach(name?: string): Promise<PerfMetrics>;
}

type Fixtures = {
    action: ActionEngine;
    /** Phase 4.4 — unique deterministic data per test (runId + testId seeded). */
    testData: TestData;
    cleanup: Cleanup;
    /** Request context with the test's role auth and the run's baseURL. */
    api: APIRequestContext;
    consoleGuard: ConsoleGuard;
    network: NetworkLog;
    a11y: A11y;
    perf: Perf;
    safety: RuntimeSafety;
};

type Options = {
    /** Phase 4.3: an `auth.roles` role from project.yaml — `test.use({ role: 'admin' })`. */
    role: string | undefined;
};

let execCache: ExecutionConfig | null = null;
let warnedUnenforced = false;

/** PW_PROJECT's resolved `execution:` block (once per worker; warnings were printed by the config already). */
function execOptions(): ExecutionConfig {
    if (!execCache) execCache = resolveExecutionConfig(loadProjectYaml(process.env.PW_PROJECT), () => {});
    return execCache;
}

function projectDir(): string | null {
    const project = process.env.PW_PROJECT;
    return project ? path.join(process.cwd(), 'application_assets', 'projects', project) : null;
}

/**
 * test_creation/pages.ts is generated per-project (one file, every module's
 * Page class + PAGE_REGISTRY — see build_dom_locator_map.py::render_pages_module),
 * so its path can't be a static import from this one shared fixture file.
 * Resolved at runtime via the same PW_PROJECT env var LocatorManager uses.
 */
function loadPageRegistry(): PageRegistry {
    const project = process.env.PW_PROJECT;
    if (!project) {
        throw new Error('testFixture: PW_PROJECT env var is not set.');
    }
    const pagesModulePath = path.join(
        process.cwd(), 'application_assets', 'projects', project, 'test_creation', 'pages.ts'
    );
    // A dynamic require() (unlike a static `import`) bypasses Playwright's
    // own TS-loader specifier rewriting, so this needs the real extension
    // for Playwright's require hook to recognize and transform the file.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const pagesModule = require(pagesModulePath);
    return pagesModule.PAGE_REGISTRY as PageRegistry;
}

/**
 * Specs live under test_creation/test_scripts/{module_id}/..., so the module
 * a spec belongs to can be read straight off its own file path — no extra
 * bookkeeping needed. Falls back to "_default" for a flat/single-module
 * project with no module subfolder.
 */
function extractModuleId(specFilePath: string): string {
    const normalized = specFilePath.split(path.sep).join('/');
    const marker = '/test_scripts/';
    const idx = normalized.indexOf(marker);
    if (idx === -1) return '_default';
    const rest = normalized.slice(idx + marker.length);
    const segments = rest.split('/');
    return segments.length > 1 ? segments[0] : '_default';
}

function locatorEntry(key: string) {
    try {
        return LocatorManager.get(key);
    } catch {
        return null;
    }
}

function failed(testInfo: { status?: string; expectedStatus: string }): boolean {
    return testInfo.status !== undefined && testInfo.status !== testInfo.expectedStatus;
}

export const test = base.extend<Fixtures & Options>({
    role: [undefined, { option: true }],

    // Phase 4.3: a test that sets `role` starts with that role's storage state (an empty one for an
    // anonymous role). Without `role`, the config's storageState (PW_STORAGE_STATE) applies unchanged.
    storageState: async ({ role, storageState }, use) => {
        if (!role) {
            await use(storageState);
            return;
        }
        const project = process.env.PW_PROJECT;
        await use(resolveRoleStorageState(role, { project: loadProjectYaml(project), projectName: project }));
    },

    // Phase 0 / 4.4 safety rails for every page of the test's context:
    //  * a top-level navigation (redirect, link click) to a host outside MTA_ALLOWED_HOSTS is recorded; ActionEngine
    //    fails the next action, and a violation no action reported fails the test at teardown;
    //  * destructive actions (tools/safety/destructive_rules.yaml) are refused by ActionEngine unless
    //    safety.allow_destructive + a local/dev/staging environment allow them.
    // Depends on `network` so the network log tears down AFTER this check: a teardown failure here still gets the HAR.
    safety: [async ({ context, network: _network }, use) => {
        const policy = destructivePolicy(process.env, loadProjectYaml(process.env.PW_PROJECT));
        if (!policy.enforced && !warnedUnenforced) {
            warnedUnenforced = true;
            // eslint-disable-next-line no-console
            console.warn('[MTA safety] no MTA_DESTRUCTIVE_ALLOWED and no PW_PROJECT — destructive-action guard not enforced');
        }
        const safety: RuntimeSafety = {
            allowedHosts: allowedHostsFromEnv(),
            violations: [],
            reported: 0,
            destructive: { policy, rules: policy.enforced ? loadRules() : null, entryOf: locatorEntry },
        };
        const watch = (page: Page) => {
            page.on('framenavigated', (frame) => {
                if (frame === page.mainFrame() && !isUrlAllowed(frame.url(), safety.allowedHosts)) {
                    safety.violations.push(frame.url());
                }
            });
        };
        context.pages().forEach(watch);
        context.on('page', watch);
        await use(safety);
        const unreported = safety.violations.slice(safety.reported ?? 0);
        if (unreported.length) {
            throw new SafetyError(
                `page left safety.allowed_hosts [${(safety.allowedHosts ?? []).join(', ')}]: ${unreported.join(', ')}`
            );
        }
    }, { auto: true }],

    action: async ({ page, safety, network, consoleGuard }, use, testInfo) => {
        const pageErrors: string[] = [];
        page.on('pageerror', (err) => pageErrors.push(err.message));
        const dialogs: string[] = [];
        page.on('dialog', (d) => { dialogs.push(`${d.type()}: ${d.message()}`); d.dismiss().catch(() => {}); });

        const moduleId = extractModuleId(testInfo.file);
        const registry = loadPageRegistry();
        // pages.ts keys its PAGE_REGISTRY by each locator's _module_id, which
        // build_dom_locator_map.py derives from the DOM scan's file layout
        // (flat dom_elements.json vs. a modules/{id}/ subfolder) — a signal
        // independent of the module folder a spec is filed under here. A flat
        // DOM scan always produces "_default", even for a spec whose real
        // module id (e.g. "M01") came from project.yaml's modules[]/script
        // generation. Fall back to "_default" rather than failing every test
        // whenever those two ID spaces disagree.
        const PageClass = registry[moduleId] ?? registry['_default'];
        if (!PageClass) {
            throw new Error(
                `testFixture: no Page class registered for module '${moduleId}' in pages.ts ` +
                `(no '_default' fallback available either)`
            );
        }
        const pageObject = new PageClass(page) as Record<string, any>;

        await use(new ActionEngine(page, pageObject, pageErrors, safety, { network, consoleGuard, dialogs }));
    },

    testData: async ({}, use, testInfo) => {
        await use(new TestData({
            runId: runIdFromEnv(),
            testId: testInfo.testId,
            repeatEachIndex: testInfo.repeatEachIndex,
            retry: testInfo.retry,
        }));
    },

    api: async ({ playwright, baseURL, storageState }, use) => {
        const ctx = await playwright.request.newContext({ baseURL, storageState: storageState as any });
        await use(guardApi(ctx, allowedHostsFromEnv(), baseURL));
        await ctx.dispose();
    },

    cleanup: async ({ api, page }, use, testInfo) => {
        const registry = new CleanupRegistry<APIRequestContext, Page>();
        await use({ register: (label, handlers) => registry.register(label, handlers) });
        if (!registry.size) return;
        const outcome = await registry.run({ api: () => api, page: () => page });
        if (!outcome.failures.length) return;
        for (const f of outcome.failures) {
            testInfo.annotations.push({ type: 'cleanup_failed', description: `${f.label}: ${f.error}` });
            // eslint-disable-next-line no-console
            console.warn(`[MTA cleanup] '${f.label}' was not cleaned up (${f.via}): ${f.error}`);
        }
        await testInfo.attach('cleanup.json', { body: JSON.stringify(outcome, null, 2), contentType: 'application/json' });
        if (execOptions().cleanup_failure === 'fail') {
            throw new Error(`cleanup failed for ${outcome.failures.length} entit(y/ies): ` +
                outcome.failures.map((f) => f.label).join(', '));
        }
    },

    // New console errors vs test_comprehension/baseline.json (execution.console_guard: off | warn | fail).
    // Depends on `network` (torn down after this fixture), so a consoleGuard failure still attaches the HAR.
    consoleGuard: [async ({ context, network: _network }, use, testInfo) => {
        const mode = execOptions().console_guard as ConsoleGuardMode;
        const dir = projectDir();
        const baseline = loadBaseline(dir ? path.join(dir, 'test_comprehension', 'baseline.json') : '(PW_PROJECT unset)');
        const guard = new ConsoleGuard(baseline, mode);
        if (mode !== 'off') {
            listenConsole(context, guard);
        }
        await use(guard);
        if (mode === 'off') return;
        if (!baseline.available && guard.errors().length) {
            testInfo.annotations.push({ type: 'console_guard', description: baseline.note ?? 'no baseline' });
        }
        const fresh = guard.newErrors();
        for (const e of fresh.slice(0, 20)) {
            testInfo.annotations.push({ type: 'console_new_error', description: `[${e.kind}] ${e.url}: ${e.text.slice(0, 300)}` });
        }
        if (guard.errors().length) {
            await testInfo.attach('console-errors.json', {
                body: JSON.stringify({ mode: guard.effectiveMode, baseline: baseline.path, new: fresh, known: guard.knownErrors() }, null, 2),
                contentType: 'application/json',
            });
        }
        const failure = guard.failureMessage();
        if (failure) throw new Error(failure);
    }, { auto: true }],

    // Request log for Phase 5 oracles + a redacted HAR attachment (execution.network: off | on-failure | on).
    network: [async ({ context }, use, testInfo) => {
        const mode = execOptions().network as NetworkMode;
        const log = new NetworkLog();
        if (mode !== 'off') {
            context.on('request', (r) => log.onRequest(r));
            context.on('response', (r) => log.onResponse(r));
            context.on('requestfinished', (r) => log.onFinished(r));
            context.on('requestfailed', (r) => log.onFailed(r));
        }
        await use(log);
        if (shouldAttachHar(mode, failed(testInfo)) && log.entries().length) {
            // written next to the trace/video (retained evidence) and attached by path
            const file = testInfo.outputPath('network.har');
            fs.mkdirSync(path.dirname(file), { recursive: true });
            fs.writeFileSync(file, JSON.stringify(log.har(), null, 2), 'utf8');
            await testInfo.attach('network.har', { path: file, contentType: 'application/json' });
        }
    }, { auto: true }],

    a11y: async ({ page }, use, testInfo) => {
        await use({
            scan: async (options) => {
                const results = await axeScan(page, options);
                await testInfo.attach('a11y.json', { body: JSON.stringify(results, null, 2), contentType: 'application/json' });
                return results;
            },
        });
    },

    perf: async ({ page }, use, testInfo) => {
        await use({
            collect: () => collectPerf(page),
            attach: async (name = 'perf.json') => {
                const metrics = await collectPerf(page);
                await testInfo.attach(name, { body: JSON.stringify(metrics, null, 2), contentType: 'application/json' });
                return metrics;
            },
        });
    },
});

function listenConsole(context: BrowserContext, guard: ConsoleGuard): void {
    context.on('console', (msg) => {
        if (msg.type() === 'error') {
            guard.record({ kind: 'console', text: msg.text(), url: msg.page()?.url() ?? msg.location().url ?? '' });
        }
    });
    context.on('weberror', (err) => {
        guard.record({ kind: 'pageerror', text: err.error().message, url: err.page()?.url() ?? '' });
    });
}

export { expect } from '@playwright/test';
