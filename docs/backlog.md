
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
