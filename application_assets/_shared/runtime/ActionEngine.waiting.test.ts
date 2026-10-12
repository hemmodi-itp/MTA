import { describe, expect, it, vi } from 'vitest';
import { ActionEngine } from './ActionEngine';

function engine(page: any = {}) {
  return new ActionEngine(page, {}, [], { allowedHosts: null, violations: [] });
}

describe('ActionEngine — Phase 4.6 web-first waiting helpers', () => {
  it('waitUntil retries until the function stops throwing (toPass)', async () => {
    let calls = 0;
    await engine().waitUntil('list shows 3 rows', () => {
      calls += 1;
      if (calls < 3) throw new Error('not yet');
    }, { timeout: 2_000, intervals: [10] });
    expect(calls).toBe(3);
  });

  it('waitUntil fails with the description once the timeout is spent', async () => {
    await expect(engine().waitUntil('never ready', () => { throw new Error('nope'); }, { timeout: 150, intervals: [20] }))
      .rejects.toThrow(/never ready|nope/);
  });

  it('pollUntil polls until the value matches (expect.poll)', async () => {
    let n = 0;
    await engine().pollUntil('counter reaches 2', () => ++n, 2, { timeout: 2_000, intervals: [10] });
    expect(n).toBe(2);
  });

  it('pollUntil fails when the value never matches', async () => {
    await expect(engine().pollUntil('stays 0', () => 0, 1, { timeout: 150, intervals: [20] })).rejects.toThrow();
  });

  it('waitForUrl and waitForLoadState delegate to the page', async () => {
    const page = { waitForURL: vi.fn().mockResolvedValue(undefined), waitForLoadState: vi.fn().mockResolvedValue(undefined) };
    const ae = engine(page);
    await ae.waitForUrl(/\/products\/\d+/);
    await ae.waitForLoadState('domcontentloaded');
    expect(page.waitForURL).toHaveBeenCalledWith(/\/products\/\d+/, { timeout: undefined });
    expect(page.waitForLoadState).toHaveBeenCalledWith('domcontentloaded');
  });

  it('waitForTimeout still works for human-authored flows but logs a warning', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const page = { waitForTimeout: vi.fn().mockResolvedValue(undefined) };
    await engine(page).waitForTimeout(250);
    expect(page.waitForTimeout).toHaveBeenCalledWith(250);
    expect(warn.mock.calls.map((c) => String(c[0])).join('\n')).toMatch(/fixed sleep waitForTimeout\(250\)/);
    warn.mockRestore();
  });

  it('a host violation fails the next action and is marked reported', async () => {
    const safety = { allowedHosts: ['127.0.0.1'], violations: ['https://evil.example/'], reported: 0 };
    const ae = new ActionEngine({ waitForURL: vi.fn() } as any, {}, [], safety);
    await expect(ae.waitForUrl('/x')).rejects.toThrow(/left safety.allowed_hosts/);
    expect(safety.reported).toBe(1);
  });
});
