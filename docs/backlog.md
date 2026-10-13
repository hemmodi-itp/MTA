
## Phase 5
- verifyApiState (grey-box backend check via `api` fixture)
- verifyAriaSnapshot (toMatchAriaSnapshot)
- verifyCountChangedBy (CRUD / double-submit)
- reloadAndVerify (persistence)
- verifyDownload / verifyNewTab / verifyStorage
- mockRoute / setOffline / setClock (fault injection, P7)
- Expected-value conflict handling (BRD vs observed → potential defect, 5.2)
- verifyResponseSchema, verifyValidationMessage, bodyContains on verifyRequest
- Positive-submit linter rule (UI success signal AND verifyRequest 2xx / reloadAndVerify)
- ActionEngine vitest tests for the new actions (vitest env lacks `yaml` pkg — pre-existing) + buggy_shop false-pass check
- _drop_placeholder_negative_tests: derive from test_cases.json oracles (5.4 second half)

## Phase 6
- Locator identity fingerprint check for healed locators (6.3)
- Blast-radius re-run of every spec using a fixed locator_map key (6.5)
- Burn-in (`--repeat-each=3`) before a healed spec gets `status: healed` (6.7)
- Model fallback via LiteLLM / `healing: skipped (reason)` (6.8)
- Heal audit log `healing_audit.jsonl` (6.9)
- Triage: `known_issue` (known_issues.yaml), `--repeat-each=3` flaky re-run, cross-browser/history signals, LLM for ambiguous (`unknown`)
- Triage: reporter-side `network_error` annotation emission (triage reads it if present; message-text fallback only today)
- Triage as its own registered agent/workflow step (currently runs as first phase of HealingAgent; needs scaffold + registry wiring)
- `environment` verdict: health-check + one re-run; `healing.mode: off`; report-writer section for defects.json / proposals

## Phase 7
- Visual regression (toHaveScreenshot, baseline approval)
- Performance budgets (project.yaml budgets + baseline.json)
- Responsive/compatibility matrix (viewports, browsers, overflow detector)
- Resilience / fault injection (page.route, offline, slow 3G)
- i18n/l10n matrix
- Active security probes (XSS, IDOR, SQLi, open redirect, CSRF)
- A11y keyboard/focus/form-error checks and accepted-issues baseline (7.1); WCAG 2.2 tags
- Passive: mixed content, stack-trace leaks, target=_blank noopener
- Wire generate.py into the pipeline/orchestrator (currently CLI-only) and render nfr specs in traceability
- Per-role storageState instead of replaying login steps in NFR specs
