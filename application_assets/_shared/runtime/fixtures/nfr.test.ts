import { describe, expect, it } from 'vitest';
import {
  a11yFindings, acceptFindings, checkBlankTargets, checkErrorPage, checkMixedContent, checkStackTrace, formErrorFindings,
  keyboardFindings, layoutFindings, perfFindings, split,
} from './nfr';

describe('a11y findings', () => {
  it('maps impact to fail/warn and drops accepted issues (globally or per page)', () => {
    const v = [{ id: 'label', impact: 'critical', help: 'Form elements must have labels', nodes: [1] },
               { id: 'region', impact: 'moderate', nodes: [1, 2] },
               { id: 'color-contrast', impact: 'serious', nodes: [1] }];
    const out = a11yFindings(v, '/login', [{ rule: 'color-contrast', url_template: '/login' }, { rule: 'x' }]);
    expect(out.map((x) => [x.rule, x.level])).toEqual([['axe:label', 'fail'], ['axe:region', 'warn']]);
    expect(a11yFindings(v, '/cart', [{ rule: 'color-contrast', url_template: '/login' }])).toHaveLength(3);
  });
});

describe('keyboard and form-error findings', () => {
  it('trap and unreachable fail; invisible focus warns', () => {
    const out = keyboardFindings({ focusable: ['a', 'b', 'c'], reached: ['a', 'b'], invisible: ['b'], trapped: null });
    expect(out.map((x) => [x.rule, x.level])).toEqual([['keyboard-unreachable', 'fail'], ['focus-visible', 'warn']]);
    expect(keyboardFindings({ focusable: ['a', 'b'], reached: ['a'], invisible: [], trapped: 'a' })[0].rule).toBe('keyboard-trap');
  });
  it('an unannounced error fails, focus not moved warns', () => {
    expect(formErrorFindings({ announced: true, focusOnInvalid: true, invalidCount: 1 }, 'f')).toEqual([]);
    const out = formErrorFindings({ announced: false, focusOnInvalid: false, invalidCount: 2 }, 'f');
    expect(out.map((x) => x.level)).toEqual(['fail', 'warn']);
  });
});

describe('performance budgets', () => {
  it('over budget fails; regression beyond the % is reported at the chosen level', () => {
    const m = { ttfb_ms: 3600, load_ms: 3900, requests: 12, url: 'x' };
    const out = perfFindings(m, { ttfb_ms: 1500, requests: 50 }, { ttfb_ms: 40, load_ms: 300 }, 50, 'fail');
    expect(out.map((x) => x.rule)).toEqual(['budget:ttfb_ms', 'regression:ttfb_ms', 'regression:load_ms']);
    expect(perfFindings({ ttfb_ms: 90 }, {}, { ttfb_ms: 10 })).toEqual([]);   // tiny absolute values are noise
  });
});

describe('passive security additions', () => {
  it('accepted findings (rule [+ page]) become warnings with their reason; nothing is accepted by default', () => {
    const found = [{ rule: 'csp', message: 'CSP missing', level: 'fail' as const },
      { rule: 'referrer-policy', message: 'Referrer-Policy missing', level: 'fail' as const }];
    expect(acceptFindings(found, '/cart')).toEqual(found);
    const out = acceptFindings(found, '/cart', [{ rule: 'csp', reason: 'not in the BRD' },
      { rule: 'referrer-policy', url_template: '/admin' }]);
    expect(out[0]).toEqual({ rule: 'csp', message: 'CSP missing (accepted: not in the BRD)', level: 'warn' });
    expect(out[1].level).toBe('fail');                                     // accepted on /admin only
    expect(split(out, [], 'security').map((x) => x.rule)).toEqual(['referrer-policy']);
  });
  it('stack traces and framework errors', () => {
    expect(checkStackTrace('Traceback (most recent call last):\n  File "app.py"')[0].rule).toBe('stack-trace');
    expect(checkStackTrace('    at Object.handler (/srv/app/index.js:12:5)')).toHaveLength(1);
    expect(checkStackTrace('Your order was placed')).toEqual([]);
  });
  it('mixed content only on https pages', () => {
    expect(checkMixedContent('https://a/x', ['http://cdn/x.js', 'https://cdn/y.js', 'http://cdn/x.js'])).toHaveLength(1);
    expect(checkMixedContent('http://a/x', ['http://cdn/x.js'])).toEqual([]);
  });
  it('target=_blank without noopener warns', () => {
    const out = checkBlankTargets([{ href: 'https://x', target: '_blank', rel: null },
                                   { href: 'https://y', target: '_blank', rel: 'noopener noreferrer' }]);
    expect(out.map((x) => [x.rule, x.level])).toEqual([['target-blank', 'warn']]);
  });
  it('error pages: 5xx, blank, stack trace', () => {
    expect(checkErrorPage(500, 'Internal Server Error', 'search').map((x) => x.rule)).toEqual(['server-error']);
    expect(checkErrorPage(200, '  ', 'p').map((x) => x.rule)).toEqual(['blank-page']);
    expect(checkErrorPage(400, 'Please enter a valid value', 'p')).toEqual([]);
  });
});

describe('layout findings and split', () => {
  it('overflow fails; small targets and clipped text warn', () => {
    const out = layoutFindings({ viewport: 320, scrollWidth: 480, offenders: ['table#t (right edge 480px)'],
                                 smallTargets: ['a#x 12x12'], clipped: ['div#c'] }, '/p @320');
    expect(out.map((x) => [x.rule, x.level])).toEqual([['horizontal-overflow', 'fail'], ['touch-target', 'warn'],
                                                       ['clipped-text', 'warn']]);
    const ann: Array<{ type: string; description: string }> = [];
    expect(split(out, ann, 'responsive').map((x) => x.rule)).toEqual(['horizontal-overflow']);
    expect(ann.map((a) => a.type)).toEqual(['responsive-warning', 'responsive-warning']);
  });
});
