// buildConfig.ts — playwright.config.ts as a pure function of (env, project.yaml) (Phase 4.2).
//
// playwright.config.ts only resolves the base URL (baseUrl.ts, fail fast), reads project.yaml and calls
// buildPlaywrightConfig(). playwright.merge.config.ts calls buildMergeConfig() (reporters only — a
// merge has no target, so it must not resolve a base URL).
//
// Env vars (set by UIExecutionAgent; all optional for a hand run):
//   PW_TEST_DIR, PW_JSON_REPORT, PW_HTML_REPORT, PW_STORAGE_STATE   (unchanged since Phase 0)
//   PW_JUNIT_REPORT     JUnit XML path        (execution.junit, default on)
//   MTA_RESULTS_FILE    MTA reporter output   (execution.mta_reporter, default on)
//   PW_BLOB_DIR         add the blob reporter (sharded runs)
//   MTA_BLOB_ONLY=1     only list + blob (each shard of a local N-shard run; the merge writes the rest)
//   MTA_PROJECTS        comma list of projects to define (a request's browser override); else the matrix

import type { PlaywrightTestConfig, ReporterDescription } from '@playwright/test';
import { devices } from 'playwright-core';

import { ExecutionConfig, KNOWN_PROJECTS, resolveExecutionConfig } from './execution';

type Env = Record<string, string | undefined>;

export interface BuildInput {
  env: Env;
  project: Record<string, any> | null;
  baseURL: string;
  mtaReporterPath: string;
  exists?: (file: string) => boolean;
  warn?: (message: string) => void;
}

const PROJECT_DEVICES: Record<string, string> = {
  chromium: 'Desktop Chrome',
  firefox: 'Desktop Firefox',
  webkit: 'Desktop Safari',
  'pixel-7': 'Pixel 7',
  'iphone-14': 'iPhone 14',
};

/** Projects to define: MTA_PROJECTS (exact list of known names) when set, else the resolved matrix. */
export function projectNames(env: Env, exec: ExecutionConfig): string[] {
  const fromEnv = (env.MTA_PROJECTS || '')
    .split(',')
    .map((p) => p.trim())
    .filter((p) => (KNOWN_PROJECTS as readonly string[]).includes(p));
  return fromEnv.length ? KNOWN_PROJECTS.filter((p) => fromEnv.includes(p)) : exec.projects;
}

export function buildProjects(names: string[]): NonNullable<PlaywrightTestConfig['projects']> {
  return names.map((name) => ({ name, use: { ...devices[PROJECT_DEVICES[name]] } }));
}

export function buildReporters(env: Env, exec: ExecutionConfig, mtaReporterPath: string): ReporterDescription[] {
  if (env.MTA_BLOB_ONLY === '1' && env.PW_BLOB_DIR) {
    return [['list'], ['blob', { outputDir: env.PW_BLOB_DIR }]];
  }
  const reporters: ReporterDescription[] = [
    ['list'],
    ['json', { outputFile: env.PW_JSON_REPORT || 'playwright-report/results.json' }],
    ['html', { outputFolder: env.PW_HTML_REPORT || 'playwright-report/html', open: 'never' }],
  ];
  if (exec.junit) reporters.push(['junit', { outputFile: env.PW_JUNIT_REPORT || 'playwright-report/junit.xml' }]);
  if (exec.mta_reporter) {
    reporters.push([mtaReporterPath, { outputFile: env.MTA_RESULTS_FILE || 'playwright-report/mta_results.json' }]);
  }
  if (env.PW_BLOB_DIR) reporters.push(['blob', { outputDir: env.PW_BLOB_DIR }]);
  return reporters;
}

export function buildPlaywrightConfig(input: BuildInput): PlaywrightTestConfig {
  const { env, project, baseURL, mtaReporterPath } = input;
  const exists = input.exists ?? (() => false);
  const exec = resolveExecutionConfig(project, input.warn);
  const storage = env.PW_STORAGE_STATE;

  const use: PlaywrightTestConfig['use'] = {
    baseURL,
    // execution.test_id_attribute (default data-testid). Python live validation uses the same one.
    testIdAttribute: exec.test_id_attribute,
    // Pre-load saved auth state (cookies + localStorage) when available — single-identity projects
    // (PW_STORAGE_STATE from --auth-setup). test.use({ role }) overrides it per test (testFixture.ts).
    storageState: storage && exists(storage) ? storage : undefined,
    screenshot: exec.screenshot as any,
    video: exec.video as any,
    trace: exec.trace as any,
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  };
  if (exec.locale) use.locale = exec.locale;
  if (exec.timezone_id) use.timezoneId = exec.timezone_id;

  return {
    // UIExecutionAgent sets PW_TEST_DIR and passes this project's spec paths as CLI targets.
    testDir: env.PW_TEST_DIR || './application_assets',
    testMatch: '**/test_scripts/**/*.spec.ts',
    // Fail the build on CI if any test.only() is left accidentally
    forbidOnly: !!env.CI,
    // Still 0: retries arrive with flaky classification (Phase 4.7) — until then the execution agent
    // would count a fail-then-pass as a pass. fullyParallel waits for 4.4's per-test data isolation.
    retries: 0,
    workers: env.CI ? 1 : 2,
    reporter: buildReporters(env, exec, mtaReporterPath),
    use,
    projects: buildProjects(projectNames(env, exec)),
    timeout: 60_000,
    expect: { timeout: 10_000 },
  };
}

/** Reporters for `npx playwright merge-reports` (only the ones whose output path is set, plus json/html). */
export function buildMergeConfig(env: Env, mtaReporterPath: string): PlaywrightTestConfig {
  const reporters: ReporterDescription[] = [
    ['list'],
    ['json', { outputFile: env.PW_JSON_REPORT || 'playwright-report/results.json' }],
    ['html', { outputFolder: env.PW_HTML_REPORT || 'playwright-report/html', open: 'never' }],
  ];
  if (env.PW_JUNIT_REPORT) reporters.push(['junit', { outputFile: env.PW_JUNIT_REPORT }]);
  if (env.MTA_RESULTS_FILE) reporters.push([mtaReporterPath, { outputFile: env.MTA_RESULTS_FILE }]);
  return { reporter: reporters, testDir: env.PW_TEST_DIR || './application_assets' };
}
