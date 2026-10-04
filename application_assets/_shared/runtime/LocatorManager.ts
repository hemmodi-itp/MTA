import fs from 'fs';
import path from 'path';
import { Locator, Page } from '@playwright/test';

export interface LocatorEntry {
    type: 'css' | 'xpath' | 'role' | 'text' | 'label' | 'testid' | 'placeholder';
    locator: string;
    name?: string;        // used only when type === 'role'
    description?: string;
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
        const entry = this.get(name);
        switch (entry.type) {
            case 'css':
                return page.locator(entry.locator);
            case 'xpath':
                return page.locator(`xpath=${entry.locator}`);
            case 'role':
                return entry.name
                    ? page.getByRole(entry.locator as Parameters<Page['getByRole']>[0], { name: entry.name })
                    : page.getByRole(entry.locator as Parameters<Page['getByRole']>[0]);
            case 'text':
                return page.getByText(entry.locator);
            case 'label':
                return page.getByLabel(entry.locator);
            case 'testid':
                return page.getByTestId(entry.locator);
            case 'placeholder':
                return page.getByPlaceholder(entry.locator);
            default:
                throw new Error(`Unknown locator type for '${name}': ${(entry as LocatorEntry).type}`);
        }
    }
}

export const LocatorManager = new LocatorManagerImpl();
