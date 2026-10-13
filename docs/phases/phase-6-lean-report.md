# Phase 6-lean report — Triage + Safe Healing
**Changed**
- `tools/triage/triage.py`: deterministic classifier (product_defect | test_defect.locator | test_defect.data | environment | flaky | unknown) with evidence per verdict; writes `reports/triage.json`.
- `HealingAgent`: runs triage first; heals only test_defect.*; product_defect → `reports/defects.json`, never patched. Result carries `triage`, `mode`, `proposals`.
- `healing.mode: auto|propose` — propose writes diffs (incl. locator_map.json delta, via scratch copy) to `test_creation/healing_proposals/<run>/`; nothing applied.
- `apply_patch` already rejected `waitForTimeout`/`setTimeout`/`sleep` (Phase 4); now covered by a test in both modes.
- `project.yaml` flag `healing: {triage, mode}`: set on `bench_buggy_shop` (triage on, propose). Projects WITHOUT the section keep legacy behaviour (no triage, auto-apply) for backward compat; a present section defaults to triage on / propose.
- `workflows/full_workflow.yaml`: healing step documents the triage phase. Deviation: triage is a sub-phase of healing, not a separate step (a new step needs a scaffolded, registered agent) — in backlog.
**Tests** `tests/unit/test_triage_and_safe_healing.py` (9 samples + report read + propose/auto/sleep) plus existing healing unit tests: 80 passed.
**Deferred** see docs/backlog.md "Phase 6". Network-error signal depends on a reporter annotation (`network_error`) not yet emitted; falls back to message text.
