import { describe, expect, it } from 'vitest';
import { resolveEntry } from './LocatorManager';

// A fake Page/FrameLocator/Locator that records the call chain, so each test can assert exactly
// which Playwright calls a locator_map entry turns into.
function fakeBase(trail: string[] = []): any {
    const step = (call: string) => fakeBase([...trail, call]);
    return {
        trail,
        locator: (s: string) => step(`locator(${s})`),
        getByRole: (r: string, o?: { name?: string }) => step(o ? `getByRole(${r},${o.name})` : `getByRole(${r})`),
        getByText: (s: string) => step(`getByText(${s})`),
        getByLabel: (s: string) => step(`getByLabel(${s})`),
        getByTestId: (s: string) => step(`getByTestId(${s})`),
        getByPlaceholder: (s: string) => step(`getByPlaceholder(${s})`),
        frameLocator: (s: string) => step(`frameLocator(${s})`),
    };
}

describe('resolveEntry — pre-Phase-2 entries resolve exactly as before', () => {
    const cases: Array<[any, string[]]> = [
        [{ type: 'css', locator: '#save' }, ['locator(#save)']],
        [{ type: 'xpath', locator: '//button' }, ['locator(xpath=//button)']],
        [{ type: 'role', locator: 'button', name: 'Save' }, ['getByRole(button,Save)']],
        [{ type: 'role', locator: 'navigation' }, ['getByRole(navigation)']],
        [{ type: 'text', locator: 'Hello' }, ['getByText(Hello)']],
        [{ type: 'label', locator: 'Email' }, ['getByLabel(Email)']],
        [{ type: 'testid', locator: 'save-btn' }, ['getByTestId(save-btn)']],
        [{ type: 'placeholder', locator: 'Search' }, ['getByPlaceholder(Search)']],
    ];
    for (const [entry, trail] of cases) {
        it(`${entry.type} -> ${trail.join('.')}`, () => {
            expect(resolveEntry(fakeBase(), entry).trail).toEqual(trail);
        });
    }

    it('still throws on an unknown type', () => {
        expect(() => resolveEntry(fakeBase(), { type: 'bogus', locator: 'x' } as any, 'k')).toThrow(
            "Unknown locator type for 'k': bogus",
        );
    });
});

describe('resolveEntry — Phase 2 frame and scope', () => {
    it('resolves a scoped role entry inside its container', () => {
        const entry = { type: 'role', locator: 'button', name: 'Save',
            scope: { type: 'role', locator: 'dialog', name: 'Edit user' } } as any;
        expect(resolveEntry(fakeBase(), entry).trail).toEqual(['getByRole(dialog,Edit user)', 'getByRole(button,Save)']);
    });

    it('chains frameLocators before the element', () => {
        const entry = { type: 'testid', locator: 'pay', frame: ['iframe#outer', 'iframe[name="card"]'] } as any;
        expect(resolveEntry(fakeBase(), entry).trail).toEqual(
            ['frameLocator(iframe#outer)', 'frameLocator(iframe[name="card"])', 'getByTestId(pay)'],
        );
    });

    it('applies frame, then scope, then the element', () => {
        const entry = { type: 'role', locator: 'link', name: 'Home', frame: ['#f'],
            scope: { type: 'role', locator: 'contentinfo' } } as any;
        expect(resolveEntry(fakeBase(), entry).trail).toEqual(
            ['frameLocator(#f)', 'getByRole(contentinfo)', 'getByRole(link,Home)'],
        );
    });

    it('rejects an unknown scope type instead of guessing', () => {
        const entry = { type: 'css', locator: '#x', scope: { type: 'nope', locator: 'y' } } as any;
        expect(() => resolveEntry(fakeBase(), entry, 'k')).toThrow("Unknown locator type for 'k': nope");
    });
});
