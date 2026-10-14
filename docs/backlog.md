
## Phase 5
All lean-pass items are done (docs/phases/phase-5-report.md). Still open:
- Measure the acceptance numbers on a regenerated suite (median assertion score ≥ 80, zero title-only tests) —
  needs an LLM generation run of buggy_shop with `oracles.enabled`.
- `verifyResponseSchema` schemas from an OpenAPI spec (Phase 8); today only inline `schema` / `schemaRef` files.

## Phase 6
All lean-pass items are done (docs/phases/phase-6-report.md). Still open:
- Fingerprints for elements that only appear after an action (`_dynamic` keys: flash messages, error areas) — not
  captured on page load, so a renamed one cannot be healed and a missing one is judged by the assertion rule only.
- Identity cannot tell two same-verb controls apart in the same slot ("Save product" vs "Save draft"); a `type`
  (submit vs button) signal would help.
- The full LLM-driven loop (ADK) was not part of the benchmark run — the benchmark calls the same deterministic
  tools the loop calls.

## Phase 7
Done in Phase 7 (docs/phases/phase-7-report.md): accessibility (WCAG 2.2 tags, keyboard, form errors, accepted
baseline), visual (baseline on first run + approve command), performance budgets/regression, passive security
additions (stack traces, mixed content, target=_blank), responsive matrix, resilience (offline, slow network,
unusual input), i18n matrix, pipeline wiring + traceability, per-role storage state. Still open:
- **Active security probes** (reflected/stored XSS payloads, SQL/NoSQL injection, open redirect, IDOR, auth bypass,
  CSRF token, login rate limit) — not built in this pass; needs an explicit decision on scope and safeguards
  (non-prod only, `safety.allow_security_probes`). XSS is partly covered by the Phase 5 functional oracles
  (verifyNoDialog / verifyNotInjected on design cases).
- Resilience fault injection per API endpoint (500/503/timeout/malformed JSON) — buggy_shop has no fetch/XHR APIs to
  exercise; the generic offline/slow-network/unusual-input checks run instead.
- i18n: date/number/currency format checks and Unicode-normalization search equivalence (only layout checks today).
- Optional Lighthouse CI / OWASP ZAP integrations.

## Phase 11
All lean-pass items are done (docs/phases/phase-11-report.md). Still open:
- Posting defects to Jira / Azure DevOps through a connector (opt-in, needs credentials) — exports only today.
- Code coverage needs the application under test to be instrumented; reported as "not measured".
- API endpoint and page coverage are read from the spec text (what tests reference), not from executed traffic.

