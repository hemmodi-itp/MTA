import { defineConfig } from '@playwright/test';
import fs from 'fs';
import path from 'path';

import { resolveBaseUrl } from './application_assets/_shared/runtime/baseUrl';
import { buildPlaywrightConfig } from './application_assets/_shared/runtime/config/buildConfig';
import { loadProjectYaml } from './application_assets/_shared/runtime/config/projectYaml';

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

// Phase 4.4: every worker of one run shares one run id (testData seeds + entity prefixes). UIExecutionAgent
// sets MTA_RUN_ID; a hand run gets one here, before the workers (which inherit this environment) start.
if (!process.env.MTA_RUN_ID) {
    process.env.MTA_RUN_ID = `local-${new Date().toISOString().replace(/[-:.]/g, '').slice(0, 15)}`;
}

// Everything else comes from PW_PROJECT's `execution:` block (Phase 4: browser/device matrix,
// test-id attribute, locale/timezone, trace/video/screenshot, JUnit + MTA reporters) and the
// env vars UIExecutionAgent sets — see application_assets/_shared/runtime/config/buildConfig.ts.
export default defineConfig(
  buildPlaywrightConfig({
    env: process.env,
    project: loadProjectYaml(process.env.PW_PROJECT),
    baseURL: loadBaseUrl(),
    mtaReporterPath: path.resolve(__dirname, 'application_assets/_shared/runtime/reporters/mta-reporter.ts'),
    exists: fs.existsSync,
  }),
);
