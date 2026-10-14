# Phase 5 report — Test Oracles (complete)

Builds on Phase 5-lean (`082de1b`). Flag unchanged: `oracles.enabled` in project.yaml (default OFF).

**5.1 New ActionEngine actions** (`ActionEngine.ts`, `ALLOWED_ACTIONS`, `spec_renderer.py`, prompt):
`verifyRequest` now takes `"2xx"`-style status classes and `bodyContains`, and polls up to 5 s for the response;
`verifyValidationMessage`, `verifyAriaSnapshot`, `rememberCount` + `verifyCountChangedBy`, `reloadAndVerify`
(renderer macro), `verifyApiState` (grey-box via the `api` fixture, now passed to ActionEngine), `verifyResponseSchema`
(new `fixtures/jsonSchema.ts` subset validator; NetworkLog keeps JSON response bodies ≤ 256 KB in memory, never in the
HAR), `verifyStorage`, `verifyDownload`, `verifyNewTab`, and fault injection `mockRoute` / `setOffline` / `setClock`.
A mocked ≥ 400 status or going offline tells consoleGuard to expect the matching "Failed to load resource" console
error (`ConsoleGuard.expectConsoleError`); page errors still count.

**5.2 Expected-value precedence**: BRD-vs-observed conflicts (already detected by test design) now go to
`human_review_queue.json` as `expected_value_conflict` (deduplicated across reruns) and to a "Potential defects"
section in the JSON/HTML report. Tests whose case oracles are all LLM-inferred get `oracle_confidence: "low"` and are
counted (`low_confidence_oracles`) in the executive summary.

**5.3 Linter**: new positive-submit rule (UI signal AND backend evidence: `verifyRequest` 2xx/3xx, `reloadAndVerify`,
`verifyApiState`, or a non-zero `verifyCountChangedBy`; search/filter/sort and XSS tests exempt). The new actions count
as outcome / error / no-submit evidence where they apply; steps inside `reloadAndVerify` count as assertions.
Fixed: "fault injection" in a test name no longer triggers the XSS rule.

**5.4**: in design mode the case's oracles fill in what the LLM left out (`_fill_placeholder_oracles`,
`_append_case_oracles`); `_drop_placeholder_negative_tests` treats a case's rejection oracles as a basis.

**Validation**: required fields per action (0/false accepted), `verifyCountChangedBy` needs an earlier `rememberCount`,
`reloadAndVerify` holds only verify steps, fixed store/rule lists for `verifyStorage`.

**Tests**
- `tests/unit/test_phase5_oracles.py` — 62: renderer golden line per action (20), reloadAndVerify plain + stepped,
  step titles, validation accept + 11 rejects, 21-row linter rule table, 5.4 fill-in, low confidence, conflict queue
  dedupe, report section. With `test_assertion_linter.py`: 30+ linter rule cases.
- `ActionEngine.oracles.test.ts` — 23 vitest tests (fakes); `consoleGuard.test.ts` +1. Vitest: 205/205.
- `tests/integration/test_phase5_oracles_e2e.py` — real Chromium on buggy_shop through UIExecutionAgent, spec
  rendered by the real renderer: all 6 oracle tests pass on the bug-free build; **with BUG_18 (empty name silently
  accepted) the strong negative fails ("Name is required" not found) while the weak-oracle version passes** — the
  false-pass check from the acceptance criteria — and the linter flags that weak one (score 65).
- Affected suites: 459 Python tests pass; `tsc --noEmit` clean.

**Not measured**: median assertion score ≥ 80 and "zero title-only tests" on a regenerated suite need an LLM
generation run (not done in this session). See docs/backlog.md → Phase 5.
