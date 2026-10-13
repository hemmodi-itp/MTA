
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
