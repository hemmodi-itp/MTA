// testData.ts — unique, deterministic test data per test (Phase 4.4 `testData` fixture).
//
// Seed = runId (MTA_RUN_ID, set by UIExecutionAgent; playwright.config.ts sets one for a hand run) + the
// Playwright test id + repeat-each index + retry. Same seed -> same values, so a run can be reproduced; a retry
// or a --repeat-each copy gets fresh values, so an entity a failed attempt left behind can't collide with it.
// Every created entity should carry `prefix` (mta<run><test>) so it can be traced to its run and cleaned up.
// No faker: uniqueness and determinism are what isolation needs, not realistic names.

export interface TestDataSeed {
  runId: string;
  testId: string;
  repeatEachIndex?: number;
  retry?: number;
}

/** 32-bit FNV-1a. */
export function fnv1a(text: string, seed = 0x811c9dc5): number {
  let h = seed >>> 0;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

/** mulberry32 PRNG: uniform floats in [0, 1). */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function base36(n: number, width: number): string {
  return n.toString(36).padStart(width, '0').slice(-width);
}

/** A 53-bit hash rendered in base 36 (two independent FNV-1a seeds). */
function hash53(text: string, width: number): string {
  const hi = fnv1a(text, 0x811c9dc5) & 0x1fffff;   // 21 bits
  const lo = fnv1a(text, 0x01000193);               // 32 bits
  return base36(hi * 4294967296 + lo, width);
}

function slug(label: string): string {
  return String(label).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'item';
}

export function runIdFromEnv(env: Record<string, string | undefined> = process.env): string {
  return env.MTA_RUN_ID || 'local';
}

const ALNUM = 'abcdefghijklmnopqrstuvwxyz0123456789';

export class TestData {
  readonly runId: string;
  /** mta + 4 chars of the run hash + 7 of the test hash (14 chars). */
  readonly prefix: string;
  private readonly rand: () => number;
  private counter = 0;

  constructor(seed: TestDataSeed) {
    this.runId = seed.runId;
    const testKey = `${seed.testId}|${seed.repeatEachIndex ?? 0}|${seed.retry ?? 0}`;
    this.prefix = `mta${hash53(seed.runId, 4)}${hash53(testKey, 7)}`;
    this.rand = mulberry32(fnv1a(`${seed.runId}|${testKey}`));
  }

  /** Next float in [0, 1). */
  next(): number {
    return this.rand();
  }

  /** Integer in [min, max] (inclusive). */
  int(min: number, max: number): number {
    if (max < min) throw new Error(`testData.int: max (${max}) < min (${min})`);
    return min + Math.floor(this.rand() * (max - min + 1));
  }

  string(length: number, alphabet = ALNUM): string {
    let out = '';
    for (let i = 0; i < length; i++) out += alphabet[Math.floor(this.rand() * alphabet.length)];
    return out;
  }

  pick<T>(list: readonly T[]): T {
    if (!list.length) throw new Error('testData.pick: empty list');
    return list[Math.floor(this.rand() * list.length)];
  }

  /** "<prefix>-<label>-<n>", unique in the run. maxLength shortens the label, never the prefix or counter. */
  unique(label = 'item', opts: { maxLength?: number } = {}): string {
    const n = ++this.counter;
    let core = slug(label);
    const fixed = `${this.prefix}--${n}`.length;
    if (opts.maxLength !== undefined) {
      if (fixed + 1 > opts.maxLength) {
        throw new Error(`testData.unique: maxLength ${opts.maxLength} is shorter than the run prefix (${fixed + 1})`);
      }
      core = core.slice(0, opts.maxLength - fixed).replace(/-+$/, '') || 'x';
    }
    return `${this.prefix}-${core}-${n}`;
  }

  /** <prefix>.<label><n>@example.test (RFC 2606 reserved domain — never delivers mail). */
  email(label = 'user'): string {
    return `${this.prefix}.${slug(label).replace(/-/g, '')}${++this.counter}@example.test`;
  }
}
