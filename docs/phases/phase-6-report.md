# Phase 6 report — Failure Triage and Safe Healing (complete)

Builds on Phase 6-lean (`b8837d8`). Flag unchanged: project.yaml `healing: {triage, mode}`.

**6.1 Triage** — its own agent now: **TriageAgent** (`agents/test_execution/triage/`, scaffolded, registered as
`triage`, workflow step between `ui_execution` and `healing` in full_workflow and test_execution_and_healing).
Deterministic rules (`tools/triage/triage.py`) gained `known_issue` (project `known_issues.yaml`, with expiry),
**network_error annotations** emitted by the runtime for failed tests (mocked responses marked and ignored), 5xx as
product evidence and 4xx only as a fallback (a negative test's expected 400 no longer hides a locator failure), run
history and cross-browser evidence, ANSI-free error text, and a **failure-time identity probe**: when an element is not
found, ActionEngine checks the page for an element with the key's recorded identity — present → the locator drifted
(test defect), absent → the expected element is missing (product). An assertion whose element never appeared, with
no recorded identity, is a product defect. `tools/triage/service.py`: `environment` → health check of the base URL,
then one re-run (a different failure is classified again); every other failure → one `--repeat-each=3` re-run (any
pass → `flaky`); what stays `unknown` → one LLM call whose verdict is kept only if every quote is in the error.

**6.2** Only `test_defect.*` reach healing. `healing.mode: off` = triage only (YAML's bare `off` handled).
**6.3 Identity check** (`tools/healing/identity.py`, fingerprint JS shared with the TS runtime): role, accessible
name, tag, label, landmark container, position; score ≥ 0.75, a margin over the runner-up, and a similar name
(no-common-word names discounted, so "Name" ≠ "Nickname"). Fingerprints are recorded by ScriptGeneration's live
validation (or `python -m tools.healing.identity capture --project X`). Repair = DOM re-scan on a scratch copy, then a
live identity search; anything else is refused and listed for review. `_dynamic` keys are never live-checked.
**6.5 Blast radius** (`tools/healing/blast.py`): `run_tests` re-runs every spec using a repaired key (direct or via a
flow); a fix that breaks a passing test is **reverted**. **6.7 Burn-in**: fixed tests re-run `--repeat-each=3`; only
then `status: healed`, else `heal_unstable`. **6.8 Model fallback**: primary model, then `adk.fallback`; none usable →
`status: skipped`, `healing: "skipped (<reasons>)"`. **6.9 Audit**: `reports/healing_audit.jsonl` (applied, proposed,
refused, reverted, verified, burn_in_failed; before/after, evidence, confidence, approver). Validation pages sign in
with the module's setup steps and open the entry's own page (one browser per run). The report shows triage counts,
product defects, refusals, reverts, proposals, burn-in and the audit path.

**Benchmark** (`python -m tools.benchmark.healing_bench`, real Chromium, no LLM: the tools the ADK loop calls, in its
order). buggy_shop gained switchable **locator changes** `LOC_01..LOC_12` (`benchmarks/apps/buggy_shop/locator_changes.py`
— renamed ids/test ids, reworded button, wrappers, moved link; LOC_11/12 replace the element with a different one)
with `data-bench-id` ground truth (only while a LOC flag is on).

| KPI | Result | Target |
|---|---|---|
| Heal success, LOC_01–10 | **10/10** (full run 9/10 + LOC_04 re-run, see below) | ≥ 80% |
| Wrong-element heals | **0** | 0 |
| Controls (element replaced) refused | 2/2 | all |
| 10 seeded product bugs classified product_defect | **10/10** | all |
| … failures sent to healing | **0** | 0 |

Files: `benchmarks/results/2026-10-14_buggy_shop_phase6_healing.md` (full run) and
`…_phase6_healing_loc04_rerun.md`. LOC_04 failed in the full run because of two benchmark defects, not healing: the
change renamed an id the app's own script uses (the app threw), and the spec asserted a per-session flash message that
parallel tests sharing one session consumed. Both were fixed (the id stays, specs assert the product page); the re-run
heals LOC_04 to the right element and BUG_01/BUG_05 stay product_defect. The first full run had triaged 5 bugs as
locator defects (Playwright's coloured error text defeated the rules) — fixed and confirmed by the second full run.

**Tests**: `tests/unit/test_phase6_safe_healing.py` 43 (identity incl. real-browser heal/refusal, blast radius,
audit, known issues, network annotations, history/cross-browser, refine steps, cited LLM, revert, burn-in, mode off,
triage reuse, model fallback, probe classification, ANSI); vitest probe + network annotation tests; updated healing and
triage tests; workflow/orchestrator step lists include `triage`.

**Open**: docs/backlog.md → Phase 6 (identity of dynamic elements, same-verb buttons, the ADK loop itself not in the
benchmark).
