// mta-reporter.ts — per-test results for MTA (Phase 4.2), consumed by tools/execution/mta_results.py.
//
// Output (contract `mta_results`, schema_version 2; written atomically to `outputFile`):
//   { schema_version, artifact, run_id, project, shard, started_at, finished_at, status, totals,
//     tests: [{ test_id, title, title_path, spec_file, line, project, tags, annotations,
//               tc_id, case_id, scenario_id, ac_ids, status, outcome, expected_status, retries,
//               duration_ms, attempts: [{retry, status, duration_ms, error, failed_step}],
//               attachments: [{name, content_type, path}], cleanup_failures: [string] }] }
// failed_step (Phase 4.5): title of the innermost failed test.step — the plan step that failed.
// cleanup_failures (Phase 4.4): the `cleanup` fixture's `cleanup_failed` annotations.
//
// status ∈ passed | failed | flaky | skipped | timedOut | interrupted. A test that failed and then
// passed on a retry is "flaky" — never "passed". Attachments are referenced by path; bodies are never
// copied (an inline body is reported without a path). Also runs under `merge-reports` (sharded runs).

import fs from 'fs';
import path from 'path';
import type { FullConfig, FullResult, Reporter, Suite, TestCase, TestResult, TestStep } from '@playwright/test/reporter';

export type MtaStatus = 'passed' | 'failed' | 'flaky' | 'skipped' | 'timedOut' | 'interrupted';

const ANSI = /\x1b\[[0-9;]*m/g;
const MAX_ERROR = 2000;

export function testStatus(test: Pick<TestCase, 'outcome' | 'results'>): MtaStatus {
  const results = test.results;
  if (!results.length) return 'skipped';
  const outcome = test.outcome();
  if (outcome === 'flaky') return 'flaky';
  if (outcome === 'expected') return 'passed';
  const last = results[results.length - 1];
  if (outcome === 'skipped') return results.some((r) => r.status === 'interrupted') ? 'interrupted' : 'skipped';
  if (last.status === 'timedOut') return 'timedOut';
  if (last.status === 'interrupted') return 'interrupted';
  return 'failed';
}

function errorText(result: TestResult): string | null {
  const err = result.error ?? result.errors?.[0];
  const text = (err?.message ?? err?.value ?? '').replace(ANSI, '').trim();
  return text ? text.slice(0, MAX_ERROR) : null;
}

/** Title of the innermost failed `test.step` of an attempt (renderer step titles name the plan step), or null. */
export function failedStep(result: Pick<TestResult, 'steps'>): string | null {
  let found: string | null = null;
  const walk = (steps: TestStep[]) => {
    for (const s of steps ?? []) {
      if (s.category === 'test.step' && s.error) found = s.title;
      walk(s.steps);
    }
  };
  walk(result.steps);
  return found;
}

function describeTitles(test: TestCase): string[] {
  const titles: string[] = [];
  for (let s: Suite | undefined = test.parent; s && s.type === 'describe'; s = s.parent) titles.unshift(s.title);
  return [...titles, test.title];
}

function annotationValues(test: TestCase, type: string): string[] {
  return test.annotations.filter((a) => a.type === type && a.description).map((a) => String(a.description));
}

export function testRecord(test: TestCase): Record<string, unknown> {
  const project = test.parent.project();
  const root = project?.testDir ?? '';
  const status = testStatus(test);
  const attachments: Array<{ name: string; content_type: string; path: string | null }> = [];
  const seen = new Set<string>();
  for (const r of test.results) {
    for (const a of r.attachments) {
      const key = `${a.name}|${a.path ?? ''}`;
      if (seen.has(key)) continue;
      seen.add(key);
      attachments.push({ name: a.name, content_type: a.contentType, path: a.path ?? null });
    }
  }
  const tc = annotationValues(test, 'tc');
  const caseId = annotationValues(test, 'case');
  const scenario = annotationValues(test, 'scenario');
  return {
    test_id: test.id,
    title: test.title,
    title_path: describeTitles(test),
    spec_file: (root ? path.relative(root, test.location.file) : test.location.file).split(path.sep).join('/'),
    line: test.location.line,
    project: project?.name ?? '',
    tags: [...test.tags],
    annotations: test.annotations.map((a) => ({ type: a.type, description: a.description ?? '' })),
    tc_id: tc[0] ?? null,
    case_id: caseId[0] ?? null,
    scenario_id: scenario[0] ?? null,
    ac_ids: annotationValues(test, 'ac'),
    status,
    outcome: test.outcome(),
    expected_status: test.expectedStatus,
    retries: Math.max(0, test.results.length - 1),
    duration_ms: test.results.reduce((sum, r) => sum + (r.duration > 0 ? r.duration : 0), 0),
    attempts: test.results.map((r) => ({
      retry: r.retry, status: r.status, duration_ms: r.duration, error: errorText(r), failed_step: failedStep(r),
    })),
    attachments,
    cleanup_failures: annotationValues(test, 'cleanup_failed'),
  };
}

export function totals(tests: Array<{ status: unknown }>): Record<string, number> {
  const out: Record<string, number> = { total: tests.length, passed: 0, failed: 0, flaky: 0, skipped: 0, timedOut: 0, interrupted: 0 };
  for (const t of tests) out[String(t.status)] = (out[String(t.status)] ?? 0) + 1;
  return out;
}

export function writeAtomic(file: string, data: unknown): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2), 'utf8');
  fs.renameSync(tmp, file);
}

export default class MtaReporter implements Reporter {
  private readonly outputFile: string;
  private config?: FullConfig;
  private suite?: Suite;
  private startedAt = new Date();

  constructor(options: { outputFile?: string } = {}) {
    this.outputFile = options.outputFile || process.env.MTA_RESULTS_FILE || 'playwright-report/mta_results.json';
  }

  printsToStdio(): boolean {
    return false;
  }

  onBegin(config: FullConfig, suite: Suite): void {
    this.config = config;
    this.suite = suite;
    this.startedAt = new Date();
  }

  onEnd(result: FullResult): void {
    const tests = (this.suite?.allTests() ?? []).map(testRecord);
    const shard = this.config?.shard ?? null;
    writeAtomic(this.outputFile, {
      schema_version: 2,
      artifact: 'mta_results',
      run_id: process.env.MTA_RUN_ID || null,
      project: process.env.PW_PROJECT || null,
      shard: shard ? { current: shard.current, total: shard.total } : null,
      started_at: this.startedAt.toISOString(),
      finished_at: new Date().toISOString(),
      status: result.status,
      totals: totals(tests),
      tests,
    });
  }
}
