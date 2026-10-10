import { defineConfig, devices } from '@playwright/test';
import fs from 'fs';
import path from 'path';

import { resolveBaseUrl } from './application_assets/_shared/runtime/baseUrl';

// Resolve the base URL Playwright navigates to (Phase 0.6 — fail fast, no default):
//   1. BASE_URL env var — always set by ui_execution/agent.py (per module when a
//      run spans modules with different URLs) and by tools/suite_orchestrator.py.
//   2. PW_PROJECT's project.yaml: `project.url`, else the single distinct
//      `modules[].url` (several distinct module URLs are ambiguous -> error).
//   3. Otherwise an error naming what to set. The old silent
//      'http://localhost:3000' fallback is gone: it pointed tests at whatever
//      listened there (often MTA's own web app).
function loadBaseUrl(): string {
  return resolveBaseUrl(process.env, (projectName) => {
    const yamlPath = path.join('application_assets', 'projects', projectName, 'project.yaml');
    return fs.existsSync(yamlPath) ? fs.readFileSync(yamlPath, 'utf8') : null;
  });
}

const BASE_URL = loadBaseUrl();

export default defineConfig({
  // Root directory where test specs are found — set per project at runtime
  // UIExecutionAgent overrides testDir via CLI: --config playwright.config.ts --project chromium
  testDir: process.env.PW_TEST_DIR || './application_assets',
  testMatch: '**/test_scripts/**/*.spec.ts',

  // Fail the build on CI if any test.only() is left accidentally
  forbidOnly: !!process.env.CI,

  // No retries (so Playwright never reports "flaky"; video/trace 'on-first-retry'
  // therefore never record). Retry/flaky handling is Phase 4.7 of the v3 plan.
  retries: 0,

  // Parallel workers
  workers: process.env.CI ? 1 : 2,

  // Reporters
  reporter: [
    ['list'],
    ['json', { outputFile: process.env.PW_JSON_REPORT || 'playwright-report/results.json' }],
    ['html', { outputFolder: process.env.PW_HTML_REPORT || 'playwright-report/html', open: 'never' }],
  ],

  use: {
    baseURL: BASE_URL,

    // Match the app's data-test attribute instead of Playwright's default data-testid
    testIdAttribute: 'data-test',

    // Pre-load saved auth state (cookies + localStorage) when available.
    // Set PW_STORAGE_STATE to an auth.json path produced by --auth-setup.
    // All browser contexts in this run are pre-authenticated — no login redirect.
    storageState: (() => {
      const p = process.env.PW_STORAGE_STATE;
      return (p && fs.existsSync(p)) ? p : undefined;
    })(),

    // Take screenshot only on failure
    screenshot: 'only-on-failure',

    // Record video on first retry of a failing test
    video: 'on-first-retry',

    // Collect trace on first retry
    trace: 'on-first-retry',

    // Default timeout per action
    actionTimeout: 15_000,

    // Page load timeout
    navigationTimeout: 30_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Global timeout per test
  timeout: 60_000,

  // Expect timeout
  expect: {
    timeout: 10_000,
  },
});
