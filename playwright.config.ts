import { defineConfig, devices } from '@playwright/test';
import fs from 'fs';
import path from 'path';

// Resolve the base URL Playwright navigates to. Priority:
//   1. BASE_URL env var — set by ui_execution/agent.py from request["url"],
//      which the orchestrator has already resolved to the *active module's*
//      url (project.yaml modules[].url, narrowed by --module). This is the
//      only path that can tell modules apart.
//   2. project.yaml regex-scrape (set via PW_PROJECT env var) — best-effort
//      fallback for running `npx playwright test` directly without going
//      through main.py; grabs the FIRST `url:` field in the file, so it's
//      only correct for single-module projects.
//   3. Hardcoded localhost:3000 default for local dev servers.
// Uses a regex instead of a YAML library so there are no extra npm dependencies.
function loadBaseUrl(): string {
  if (process.env.BASE_URL) return process.env.BASE_URL;

  const projectName = process.env.PW_PROJECT || '';
  if (projectName) {
    const yamlPath = path.join(
      'application_assets', 'projects', projectName, 'project.yaml'
    );
    if (fs.existsSync(yamlPath)) {
      try {
        const content = fs.readFileSync(yamlPath, 'utf8');
        // Leading whitespace allowed — project.yaml nests url: under modules[].
        const match = content.match(/^\s*url:\s*(.+)$/m);
        if (match) return match[1].trim().replace(/^['"]|['"]$/g, '');
      } catch {
        // fall through to default
      }
    }
  }
  return 'http://localhost:3000';
}

const BASE_URL = loadBaseUrl();

export default defineConfig({
  // Root directory where test specs are found — set per project at runtime
  // UIExecutionAgent overrides testDir via CLI: --config playwright.config.ts --project chromium
  testDir: process.env.PW_TEST_DIR || './application_assets',
  testMatch: '**/test_scripts/**/*.spec.ts',

  // Fail the build on CI if any test.only() is left accidentally
  forbidOnly: !!process.env.CI,

  // Retry once on failure before marking as failed
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
