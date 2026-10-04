import path from 'path';
import { test as base, Page } from '@playwright/test';
import { ActionEngine } from '../ActionEngine';

type PageRegistry = Record<string, new (page: Page) => Record<string, unknown>>;

type Fixtures = {
    action: ActionEngine;
};

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

export const test = base.extend<Fixtures>({
    action: async ({ page }, use, testInfo) => {
        const pageErrors: string[] = [];
        page.on('pageerror', (err) => pageErrors.push(err.message));

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

        await use(new ActionEngine(page, pageObject, pageErrors));
    }
});

export { expect } from '@playwright/test';
