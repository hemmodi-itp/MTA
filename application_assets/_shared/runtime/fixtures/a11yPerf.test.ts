import { describe, expect, it, vi } from 'vitest';
import { A11yUnavailableError, axeScan, DEFAULT_TAGS } from './a11y';
import { collectPerf, toMetrics } from './perf';

describe('a11y — AxeBuilder wiring (checks are Phase 7)', () => {
  it('without @axe-core/playwright: a clear error naming the package and Phase 7', async () => {
    const load = () => { throw new Error('Cannot find module'); };
    await expect(axeScan({}, {}, load)).rejects.toBeInstanceOf(A11yUnavailableError);
    await expect(axeScan({}, {}, load)).rejects.toThrow(/@axe-core\/playwright is not installed — accessibility checks arrive with Phase 7/);
  });

  it('with the package: AxeBuilder({ page }).withTags(...).include(...).analyze()', async () => {
    const calls: unknown[] = [];
    class FakeAxe {
      constructor(opts: unknown) { calls.push(['new', opts]); }
      withTags(t: string[]) { calls.push(['tags', t]); return this; }
      include(s: string) { calls.push(['include', s]); return this; }
      exclude(s: string) { calls.push(['exclude', s]); return this; }
      async analyze() { return { violations: [] }; }
    }
    const page = { id: 'p' };
    const out = await axeScan(page, { include: 'main' }, () => ({ default: FakeAxe }));
    expect(out).toEqual({ violations: [] });
    expect(calls).toEqual([['new', { page }], ['tags', DEFAULT_TAGS], ['include', 'main']]);
  });
});

describe('perf — navigation timing + web vitals (budgets are Phase 7)', () => {
  it('maps the page probe to baseline.json timing names + lcp/cls', () => {
    const m = toMetrics({
      nav: { startTime: 0, requestStart: 3, responseStart: 8.4, domContentLoadedEventEnd: 17.2, loadEventEnd: 18, transferSize: 3026 },
      fcp: 28.1, lcp: 40, cls: 0.01234, resources: 2, resourceBytes: 500,
    }, 'http://h/login');
    expect(m).toEqual({ url: 'http://h/login', ttfb_ms: 8, dcl_ms: 17, load_ms: 18, fcp_ms: 28, lcp_ms: 40, cls: 0.012, transfer_bytes: 3526, requests: 3 });
  });

  it('missing entries become null, never NaN', () => {
    expect(toMetrics({ nav: null, fcp: null, lcp: null, cls: null, resources: 0, resourceBytes: 0 }, 'about:blank'))
      .toEqual({ url: 'about:blank', ttfb_ms: null, dcl_ms: null, load_ms: null, fcp_ms: null, lcp_ms: null, cls: null, transfer_bytes: null, requests: 0 });
  });

  it('collectPerf evaluates the probe in the page', async () => {
    const page = { evaluate: vi.fn().mockResolvedValue({ nav: null, fcp: 5, lcp: null, cls: 0, resources: 0, resourceBytes: 0 }), url: () => 'http://h/' };
    const m = await collectPerf(page);
    expect(page.evaluate).toHaveBeenCalledTimes(1);
    expect(m.fcp_ms).toBe(5);
  });
});
