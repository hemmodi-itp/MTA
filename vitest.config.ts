import { defineConfig } from 'vitest/config';

// Scoped to application_assets/_shared/runtime/ only — Playwright owns
// application_assets/**/test_scripts/**/*.spec.ts (real e2e specs, run via
// `npm test`), and vitest's default include glob would otherwise try to
// execute thousands of generated specs as unit tests.
export default defineConfig({
  test: {
    include: ['application_assets/_shared/runtime/**/*.test.ts'],
  },
});
