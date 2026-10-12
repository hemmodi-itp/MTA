import { defineConfig } from '@playwright/test';
import path from 'path';

import { buildMergeConfig } from './application_assets/_shared/runtime/config/buildConfig';

// Config for `npx playwright merge-reports` (Phase 4.8 — sharded runs; see tools/execution/merge_reports.py).
// Reporters only, driven by the same env vars as a normal run (PW_JSON_REPORT, PW_HTML_REPORT,
// PW_JUNIT_REPORT, MTA_RESULTS_FILE). Deliberately does NOT resolve a base URL: playwright.config.ts
// fails fast without one, and merging blob reports has no target to test.
export default defineConfig(
  buildMergeConfig(process.env, path.resolve(__dirname, 'application_assets/_shared/runtime/reporters/mta-reporter.ts')),
);
