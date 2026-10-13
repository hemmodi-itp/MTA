# Phase 5-lean report — Test Oracles
Flag: `oracles.enabled` in project.yaml (default OFF; ON in the buggy_shop template `project.yaml.tmpl` and bench_buggy_shop).

**Changed**
- ActionEngine.ts: `verifyRequest`, `verifyNoRequest`, `verifyFieldInvalid`, `verifyNoDialog`, `verifyNotInjected`, `verifyNoNewConsoleErrors` (uses Phase 4 `network` / `consoleGuard`; testFixture passes them plus a dialog recorder).
- agent.py `ALLOWED_ACTIONS` + required-field validation (`ORACLE_REQUIRED_FIELDS`); spec_renderer.py renders the actions and, with the flag, appends `verifyNoNewConsoleErrors` to every test (compose/rerender pass the flag).
- New `tools/test_creation/assertion_linter.py` (rules a–e, score 0–100, threshold 70). With the flag, weak tests are regenerated once with linter feedback; still weak → `weak_oracle` list (+ `assertion_score` median) on the spec entry in test_suite.json and `weak_oracle: true` on the plan test.
- prompt.py: oracle block (new actions, test_cases.json oracle → action mapping, lint rules) injected only when flagged.

**Tests** `tests/unit/test_assertion_linter.py` 9 pass (one+ per rule, validation, renderer per action); plus 75 existing renderer/validator/rerender tests pass.
tsc: no errors in runtime files (one pre-existing parse error in an old myTestProjects spec). ActionEngine vitest cannot run here (`yaml` package missing — fails identically without my changes), so the TS actions are type-checked only, not executed.

**Not done / caveats** Single commit (changes intertwine across tasks). Regeneration path not exercised against a live LLM. Deferred items: docs/backlog.md → Phase 5.
