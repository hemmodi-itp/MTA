
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

## Phase 8
Done in Phase 8 (docs/phases/phase-8-report.md): white-box rule extraction (Python AST; zod / yup / joi /
class-validator patterns), API test generation, frontend/backend contract checks, coverage.py branch coverage with a
gap loop, V8 JS coverage capture, built-in mutation runner. Still open:
- Rules held in local variables inside a handler (buggy_shop BUG_17: the upload allow-list) are not extracted —
  needs intra-function data flow.
- OpenAPI / JSON-schema import as a rule source (only code is read today).
- V8 coverage of bundled frontends needs source maps (v8-to-istanbul); inline scripts are not attributed to files.
- JS/TS backends: route + validator patterns only (no AST); nyc/c8 server coverage not wired into the gap loop.
- Boundary-accepted cases on limits that depend on stored state (cart quantity) are skipped, so mutants there
  survive — needs per-test data reset.

## Phase 10
Done in Phase 10 (docs/phases/phase-10-report.md): burn-in admission, flaky quarantine (`quarantine.yaml`, auto
release / auto add), order-independence check, pre-run health check (`environment_blocked`, exit 3), selective PR
runs from a change fingerprint, one CI entry point (`python -m tools.ci.run`) with GitHub Actions / Azure Pipelines
templates. Still open:
- Sharded CI jobs across machines: one CI job per shard, then merge the Playwright blob reports and MTA results before
  triage and reporting run once (today `execution.shards` shards within one job).
- A flaky-rate trend chart in the report (history keeps the flaky count per run; no chart yet).
- Burn-in (50 specs per night) and the 3-mode order check are untimed on a large suite; the benchmark fixture has 5 UI
  tests.
- Selective execution without white-box `code_rules.json` maps source changes to tests only through spec text and
  git paths.

## Phase 11
All lean-pass items are done (docs/phases/phase-11-report.md). Still open:
- Posting defects to Jira / Azure DevOps through a connector (opt-in, needs credentials) — exports only today.
- Code coverage: shown when a Phase 8 coverage run saved `test_execution/code_coverage.json`; otherwise "not measured".
- API endpoint and page coverage are read from the spec text (what tests reference), not from executed traffic.

