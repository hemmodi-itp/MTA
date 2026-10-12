// perf.ts — the `perf` fixture: navigation timing + Web Vitals of the current page (Phase 4.4, wiring only).
//
// Field names match test_comprehension/baseline.json `timing` (ttfb_ms, dcl_ms, load_ms, fcp_ms, transfer_bytes,
// requests) plus lcp_ms and cls. TODO(Phase 7.3): budgets in project.yaml compared with baseline.json.

export interface PerfRaw {
  nav: {
    requestStart?: number; responseStart?: number; domContentLoadedEventEnd?: number; loadEventEnd?: number;
    startTime?: number; transferSize?: number;
  } | null;
  fcp: number | null;
  lcp: number | null;
  cls: number | null;
  resources: number;
  resourceBytes: number;
}

export interface PerfMetrics {
  url: string;
  ttfb_ms: number | null;
  dcl_ms: number | null;
  load_ms: number | null;
  fcp_ms: number | null;
  lcp_ms: number | null;
  cls: number | null;
  transfer_bytes: number | null;
  requests: number;
}

const ms = (v: number | undefined | null): number | null =>
  typeof v === 'number' && Number.isFinite(v) && v > 0 ? Math.round(v) : null;

export function toMetrics(raw: PerfRaw, url: string): PerfMetrics {
  const nav = raw.nav ?? {};
  const start = nav.startTime ?? 0;
  return {
    url,
    ttfb_ms: ms((nav.responseStart ?? 0) - start),
    dcl_ms: ms((nav.domContentLoadedEventEnd ?? 0) - start),
    load_ms: ms((nav.loadEventEnd ?? 0) - start),
    fcp_ms: ms(raw.fcp),
    lcp_ms: ms(raw.lcp),
    cls: typeof raw.cls === 'number' ? Math.round(raw.cls * 1000) / 1000 : null,
    transfer_bytes: raw.nav ? (nav.transferSize ?? 0) + raw.resourceBytes : null,
    requests: (raw.nav ? 1 : 0) + raw.resources,
  };
}

/** Runs in the page. Buffered observers deliver LCP / layout-shift entries recorded before this call. */
export const PERF_PROBE = (): Promise<PerfRaw> =>
  new Promise((resolve) => {
    const perf = performance as any;
    const nav = perf.getEntriesByType('navigation')[0] ?? null;
    const fcp = perf.getEntriesByType('paint').find((e: any) => e.name === 'first-contentful-paint');
    const res = perf.getEntriesByType('resource');
    let lcp: number | null = null;
    let cls: number | null = null;
    try {
      new PerformanceObserver((list) => {
        for (const e of list.getEntries()) lcp = (e as any).startTime;
      }).observe({ type: 'largest-contentful-paint', buffered: true } as any);
    } catch { /* not supported (firefox / webkit) */ }
    try {
      new PerformanceObserver((list) => {
        for (const e of list.getEntries() as any[]) if (!e.hadRecentInput) cls = (cls ?? 0) + e.value;
      }).observe({ type: 'layout-shift', buffered: true } as any);
    } catch { /* not supported */ }
    // one task later, so the buffered entries have been delivered to the observers above
    setTimeout(() => resolve({
      nav: nav ? nav.toJSON() : null,
      fcp: fcp ? fcp.startTime : null,
      lcp,
      cls: cls ?? (nav ? 0 : null),
      resources: res.length,
      resourceBytes: res.reduce((s: number, r: any) => s + (r.transferSize || 0), 0),
    }), 0);
  });

export async function collectPerf(page: { evaluate: (fn: () => Promise<PerfRaw>) => Promise<PerfRaw>; url: () => string }): Promise<PerfMetrics> {
  return toMetrics(await page.evaluate(PERF_PROBE), page.url());
}
