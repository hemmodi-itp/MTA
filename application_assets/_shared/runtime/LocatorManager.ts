import fs from 'fs';
import path from 'path';
import { FrameLocator, Locator, Page } from '@playwright/test';

type LocatorType = 'css' | 'xpath' | 'role' | 'text' | 'label' | 'testid' | 'placeholder';

/** A container the entry is resolved inside (Phase 2 container-scoped locators). */
export interface LocatorScope {
    type: LocatorType;
    locator: string;
    name?: string;
}

export interface LocatorEntry {
    type: LocatorType;
    locator: string;
    name?: string;        // used only when type === 'role'
    description?: string;
    frame?: string[];     // Phase 2: iframe selectors from the page down to the element's frame
    scope?: LocatorScope; // Phase 2: resolve inside this container (e.g. a named dialog)
    _fingerprint?: Record<string, unknown>; // Phase 6.3: identity of the element while the locator worked
}

type LocatorBase = Page | FrameLocator | Locator;

function resolveOn(base: LocatorBase, type: string, locator: string, name: string | undefined, key: string): Locator {
    switch (type) {
        case 'css':
            return base.locator(locator);
        case 'xpath':
            return base.locator(`xpath=${locator}`);
        case 'role':
            return name
                ? base.getByRole(locator as Parameters<Page['getByRole']>[0], { name })
                : base.getByRole(locator as Parameters<Page['getByRole']>[0]);
        case 'text':
            return base.getByText(locator);
        case 'label':
            return base.getByLabel(locator);
        case 'testid':
            return base.getByTestId(locator);
        case 'placeholder':
            return base.getByPlaceholder(locator);
        default:
            throw new Error(`Unknown locator type for '${key}': ${type}`);
    }
}

/**
 * {type, locator, name?, frame?, scope?} -> Locator. Without frame/scope this is exactly the
 * pre-Phase-2 switch against *page*. Mirrored in Python by
 * tools/test_creation/script_generator/locator_resolve.py (live validation).
 */
export function resolveEntry(page: Page, entry: LocatorEntry, key = '<entry>'): Locator {
    let base: LocatorBase = page;
    for (const selector of entry.frame ?? []) {
        base = base.frameLocator(selector);
    }
    if (entry.scope) {
        base = resolveOn(base, entry.scope.type, entry.scope.locator, entry.scope.name, key);
    }
    return resolveOn(base, entry.type, entry.locator, entry.name, key);
}

type LocatorMap = Record<string, LocatorEntry>;

class LocatorManagerImpl {
    private map: LocatorMap | null = null;
    private loadedProject: string | null = null;

    private load(): LocatorMap {
        const project = process.env.PW_PROJECT;
        if (!project) {
            throw new Error('LocatorManager: PW_PROJECT env var is not set.');
        }

        if (this.map && this.loadedProject === project) {
            return this.map;
        }

        const mapPath = path.join(
            'application_assets',
            'projects',
            project,
            'test_creation',
            'locator_map.json'
        );

        if (!fs.existsSync(mapPath)) {
            throw new Error(
                `LocatorManager: locator_map.json not found for '${project}' at ${mapPath}`
            );
        }

        this.map = JSON.parse(fs.readFileSync(mapPath, 'utf8')) as LocatorMap;
        this.loadedProject = project;
        return this.map;
    }

    get(name: string): LocatorEntry {
        const entry = this.load()[name];
        if (!entry) {
            throw new Error(
                `Locator not found : ${name} (project=${process.env.PW_PROJECT})`
            );
        }
        return entry;
    }

    /**
     * Resolve a locator_map.json key directly to a Playwright Locator against
     * *page* — the one place the {type, locator, name?} descriptor turns into
     * a real Locator. Called only from generated Page-class getters
     * (test_creation/pages.ts) and from ActionEngine's own resolve(), which
     * delegates here instead of duplicating this switch.
     */
    resolve(page: Page, name: string): Locator {
        return resolveEntry(page, this.get(name), name);
    }
}

export const LocatorManager = new LocatorManagerImpl();
