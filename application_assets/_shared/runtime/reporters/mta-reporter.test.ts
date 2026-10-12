import fs from 'fs';
import os from 'os';
import path from 'path';
import { describe, expect, it } from 'vitest';

import MtaReporter, { failedStep, testRecord, testStatus, totals } from './mta-reporter';

const TEST_DIR = path.resolve('/assets');

type R = { status: string; duration?: number; retry?: number; error?: { message: string }; attachments?: any[] };

function makeTest(results: R[], opts: { outcome?: string; title?: string; annotations?: any[]; tags?: string[] } = {}): any {
  const project = { name: 'chromium', testDir: TEST_DIR };
  const file = { type: 'file', title: 'f', parent: undefined, project: () => project };
  const describe = { type: 'describe', title: 'Product form (M03_BS_003)', parent: file, project: () => project };
  const full = results.map((r, i) => ({ retry: i, duration: 100, attachments: [], ...r }));
  return {
    id: 'abc123',
    title: opts.title ?? 'AC-03.3.1 Price min-1 is rejected',
    parent: describe,
    location: { file: path.join(TEST_DIR, 'shop', 'test_creation', 'test_scripts', 'M03', 'test_M03_BS_003_x.spec.ts'), line: 17, column: 3 },
    tags: opts.tags ?? ['@P0', '@negative', '@bva'],
    annotations: opts.annotations ?? [
      { type: 'ac', description: 'AC-03.3.1' },
      { type: 'ac', description: 'AC-03.3.2' },
      { type: 'tc', description: 'M03_TC_035' },
      { type: 'case', description: 'TC-cfd8a28e' },
      { type: 'scenario', description: 'M03_BS_003' },
    ],
    expectedStatus: 'passed',
    results: full,
    outcome: () => opts.outcome ?? 'expected',
  };
}

describe('testStatus', () => {
  it('maps outcome + last attempt to the MTA status', () => {
    expect(testStatus(makeTest([{ status: 'passed' }], { outcome: 'expected' }))).toBe('passed');
    expect(testStatus(makeTest([{ status: 'failed' }, { status: 'passed' }], { outcome: 'flaky' }))).toBe('flaky');
    expect(testStatus(makeTest([{ status: 'failed' }], { outcome: 'unexpected' }))).toBe('failed');
    expect(testStatus(makeTest([{ status: 'timedOut' }], { outcome: 'unexpected' }))).toBe('timedOut');
    expect(testStatus(makeTest([{ status: 'skipped' }], { outcome: 'skipped' }))).toBe('skipped');
    expect(testStatus(makeTest([{ status: 'interrupted' }], { outcome: 'skipped' }))).toBe('interrupted');
    expect(testStatus(makeTest([], { outcome: 'skipped' }))).toBe('skipped');
  });

  it('a fail-then-pass is flaky, never passed', () => {
    expect(testStatus(makeTest([{ status: 'failed' }, { status: 'passed' }], { outcome: 'flaky' }))).not.toBe('passed');
  });
});

describe('testRecord', () => {
  it('links the test to its TC / AC / case / scenario ids and keeps tags', () => {
    const rec = testRecord(makeTest([{ status: 'passed', duration: 250 }])) as any;
    expect(rec).toMatchObject({
      test_id: 'abc123',
      title: 'AC-03.3.1 Price min-1 is rejected',
      title_path: ['Product form (M03_BS_003)', 'AC-03.3.1 Price min-1 is rejected'],
      spec_file: 'shop/test_creation/test_scripts/M03/test_M03_BS_003_x.spec.ts',
      line: 17,
      project: 'chromium',
      tags: ['@P0', '@negative', '@bva'],
      tc_id: 'M03_TC_035',
      case_id: 'TC-cfd8a28e',
      scenario_id: 'M03_BS_003',
      ac_ids: ['AC-03.3.1', 'AC-03.3.2'],
      status: 'passed',
      retries: 0,
      duration_ms: 250,
    });
  });

  it('records every attempt with its ANSI-stripped, bounded error', () => {
    const long = '\x1b[31mexpect(locator).toContainText\x1b[39m ' + 'x'.repeat(5000);
    const rec = testRecord(makeTest([{ status: 'failed', error: { message: long } }, { status: 'passed' }], { outcome: 'flaky' })) as any;
    expect(rec.status).toBe('flaky');
    expect(rec.retries).toBe(1);
    expect(rec.attempts).toHaveLength(2);
    expect(rec.attempts[0].error.startsWith('expect(locator).toContainText')).toBe(true);
    expect(rec.attempts[0].error.length).toBe(2000);
    expect(rec.attempts[1].error).toBeNull();
  });

  it('attachments: name, type and path only — never the body; de-duplicated', () => {
    const shot = { name: 'screenshot', contentType: 'image/png', path: '/r/test-failed-1.png' };
    const inline = { name: 'stdout', contentType: 'text/plain', body: Buffer.from('secret-ish') };
    const rec = testRecord(makeTest([{ status: 'failed', attachments: [shot, inline] }, { status: 'failed', attachments: [shot] }], { outcome: 'unexpected' })) as any;
    expect(rec.attachments).toEqual([
      { name: 'screenshot', content_type: 'image/png', path: '/r/test-failed-1.png' },
      { name: 'stdout', content_type: 'text/plain', path: null },
    ]);
    expect(JSON.stringify(rec)).not.toContain('secret-ish');
  });

  it('a test without MTA annotations still gets a record (nulls, empty ac_ids)', () => {
    const rec = testRecord(makeTest([{ status: 'passed' }], { annotations: [], tags: [] })) as any;
    expect(rec.tc_id).toBeNull();
    expect(rec.case_id).toBeNull();
    expect(rec.ac_ids).toEqual([]);
  });
});

