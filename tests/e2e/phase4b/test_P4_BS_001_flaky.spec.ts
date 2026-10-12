// Phase 4 acceptance criterion 3 — a deliberately flaky test (fails on the first attempt, passes on the retry)
// must be reported as "flaky", never "passed", end to end. Copied into bench_p4b_e2e/test_creation/test_scripts/P4B/.
import { test, expect } from '../../../../../_shared/runtime/fixtures/testFixture';

test.describe('flaky classification (P4_BS_001)', () => {
  test('deliberately flaky: fails first, passes on retry', {
    tag: ['@flaky-demo'],
    annotation: [{ type: 'ac', description: 'AC-90.1' }, { type: 'tc', description: 'P4B_TC_001' }],
  }, async ({}, testInfo) => {
    expect(testInfo.retry, 'the first attempt fails on purpose').toBeGreaterThan(0);
  });

  test('stable check', {
    tag: ['@flaky-demo'],
    annotation: [{ type: 'ac', description: 'AC-90.2' }, { type: 'tc', description: 'P4B_TC_002' }],
  }, async () => {
    expect(1 + 1).toBe(2);
  });
});
