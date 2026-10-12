import { describe, expect, it } from 'vitest';
import { ConsoleGuard, indexBaseline, loadBaseline, normalizeText, urlPath } from './consoleGuard';

const FORBIDDEN = 'Failed to load resource: the server responded with a status of 403 (Forbidden)';
const BASELINE = {
  schema_version: 2, artifact: 'baseline',
  states: {
    'S-1': { url: 'http://127.0.0.1:8765/admin', role: 'user', console_errors: [{ text: FORBIDDEN, source: 'x' }], page_errors: [] },
    'S-2': { url: 'http://127.0.0.1:8765/products', role: 'user', console_errors: [], page_errors: ['ReferenceError: foo is not defined'] },
  },
};

describe('consoleGuard — baseline diff', () => {
  const baseline = indexBaseline(BASELINE);

  it('an error recorded for the same page path is known; on another page it is new', () => {
    const g = new ConsoleGuard(baseline, 'fail');
    g.record({ kind: 'console', text: FORBIDDEN, url: 'http://localhost:9999/admin?x=1' });   // origin + query ignored
    g.record({ kind: 'console', text: FORBIDDEN, url: 'http://127.0.0.1:8765/cart' });
    expect(g.knownErrors().map((e) => urlPath(e.url))).toEqual(['/admin']);
    expect(g.newErrors().map((e) => urlPath(e.url))).toEqual(['/cart']);
  });

  it('page errors from the baseline are known too; whitespace and ANSI do not matter', () => {
    const g = new ConsoleGuard(baseline, 'fail');
    g.record({ kind: 'pageerror', text: '\x1b[31mReferenceError:  foo is not\ndefined\x1b[0m', url: 'http://127.0.0.1:8765/products/' });
    expect(g.newErrors()).toEqual([]);
    expect(g.failureMessage()).toBeNull();
  });

  it('fail mode reports the new errors; warn mode never fails; off records nothing', () => {
    const fail = new ConsoleGuard(baseline, 'fail');
    fail.record({ kind: 'console', text: 'Failed to load resource: 404 (Not Found)', url: 'http://127.0.0.1:8765/products/999999' });
    expect(fail.failureMessage()).toMatch(/1 new console error\(s\) not in baseline\.json:\n {2}- \[console\] \/products\/999999: Failed to load resource/);
    const warn = new ConsoleGuard(baseline, 'warn');
    warn.record({ kind: 'console', text: 'boom', url: 'http://x/y' });
    expect(warn.newErrors()).toHaveLength(1);
    expect(warn.failureMessage()).toBeNull();
    const off = new ConsoleGuard(baseline, 'off');
    off.record({ kind: 'console', text: 'boom', url: 'http://x/y' });
    expect(off.errors()).toEqual([]);
  });

  it('a missing baseline makes fail mode warn-only, with a note', () => {
    const missing = loadBaseline('/nope/baseline.json', () => null);
    expect(missing.available).toBe(false);
    expect(missing.note).toMatch(/no baseline\.json at \/nope\/baseline\.json — new-error check is warn-only/);
    const g = new ConsoleGuard(missing, 'fail');
    g.record({ kind: 'console', text: 'boom', url: 'http://x/y' });
    expect(g.effectiveMode).toBe('warn');
    expect(g.newErrors()).toHaveLength(1);
    expect(g.failureMessage()).toBeNull();
  });

  it('unreadable or state-less baselines are warn-only too', () => {
    expect(loadBaseline('b.json', () => '{not json').available).toBe(false);
    expect(loadBaseline('b.json', () => '{"states": null}').available).toBe(false);
    expect(loadBaseline('b.json', () => JSON.stringify(BASELINE)).available).toBe(true);
  });

  it('helpers', () => {
    expect(normalizeText('  a \n\t b ')).toBe('a b');
    expect(urlPath('http://h/')).toBe('/');
    expect(urlPath('not a url')).toBe('');
  });
});