describe('totals', () => {
  it('counts every status', () => {
    expect(totals([{ status: 'passed' }, { status: 'flaky' }, { status: 'failed' }, { status: 'passed' }])).toEqual({
      total: 4, passed: 2, failed: 1, flaky: 1, skipped: 0, timedOut: 0, interrupted: 0,
    });
  });
});

describe('MtaReporter', () => {
  it('writes the contract shape atomically at onEnd', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mta-reporter-'));
    const out = path.join(dir, 'nested', 'run.mta_results.json');
    const tests = [makeTest([{ status: 'passed' }]), makeTest([{ status: 'failed' }, { status: 'passed' }], { outcome: 'flaky', title: 't2' })];
    process.env.MTA_RUN_ID = 'run-1';
    process.env.PW_PROJECT = 'shop';
    const reporter = new MtaReporter({ outputFile: out });
    expect(reporter.printsToStdio()).toBe(false);
    reporter.onBegin({ shard: { current: 1, total: 2 } } as any, { allTests: () => tests } as any);
    reporter.onEnd({ status: 'passed' } as any);
    const doc = JSON.parse(fs.readFileSync(out, 'utf8'));
    expect(doc).toMatchObject({
      schema_version: 2, artifact: 'mta_results', run_id: 'run-1', project: 'shop',
      shard: { current: 1, total: 2 }, status: 'passed',
      totals: { total: 2, passed: 1, flaky: 1 },
    });
    expect(doc.tests.map((t: any) => t.status)).toEqual(['passed', 'flaky']);
    expect(fs.readdirSync(path.dirname(out))).toEqual(['run.mta_results.json']); // no tmp file left
    delete process.env.MTA_RUN_ID;
    delete process.env.PW_PROJECT;
  });
});

describe('Phase 4 session 2 fields', () => {
  const step = (title: string, error?: any, steps: any[] = [], category = 'test.step') => ({ title, category, error, steps });

  it('failed_step = the innermost failed test.step (the plan step), ignoring hooks and API steps', () => {
    const result = {
      steps: [
        step('Before Hooks', undefined, [], 'hook'),
        step('1. Navigate to "/products/new"'),
        step('2. Click "save_product_button"', { message: 'x' }, [step('locator.click', { message: 'x' }, [], 'pw:api')]),
      ],
    };
    expect(failedStep(result as any)).toBe('2. Click "save_product_button"');
    expect(failedStep({ steps: [step('1. ok')] } as any)).toBeNull();
    expect(failedStep({} as any)).toBeNull();
  });

  it('record carries failed_step per attempt and cleanup_failures from the cleanup fixture', () => {
    const t = makeTest([{ status: 'failed', steps: [step('3. Verify "x" is visible', { message: 'nope' })] } as any], {
      outcome: 'unexpected',
      annotations: [{ type: 'tc', description: 'T1' }, { type: 'cleanup_failed', description: 'product 7: 500 boom' }],
    });
    const rec: any = testRecord(t);
    expect(rec.attempts[0].failed_step).toBe('3. Verify "x" is visible');
    expect(rec.cleanup_failures).toEqual(['product 7: 500 boom']);
    expect(rec.status).toBe('failed');
  });
});
