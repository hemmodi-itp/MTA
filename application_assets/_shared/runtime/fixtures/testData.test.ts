import { describe, expect, it } from 'vitest';
import { fnv1a, mulberry32, runIdFromEnv, TestData } from './testData';

const seed = { runId: 'run-20261012', testId: 'abc123-def', repeatEachIndex: 0, retry: 0 };

describe('testData — determinism', () => {
  it('same seed -> same prefix and the same value sequence', () => {
    const a = new TestData(seed);
    const b = new TestData(seed);
    expect(a.prefix).toBe(b.prefix);
    expect([a.int(1, 1000), a.string(8), a.unique('Widget'), a.email('alice')])
      .toEqual([b.int(1, 1000), b.string(8), b.unique('Widget'), b.email('alice')]);
  });

  it('another test, a retry or a repeat-each copy gets different data', () => {
    const base = new TestData(seed);
    for (const other of [{ ...seed, testId: 'other' }, { ...seed, retry: 1 }, { ...seed, repeatEachIndex: 1 }]) {
      const t = new TestData(other);
      expect(t.prefix).not.toBe(base.prefix);
      expect(t.unique('Widget')).not.toBe(new TestData(seed).unique('Widget'));
    }
  });

  it('the prefix carries the run: same run -> same 4-char run part, other run -> different', () => {
    const a = new TestData(seed).prefix;
    const sameRun = new TestData({ ...seed, testId: 'x' }).prefix;
    const otherRun = new TestData({ ...seed, runId: 'run-2' }).prefix;
    expect(a).toMatch(/^mta[0-9a-z]{11}$/);
    expect(sameRun.slice(0, 7)).toBe(a.slice(0, 7));
    expect(otherRun.slice(0, 7)).not.toBe(a.slice(0, 7));
  });

  it('fnv1a and mulberry32 are stable', () => {
    expect(fnv1a('')).toBe(0x811c9dc5);
    expect(fnv1a('a')).toBe(0xe40c292c);
    const r = mulberry32(42);
    const first = [r(), r(), r()];
    const r2 = mulberry32(42);
    expect([r2(), r2(), r2()]).toEqual(first);
    for (const v of first) expect(v >= 0 && v < 1).toBe(true);
  });
});

describe('testData — uniqueness', () => {
  it('10 000 tests of one run get 10 000 distinct prefixes', () => {
    const prefixes = new Set<string>();
    for (let i = 0; i < 10_000; i++) prefixes.add(new TestData({ runId: 'r', testId: `t${i}` }).prefix);
    expect(prefixes.size).toBe(10_000);
  });

  it('unique() never repeats within a test', () => {
    const t = new TestData(seed);
    const values = new Set<string>();
    for (let i = 0; i < 10_000; i++) values.add(t.unique('Widget'));
    expect(values.size).toBe(10_000);
  });

  it('unique() respects maxLength by shortening the label, never the prefix', () => {
    const t = new TestData(seed);
    const v = t.unique('A very long product name that would break a 50 char limit', { maxLength: 30 });
    expect(v.length).toBeLessThanOrEqual(30);
    expect(v.startsWith(`${t.prefix}-`)).toBe(true);
    expect(() => t.unique('x', { maxLength: 10 })).toThrow(/shorter than the run prefix/);
  });

  it('email uses the RFC 2606 reserved domain', () => {
    expect(new TestData(seed).email('Alice Smith')).toMatch(/^mta[0-9a-z]{11}\.alicesmith1@example\.test$/);
  });

  it('int / pick / string stay in range', () => {
    const t = new TestData(seed);
    for (let i = 0; i < 500; i++) {
      const n = t.int(3, 7);
      expect(n >= 3 && n <= 7).toBe(true);
    }
    expect(['a', 'b']).toContain(t.pick(['a', 'b']));
    expect(t.string(12, 'xy')).toMatch(/^[xy]{12}$/);
    expect(() => t.pick([])).toThrow();
    expect(() => t.int(5, 1)).toThrow();
  });

  it('runIdFromEnv falls back to "local"', () => {
    expect(runIdFromEnv({ MTA_RUN_ID: 'r1' })).toBe('r1');
    expect(runIdFromEnv({})).toBe('local');
  });
});
