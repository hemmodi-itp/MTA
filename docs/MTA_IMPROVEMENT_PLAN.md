# MTA v3 — Phase-wise Improvement Plan

> **Audience:** Claude Opus 5.5 (implementer) + MTA owner, manager and reviewers.
> **Source:** derived from the current `README.md` only. Phase 0.1 makes Opus verify every claim against the code before changing anything.
> **Goal:** turn MTA from "generate some Playwright specs that mostly pass" into a **measurable, professional test engine**: it derives test cases with named test-design techniques, traces every test to a requirement, checks results with strong assertions, covers non-functional and AI-agent quality, and proves how many bugs it actually catches.

---

## Table of Contents

1. [How to use this document with Opus](#1-how-to-use-this-document-with-opus)
2. [Diagnosis — why the current MTA under-tests](#2-diagnosis--why-the-current-mta-under-tests)
3. [Target architecture](#3-target-architecture)
4. [Phases 0 – 12](#4-phases)
5. [Professional Test Case Catalog (what MTA must generate)](#5-professional-test-case-catalog)
6. [Playwright — keep vs change (quick view)](#6-playwright--keep-vs-change)
7. [KPIs to show your manager](#7-kpis-to-show-your-manager)
8. [Copy-paste prompts for Opus](#8-copy-paste-prompts-for-opus)

---

## 1. How to use this document with Opus

1. Put this file in the repo at `docs/MTA_IMPROVEMENT_PLAN.md`.
2. Start every Opus session with the **Master Context Prompt** (§8.1).
3. Give Opus **one phase per session** with the **Phase Prompt** (§8.2). Don't merge phases. Each phase ends with a phase report and passing tests.
4. Follow the phase order: each phase lists what it depends on. If you are short on time, use the **Minimum Viable Track** in §4.
5. After each phase, re-run the benchmark from Phase 0. Before/after numbers are the evidence your manager will want to see.

---

## 2. Diagnosis — why the current MTA under-tests

These gaps come straight from what the README says. Each one is closed in a specific phase.

| # | Gap | Evidence in README | Why it matters | Fixed in |
|---|-----|--------------------|----------------|----------|
| G1 | **Coverage is deliberately capped** | `max_negative_cases: 1`, `max_boundary_cases: 1`, `max_data_iterations: 1`; "Coverage is intentionally minimal by default" | Each scenario gets at most 1 negative and 1 boundary test, so most invalid classes and boundaries are never tested | P3 |
| G2 | **No explicit test-design layer** | Pipeline is scenario → data variants → action plan. No technique (EP, BVA, decision table, state transition, pairwise) is ever applied | You can't show *what* is covered or *why*. Test selection is whatever the LLM produces | P3 |
| G3 | **No requirement traceability in the main pipeline** | Traceability exists only in the Agent-Evaluation DAG, not in `full_workflow.yaml` | You can't answer "which BRD requirements are untested?" | P1 |
| G4 | **Shallow discovery** | Single URL; fixed selector set `input, button, select, textarea, a, [role=combobox]` | Misses custom widgets (`div[role=button]`, tabs, menus, switches, sliders), contenteditable, iframes, modals, content behind hover or tabs, and every other page | P2 |
| G5 | **Field constraints are not captured** | The 12 scanned attributes exclude `required, maxlength, minlength, pattern, min, max, step, accept`; "defaults to 255 if unspecified" | Boundary tests are guesses, not real boundaries | P2 |
| G6 | **Weak checks (test oracles)** | A negative test passes when the "success indicator is absent". The fallback test checks only the page title. XSS/SQLi payloads are typed in, but nothing checks whether they executed | A test can pass while the app is broken (crashed page, slow load, renamed element) | P5 |
| G7 | **UI black-box only** | No API tests, no network assertions, no backend state checks, no code coverage | Server-side validation, authorization and data integrity go untested | P8 |
| G8 | **No non-functional testing** | Chromium only; no accessibility, visual, performance or security-header checks; no mobile | Whole quality dimensions that reviewers expect are missing | P7 |
| G9 | **No resilience testing** | No fault injection, even though Playwright supports `page.route` | How the app behaves when an API fails is never tested | P7 |
| G10 | **Single auth identity** | One `storageState` | No role-based access, unauthorized access, session-expiry or logout tests | P2, P7 |
| G11 | **Flakiness is hidden** | `"flaky"` counts as pass; browser-close errors become "skipped"; `waitForTimeout` is in the action vocabulary; the healer has a "timing fix" | Unstable tests look green, and fixed sleeps hide real performance problems | P4, P6, P10 |
| G12 | **Healing can hide defects** | A shared `locator_map.json` fix "heals every spec"; no check that the healed element is the same element; no approval step; Gemini-only, with no fallback | One wrong heal silently breaks many tests or masks a real bug | P6 |
| G13 | **Static test data** | Fixed datasets; no unique data per run, no setup/teardown, no cleanup | Data collisions, tests that depend on run order, polluted environments | P4 |
| G14 | **Test effectiveness is never measured** | No bug-detection metric, benchmark or mutation testing | You can't prove MTA finds bugs. This is likely the core of the review feedback | P0, P12 |
| G15 | **Thin reporting** | Pass/fail counts, "degraded/healed" marks | No coverage matrix, no "not tested and why", no defect triage, no trends, no quality gates | P11 |
| G16 | **No guard against destructive actions** | Generated tests can click anything | Risk of Delete, Pay or Send actions on a real environment | P0 |
| G17 | **Shallow AI-agent testing** | Agent Evaluation has a quote-grounded judge but no listed injection, consistency, hallucination or tool-use categories | Agent quality and safety are under-tested (verify in P0.1) | P9 |
| G18 | **Two diverging pipelines** | Legacy `main.py` workflow and the `agent_evaluation.yaml` DAG have different capabilities | Improvements land in one pipeline but not the other | P1 (shared core) |
| G19 | **Silent base-URL fallback** | `baseURL` falls back to `http://localhost:3000` | Tests can silently run against the wrong target | P0 |
| G20 | **Hard-coded test-id attribute** | `testIdAttribute: data-test` | Wrong for apps that use `data-testid` or `data-qa` | P4 |

---

## 3. Target architecture

```
 project.yaml (+ environment, roles, test_types, profile, budgets, quality_gates)
        │
 ┌──────▼───────────────────────────────────────────────────────────────┐
 │ P2  Discovery+                                                       │
 │     multi-page crawl → app_map.json (states + transitions)           │
 │     rich elements + constraints → dom_elements.json (v2)             │
 │     form model + observed validation messages → form_model.json      │
 │     network capture → api_inventory.json                             │
 │     per-role scan → permission_matrix.json                           │
 │     console/perf baseline → baseline.json                            │
 └──────┬───────────────────────────────────────────────────────────────┘
 ┌──────▼──────────────────────┐
 │ P1  Requirements + Trace    │ REQ/AC ids, testability, priority, quote-grounding
 └──────┬──────────────────────┘ → requirements.json, traceability.json
 ┌──────▼──────────────────────┐
 │ P3  Test Design Agent (NEW) │ EP · BVA · decision table · state transition ·
 │                             │ pairwise · use-case · CRUD · error-guessing ·
 │                             │ risk-based selection under a budget
 └──────┬──────────────────────┘ → test_cases.json (first-class artifact)
 ┌──────▼──────────────────────┐
 │ TestData (per test case)    │ unique per run, factories, cleanup hints
 │ SemanticMap                 │ (unchanged role)
 │ ScriptGen + Assertion Lint  │ P5: multi-signal checks, strength score
 └──────┬──────────────────────┘
 ┌──────▼──────────────────────┐
 │ Burn-in (repeat-each)       │ P10: new/healed tests must be stable before admission
 └──────┬──────────────────────┘
 ┌──────▼──────────────────────┐
 │ Execution matrix            │ P4/P7: browsers × devices × roles × locales;
 │                             │ evidence = trace, video, HAR, console, axe, perf
 └──────┬──────────────────────┘
 ┌──────▼──────────────────────┐
 │ P6 Failure Triage (determ.) │ product_defect | test_defect | environment | flaky
 │    → Guarded Healing        │ heals test_defect only; identity check; approval
 └──────┬──────────────────────┘
 ┌──────▼──────────────────────┐
 │ P8 Coverage Gap Loop        │ uncovered AC / state / endpoint / branch → back to P3
 └──────┬──────────────────────┘
 ┌──────▼──────────────────────┐
 │ P11 Reporting + Gates       │ traceability matrix, defects, not-tested-why, trend
 └─────────────────────────────┘
```

**Design principles. Apply these in every phase:**

1. **Deterministic first, LLM second.** Use Python code for anything computable: boundary values, decision tables, pairwise sets, state coverage, triage signals. Use the LLM to interpret business language and name things, never to decide coverage.
2. **Every test case is a first-class record** with: `id`, linked `ac_ids`, `technique`, `test_type`, `priority`, `preconditions`, `steps`, `data`, `oracles[]`, `expected_result`, `cleanup`, `source` (`brd` | `observed` | `code` | `llm_inferred`) and `confidence`.
3. **Nothing degrades silently.** Every skipped, capped, deduplicated or degraded item is listed in the report with a reason.
4. **Feature flags in `project.yaml`.** Old projects keep running unchanged. New behaviour is opt-in per project until it has been validated on the benchmark.
5. **One shared core.** New logic lives in importable modules (`tools/test_design/`, `tools/oracles/`, `tools/triage/`) so both the legacy pipeline and the Agent-Evaluation DAG can use it (closes G18).

---

## 4. Phases

**Dependency order:** P0 → P1 → P2 → P3 → P4 → P5 → P6 → (P7, P8, P9 in any order) → P10 → P11 → P12

**Minimum Viable Track** (to show visible improvement to your manager fastest): **P0 → P1 → P2 (2.1–2.3 only) → P3 → P5 → P6 → P11 (summary + traceability only)**

Each phase uses the same template: **Objective · Gaps closed · Tasks · Likely files · New artifacts · Acceptance criteria · Required tests**.

---

### Phase 0 — Baseline, Benchmark and Safety Rails

**Objective:** Know where MTA stands today in numbers, and make it safe to run more aggressive tests.
**Gaps closed:** G14, G16, G19 (and the factual base for everything else)

**Tasks**

- **0.1 README-vs-code audit.** Read the code and write `docs/audit/current_state.md`: confirm or correct every README claim that later phases rely on (scanner selector set, captured attributes, caps, flaky handling, healing tools, ActionEngine actions, Agent-Eval capabilities). List the discrepancies. **Later phases must follow the audit wherever it disagrees with this plan.**
- **0.2 Benchmark apps with seeded bugs.** Create `benchmarks/`:
  - `benchmarks/apps/buggy_shop/`: a small local web app (login, list with search/filter/sort/pagination, CRUD form with validation, cart/checkout total, file upload, admin page). Each seeded bug sits behind its own env flag (`BUG_07=1`). Include at least 20 seeded bugs, spread across categories: off-by-one length validation, server accepts what the client rejects, wrong total rounding, missing role check (IDOR), unescaped output (stored XSS), broken link, 500 on an edge input, missing form label (a11y), slow endpoint (> 3 s), state-machine bug (checkout reachable without a cart), session not invalidated on logout, double-submit creating duplicates, wrong error message, sort not stable, pagination losing the filter.
  - `benchmarks/apps/buggy_shop/bugs.yaml`: ground truth (`id`, `category`, `severity`, `affected_ac`, `how_detectable`).
  - `benchmarks/agents/buggy_bot/`: a small chatbot with seeded weaknesses (system-prompt leak, follows injected instructions, hallucinates on unknown questions, forgets turn-1 context) for P9.
  - Optional: public practice sites that explicitly allow automated testing. Local apps are preferred, because destructive and security tests are only allowed against local targets.
- **0.3 Scoring tool** `tools/benchmark/score.py` → `benchmarks/results/<date>.json` + a Markdown summary:
  - Requirement (AC) coverage %
  - **Seeded-bug detection rate** (bugs caught ÷ bugs enabled)
  - **False-failure rate** (failures when every bug flag is off)
  - Flaky rate, heal precision, runtime, LLM tokens and cost per run
- **0.4 Record the baseline** by running current MTA on the benchmark. Commit the numbers. This is the "before" column for your manager.
- **0.5 Safety rails** (`project.yaml`):
  ```yaml
  environment: local | dev | staging | prod      # required
  safety:
    allow_destructive: false        # delete/pay/send/deactivate/transfer actions
    allow_security_probes: false    # active XSS/SQLi/IDOR probes
    allowed_hosts: [myapp.example.com, api.myapp.example.com]
  ```
  - Add an action-safety classifier (deterministic keyword + role heuristics on the accessible name and URL: delete, remove, pay, purchase, place order, send, transfer, deactivate, unsubscribe, reset). Destructive steps are dropped and reported unless `allow_destructive: true` **and** `environment != prod`.
  - Active security probes are refused on `prod`, whatever the flags say.
  - Navigation outside `allowed_hosts` makes the step fail.
- **0.6 Remove the silent `localhost:3000` fallback.** An unresolved base URL is a fail-fast error.
- **0.7 Artifact contracts.** Add Pydantic models and exported JSON Schemas (`schemas/`) for every artifact (`dom_elements`, `business_scenarios`, `test_data`, `scenario_element_map`, `test_plans`, `test_suite`, results). Validate at every step boundary in the orchestrator. Version every artifact (`"schema_version": 2`) and add loaders that migrate v1 artifacts forward.

**Acceptance criteria**
- `python -m tools.benchmark.run --app buggy_shop` runs end to end and prints the metrics.
- Baseline results are committed.
- All existing project artifacts validate (or migrate) against the schemas.
- A generated step that clicks "Delete account" is dropped when `allow_destructive: false`.

**Required tests:** unit tests for the safety classifier (≥ 30 labelled names), schema round-trip tests, scorer tests with synthetic results.

---

### Phase 1 — Requirements and Traceability Backbone

**Objective:** Every requirement has an ID, and every test points to one. "What is untested?" gets an exact answer.
**Gaps closed:** G3, G18 (starts the shared core)

**Tasks**
- **1.1** Extend comprehension output into `comprehension/requirements.json`:
  - `REQ-###` → atomic acceptance criteria `AC-###.#` (one checkable behaviour each; reuse Agent-Eval's atomic-criteria logic)
  - Per AC: `testability` (`ui` | `api` | `non_functional` | `manual_only` | `not_testable`, with a reason), `priority` (P0–P3), `risk_tags` (auth, payment, data-loss, PII, compliance), `source_quote` (exact BRD text; **quote-verified** with Agent-Eval's verifier) or `source: dom_inferred`
  - Keep `business_scenarios.json`, and link each scenario to its `ac_ids`.
- **1.2** `test_creation/traceability.json`: AC → test_case_ids → spec file + test title → latest result → defect ids. Update it after generation and after every execution.
- **1.3** Tag every generated test with Playwright tags and annotations:
  ```ts
  test('AC-012.2 rejects password shorter than 8', {
    tag: ['@P1', '@negative', '@bva', '@REQ-012'],
    annotation: [{ type: 'ac', description: 'AC-012.2' }, { type: 'tc', description: 'TC-0457' }],
  }, async ({ page }) => { ... });
  ```
- **1.4** Move the requirement and trace logic into a shared module (`tools/requirements/`) that both pipelines import.

**Acceptance criteria**
- Every generated test maps to at least one AC.
- The report lists every AC with zero tests, with a reason (`not_testable`, `budget`, `missing_locator`, etc.).
- On buggy_shop, at least 90% of hand-labelled ACs are extracted. Opus writes the ground-truth list in `benchmarks/apps/buggy_shop/acs.yaml`.

**Required tests:** AC extraction schema tests, quote-verifier tests (exact, paraphrased and fabricated quotes), traceability update tests.

---

### Phase 2 — Deep Discovery

**Objective:** Find every element, constraint, page, state, API call and role difference, because test design can only be as good as discovery.
**Gaps closed:** G4, G5, G10 (partly)

**Tasks**
- **2.1 Wider element capture** (`tools/playwright_scanner.py`):
  - Add to the selector set: `[role=button|link|tab|menuitem|menuitemcheckbox|checkbox|radio|switch|slider|spinbutton|option|treeitem|searchbox|textbox]`, `[contenteditable=true]`, `[onclick]`, `[tabindex]:not([tabindex="-1"])`, `summary`, `details`, `input[type=file|date|datetime-local|time|range|color]`, and elements whose computed `cursor: pointer` has no interactive ancestor.
  - Go through **all frames** (`page.frames`), not just the main frame. Confirm open shadow roots are pierced (Playwright CSS does this by default; check in the audit).
  - **Performance:** replace the per-element round trips (`inner_text()`, `is_visible()`, …) with one `page.evaluate()` that extracts every element's data in a single call. This should cut scan time sharply and remove the reason for the 600 s cap.
  - **Better locators than demotion:** when a role locator matches 2 or more elements, first try **scoping by container** (nearest landmark, form, dialog or section with an accessible name, e.g. `page.getByRole('dialog', {name:'Edit user'}).getByRole('button', {name:'Save'})`) before falling back to CSS.
- **2.2 Constraint capture:** `required`, `aria-required`, `maxlength`, `minlength`, `pattern`, `min`, `max`, `step`, `type`, `inputmode`, `accept`, `multiple`, `autocomplete`, `readonly`, `disabled`, default value, `<select>` options (value + text), radio group membership, and the associated error container (`aria-describedby`, `aria-errormessage`).
- **2.3 Observed validation oracle** (only when `environment != prod`, or for forms with no destructive submit): for each form, submit it empty, then with each field invalid in turn (wrong type, too long). Record the native `validationMessage`, the visible error text, `aria-invalid`, focus position and the network calls made. Store the results in `comprehension/form_model.json`. **This gives real expected error messages instead of LLM guesses.**
- **2.4 Multi-page crawl and state model:** breadth-first crawl within `allowed_hosts`, bounded by `discovery.max_pages`, `max_depth` and `max_minutes`. Deduplicate states by URL template + DOM structural hash. Open non-destructive expanders (tabs, accordions, menus, modals) to reveal hidden states. Record transitions (`from_state`, `action`, `element`, `to_state`). Output `comprehension/app_map.json`. Reuse Agent-Eval's `runtime_discovery` logic, don't duplicate it.
- **2.5 Network inventory:** record requests during the crawl (`page.on('request'/'response')`) into `comprehension/api_inventory.json`: method, path template (`/users/{id}`), status codes seen, inferred request/response JSON schemas, whether an auth header was present, and the triggering UI action.
- **2.6 Role-aware discovery:**
  ```yaml
  auth:
    roles:
      admin: { strategy: credentials, username_env: ADMIN_USER, password_env: ADMIN_PASS, ... }
      user:  { strategy: storageState, storage_state_path: .auth/user.json }
      guest: { anonymous: true }
  ```
  Scan per role, then diff the results into `permission_matrix.json` (state/action × role → visible / hidden / blocked).
- **2.7 Baseline capture:** console errors and page errors already present at discovery time, plus navigation timing per state, saved to `baseline.json`. Later tests can then tell new errors apart from existing noise.

**Acceptance criteria**
- buggy_shop element recall ≥ 95% against a hand-labelled list.
- Every constrained field has its constraints captured.
- `app_map` contains every page.
- The observed validation messages match the app's real messages.
- Scan time is the same or better than baseline.

**Required tests:** fixture HTML pages (shadow DOM, iframe, custom widgets, duplicate buttons inside different dialogs), constraint-extraction tests, state-hash dedup tests, URL-templating tests.

---

### Phase 3 — Test Design Agent (the core upgrade)

**Objective:** Generate test cases **systematically with named techniques**, prioritized by risk, within an explicit budget, instead of 1 positive + 1 negative + 1 boundary per scenario.
**Gaps closed:** G1, G2

**Tasks**
- **3.1** Create `agents/test_creation/test_design/` **with `tools/scaffold_agent.py`** (`--has-llm --has-tools`). Wire it between `testdata` and `semantic_map` (or before `testdata`, so data is generated per test case; Opus decides based on the audit and explains the choice).
- **3.2 Deterministic generators** in `tools/test_design/` (pure Python, no LLM):

  | Module | Technique | Rule |
  |---|---|---|
  | `ep.py` | Equivalence partitioning | Valid and invalid classes per field type (see §5.D). One test per invalid class, valid classes combined |
  | `bva.py` | Boundary value analysis (3-value) | For every length, numeric, date, count and file-size constraint: `min-1, min, min+1, nominal, max-1, max, max+1`. Constraint sources in priority order: DOM constraint > BRD AC > observed validation > default (flagged) |
  | `decision_table.py` | Decision tables | The LLM extracts conditions and actions from AC text ("if/when/unless/only if"). The table is built and collapsed **deterministically** |
  | `state_transition.py` | State transition | From `app_map`: every valid transition (0-switch), pairs of transitions for P0/P1 flows (1-switch), and **invalid transitions** (deep link to step 3 without step 2, back button after submit, refresh mid-flow) |
  | `pairwise.py` | Combinatorial (all-pairs) | For filter, sort and option combinations with ≥ 3 parameters |
  | `use_case.py` | Use case / journey | Main + alternate + exception flows across pages (E2E journeys, not just single-page scenarios) |
  | `crud.py` | CRUD lifecycle | create → list → detail → reload persists → update → delete → gone, including direct-URL access to the deleted item |
  | `error_guessing.yaml` | Error guessing catalog | The catalog in §5 encoded as data, applied per field or widget type |
  | `role_matrix.py` | Authorization | Every `permission_matrix` cell becomes a test (allowed → works; denied → blocked in the UI **and** by direct URL/API) |

- **3.3 LLM's role (limited):** map generated cases to ACs, add domain-specific cases the catalog can't know (business rules), and write human-readable titles. **The LLM may add cases, never drop deterministic ones.** Its output is schema-validated.
- **3.4 Risk-based prioritization:** `risk = impact × likelihood`.
  - Impact comes from AC priority and risk tags (auth, payment, data loss, PII).
  - Likelihood comes from input count, branching (decision-table size), number of transitions, and the change fingerprint (recently changed pages are riskier).
  - The result maps to P0–P3.
- **3.5 Coverage profiles replace the 1/1/1 caps:**
  ```yaml
  test_generation:
    profile: standard            # smoke | standard | thorough | exhaustive
    budget: { max_tests: 400, max_runtime_minutes: 45 }
    # legacy caps still honoured if present, but logged as deprecated
  ```

  | Profile | Contents |
  |---|---|
  | smoke | P0 positive journeys only |
  | standard | Every AC: ≥ 1 positive + ≥ 1 negative (when a negative path exists); full BVA on P0/P1 fields; all valid transitions; role matrix for P0 actions |
  | thorough | standard + full EP/BVA on all fields, pairwise, invalid transitions, error-guessing catalog, CRUD lifecycle |
  | exhaustive | thorough + 1-switch transitions and every catalog entry on every field |

  **Selection algorithm:** keep every P0, then add by descending risk until the budget runs out, while guaranteeing the coverage floor for the profile. Everything that gets cut is listed in the report with the reason "budget".
- **3.6** Run `SemanticDedupAgent` on `test_cases.json` (it currently runs only in the older pipeline).
- **3.7 `test_cases.json` schema (example):**
  ```json
  {
    "id": "TC-0457", "ac_ids": ["AC-012.2"], "scenario_id": "BS-004",
    "title": "Password shorter than minimum is rejected",
    "technique": "bva", "test_type": "negative", "priority": "P1",
    "risk_score": 0.72, "roles": ["guest"],
    "preconditions": ["on /register", "no existing user with generated email"],
    "inputs": { "password": { "value_rule": "len=min-1", "min": 8, "constraint_source": "dom:minlength" } },
    "steps_outline": ["fill all valid", "set password to 7 chars", "submit"],
    "oracles": [
      { "type": "field_invalid", "field": "password" },
      { "type": "error_text", "contains": "at least 8 characters", "source": "observed" },
      { "type": "no_request", "method": "POST", "url": "/api/users" },
      { "type": "url_unchanged" }
    ],
    "cleanup": [], "source": "dom+observed", "confidence": 0.95
  }
  ```

**Acceptance criteria**
- On buggy_shop with the `standard` profile: requirement coverage ≥ 90% of testable ACs, and every seeded *validation* and *state-machine* bug has at least one test targeting it.
- The budget is respected.
- Generators are deterministic (same input → byte-identical output).

**Required tests:** exact expected values for BVA (including dates: leap years, month ends), decision-table collapse tests, pairwise coverage proof (every pair present), and property-based tests (`hypothesis`) for the generators.

---

### Phase 4 — Playwright Runtime Modernization

**Objective:** Upgrade the runner and the shared runtime (fixtures, config) so the stronger checks, test types and data handling in later phases are possible.
**Gaps closed:** G11 (partly), G13, G20

**Tasks**
- **4.1 Upgrade and pin** `@playwright/test` to the latest stable version. Record it in `package.json` and the audit.
- **4.2 `playwright.config.ts`:**
  - `projects`: `chromium` always. `firefox`, `webkit`, `Pixel 7` and `iPhone 14` are enabled by the profile or `project.yaml` `execution.matrix`.
  - `fullyParallel: true` (only after 4.4 isolation is in place)
  - `trace: 'retain-on-failure'`, `video: 'retain-on-failure'`, `screenshot: 'only-on-failure'`
  - `forbidOnly: !!process.env.CI`
  - Reporters: `list`, `json`, `html`, **`junit`**, **`blob`** (for shards + `merge-reports`) and a **custom MTA reporter** (`runtime/reporters/mta-reporter.ts`) that writes results straight into `traceability.json` fields (test id ↔ AC ↔ status ↔ attachments).
  - `testIdAttribute` read from `project.yaml` (`execution.test_id_attribute`, default `data-testid`).
  - `use.locale` and `use.timezoneId` from the project's matrix.
  - No base-URL fallback (enforced in P0).
- **4.3 Auth per role:** a setup project or `globalSetup` writes `.auth/<role>.json` for each role. Tests pick a role with a fixture: `test.use({ role: 'admin' })`.
- **4.4 Fixtures** (`runtime/fixtures.ts`):

  | Fixture | Purpose |
  |---|---|
  | `testData` | Unique data per test: deterministic faker seeded with `runId + testId`, plus a `runId` prefix on created entities |
  | `cleanup` | A registry. Tests register created entities, teardown deletes them (API preferred, UI fallback) |
  | `api` | Playwright `request` context with the role's auth, for setup, verification and API tests |
  | `consoleGuard` | Collects `console.error` + `pageerror` and fails the test on **new** errors compared with `baseline.json` |
  | `network` | Records requests and responses for network checks (P5) and HAR evidence |
  | `a11y` | `@axe-core/playwright` AxeBuilder helper (P7) |
  | `perf` | Navigation timing + Web Vitals collector (P7) |
  | `safety` | Runtime check of the P0 safety rules (host allow-list, destructive guard) |

- **4.5 Structure:** render each plan step as a `test.step('<plan step text>', …)` so reports and healing map failures to plan steps.
- **4.6 Waiting:** remove `waitForTimeout` from the LLM action vocabulary (keep it only for human-authored flows, and have the linter flag it). Use web-first assertions, `expect.poll` and `expect(...).toPass()` for eventual consistency.
- **4.7 Flakiness:** a test that fails and then passes on retry is recorded as **`flaky`**, never as `passed`. Enable `failOnFlakyTests` in CI if the installed version supports it. In headless/CI runs, browser-close errors are treated as **errors**. The "reclassify as skipped" behaviour applies only in headed mode, when a human closes the window.
- **4.8 Scale:** support `--shard=i/n` and `merge-reports` in `UIExecutionAgent`.
- **4.9 Suites by tag:** `--grep @smoke` / `@P0` replaces hand-maintained scenario lists. `test_suites/*.json` stays as a compatibility layer that is translated into grep expressions.

**Acceptance criteria**
- Existing generated specs still pass on the benchmark (no regression).
- Two parallel workers create no data collisions.
- A deliberately flaky test shows up as `flaky`.
- JUnit XML and the MTA reporter output are produced.

**Required tests:** vitest unit tests for the fixtures and reporter, a config snapshot test, and a pytest test for the shard/merge path in `UIExecutionAgent`.

---

### Phase 5 — Test Oracles and Assertion Strength

**Objective:** A passing test must actually prove the behaviour. Today's biggest quality issue is weak checks (oracles).
**Gaps closed:** G6, G11 (`waitForTimeout`)

**Tasks**
- **5.1 New ActionEngine actions** (mirror them in `ALLOWED_ACTIONS` and the renderer):

  | Action | Purpose |
  |---|---|
  | `verifyRequest {method, urlPattern, status?, bodyContains?}` | The expected API call happened with the expected status |
  | `verifyNoRequest {method, urlPattern}` | Negative tests: nothing was submitted |
  | `verifyResponseSchema {urlPattern, schemaRef}` | Response shape matches the schema |
  | `verifyApiState {request, expect}` | Check backend state through the `api` fixture (grey-box) |
  | `verifyFieldInvalid {locator}` | `aria-invalid=true` or native `:invalid` |
  | `verifyValidationMessage {locator, contains}` | Native or custom validation text |
  | `verifyAriaSnapshot {locator, snapshot}` | Structural assertion with `toMatchAriaSnapshot` |
  | `verifyNoNewConsoleErrors` | Uses `consoleGuard` |
  | `verifyNoDialog` | XSS: no `alert/confirm/prompt` fired |
  | `verifyNotInjected {payloadMarker}` | XSS: the payload is rendered as text, and no new `<script>` or event-handler attribute appears |
  | `verifyCountChangedBy {locator, delta}` | CRUD and double-submit checks |
  | `reloadAndVerify {steps}` | Persistence |
  | `verifyDownload {nameRegex, minBytes}` / `verifyNewTab {urlContains}` | Downloads and popups |
  | `verifyStorage {cookie/localStorage, rule}` | Session and security checks |
  | `mockRoute {urlPattern, status, body, delayMs}` / `setOffline` / `setClock` | Fault injection and time control (P7) |

- **5.2 Expected-value precedence:** BRD AC (quoted) > observed behaviour (P2.3) > code-derived (P8) > LLM-inferred (`low_confidence`, reported). **When the BRD and observed behaviour disagree, record it as a *potential defect* for human review. Never pick one silently.**
- **5.3 Assertion linter** (`tools/test_creation/assertion_linter.py`). It runs after plan validation and scores each test from 0 to 100. Rules:
  - At least one check must be about the **outcome**, not about the element just acted on (`click X` then `verifyVisible X` is rejected).
  - A title-only check is rejected (except for an explicit `@smoke-reachability` test).
  - **Negative tests** need (specific error text **or** `verifyFieldInvalid`) **and** (`verifyNoRequest` **or** `url_unchanged` **or** `verifyCountChangedBy 0`).
  - **Positive submit tests** need a UI success signal **and** (`verifyRequest` 2xx **or** `reloadAndVerify`).
  - **Security payload tests** need `verifyNoDialog` + `verifyNotInjected`.
  - Every test gets `verifyNoNewConsoleErrors` (added automatically by the renderer).
  - `waitForTimeout` in a generated plan → rejected.
  - Tests that score below the threshold are regenerated once with the linter feedback, then flagged as `weak_oracle` in the report.
- **5.4** Update the ScriptGeneration prompt and the `_drop_placeholder_negative_tests` logic to use oracles from `test_cases.json` (P3) instead of inventing them.

**Acceptance criteria**
- Median assertion score ≥ 80.
- Zero generated tests whose only check is the title.
- On buggy_shop, the false-pass check passes: with a seeded bug that turns validation into a silent no-op, the negative test **fails**.

**Required tests:** at least 25 linter rule tests (good and bad plans), renderer golden tests for each new action, ActionEngine vitest tests against local fixture pages.

---

### Phase 6 — Failure Triage and Safe Healing

**Objective:** Healing fixes **tests**, never hides **bugs**.
**Gaps closed:** G12, G11 (timing fixes)

**Tasks**
- **6.1 New deterministic `FailureTriage` step** (`tools/triage/`, called before HealingAgent). It classifies each failure as:
  - `product_defect`: the assertion on an expected value failed while the locators resolved; an API returned 4xx/5xx unexpectedly; new console errors appeared; the BRD vs observed conflict reproduces
  - `test_defect.locator`: element not found or strict-mode violation, while the page state is otherwise as expected
  - `test_defect.data`: collision or duplicate, or a missing precondition
  - `environment`: base URL unreachable, 502/503/504 from infrastructure, auth state expired, DNS or TLS problems
  - `flaky`: passes on `--repeat-each=3` re-run
  - `known_issue`: matches an entry in `known_issues.yaml`

  Signals: error type, trace, network log, console log, previous-run history, and whether the same step fails across browsers. **The LLM is consulted only when the deterministic signals are ambiguous**, and it must cite the evidence.
- **6.2 Heal only `test_defect.*`.** `product_defect` → defect report (P11), never patched. `environment` → re-run once after a health check, then report.
- **6.3 Locator identity check:** a healed locator must match the original element's fingerprint (role, accessible-name similarity, tag, associated label, form/container, relative position) above a threshold. Below the threshold → human review.
- **6.4 Healing modes:** `healing.mode: auto | propose | off`. In `propose` mode, patches go to `test_creation/healing_proposals/<run>/` as diffs with the evidence. CI defaults to `propose`. `auto` applies only above the confidence threshold.
- **6.5 Blast radius:** a `locator_map.json` fix lists every spec that uses the key. **All** of them are re-run, not only the failing one.
- **6.6 Timing fixes may not add fixed sleeps.** Allowed fixes: replace with a web-first assertion, `waitForResponse`, or `expect.poll`.
- **6.7** A healed spec must pass burn-in (`--repeat-each=3`) before it gets `status: healed`.
- **6.8 Model fallback:** if Gemini/ADK is unavailable, use another model configured in `adk.models` through LiteLLM. If that also fails → `healing: skipped (reason)`, not a pipeline failure.
- **6.9 Heal audit log** in `healing_audit.jsonl`: before/after, evidence, confidence, approver.

**Acceptance criteria (on the benchmark)**
- Inject 10 locator changes (renamed id/class, moved DOM): heal success ≥ 80%, and **0 wrong-element heals**.
- Enable 10 seeded product bugs: **0 healed**; all 10 classified as `product_defect`.

**Required tests:** triage classifier tests with recorded failure fixtures, identity-score tests, a test that `apply_patch` rejects `waitForTimeout`.

---

### Phase 7 — Non-Functional Test Types

**Objective:** Cover the quality dimensions reviewers expect from a professional test suite.
**Gaps closed:** G8, G9, G10 (remaining)

All of these are controlled per project:
```yaml
test_types: { functional: true, accessibility: true, visual: false, performance: true,
              security_passive: true, security_active: false, compatibility: true,
              resilience: true, i18n: false }
```

- **7.1 Accessibility (WCAG 2.2 AA)**
  - Run axe on every discovered state (tags `wcag2a, wcag2aa, wcag21aa, wcag22aa`).
  - Keyboard: Tab order reaches every interactive element; focus is visible; no keyboard trap; Esc closes modals; focus returns to the trigger.
  - Forms: every field has an accessible name; errors are announced (`role=alert` / `aria-live`); focus moves to the first error.
  - Map severity (critical/serious → fail; moderate/minor → warn) and keep a baseline file for accepted known issues.
- **7.2 Visual regression:** `toHaveScreenshot` per key state × viewport. Mask dynamic regions (dates, avatars, counters). There's an explicit baseline approval command, and visual tests never fail on the first run.
- **7.3 Performance (functional-level, not a load test)**
  - Per state: TTFB, FCP, LCP, CLS, INP-proxy, total transfer bytes, request count, slowest API calls.
  - Budgets in `project.yaml`, compared with `baseline.json`. A regression of more than X% → warn or fail.
  - Optional Lighthouse CI. Recommend k6 for real load testing (out of MTA scope).
- **7.4 Security**
  - *Passive (safe everywhere):* CSP, HSTS, X-Content-Type-Options, frame-ancestors/X-Frame-Options, Referrer-Policy; cookie flags (`HttpOnly`, `Secure`, `SameSite`) on session cookies; mixed content; tokens or PII in URLs or `localStorage`; stack traces or framework errors in responses; `target=_blank` without `noopener`.
  - *Active (non-prod + `allow_security_probes` only):* reflected and stored XSS with execution checks (P5), SQL/NoSQL injection error-leak checks, open redirect on `redirect/next/url` params, **IDOR** (user A requests user B's resource ID through the URL and the API), auth bypass (deep link and API without a token → 401/403), CSRF token presence on state-changing forms, login rate limiting.
  - Optional: OWASP ZAP baseline scan integration.
- **7.5 Compatibility and responsive:** browser matrix; viewports 320/375/768/1024/1440; no horizontal overflow (`scrollWidth > clientWidth`); touch targets ≥ 24 px; orientation change.
- **7.6 Resilience (fault injection with `page.route`)**
  - For each API in `api_inventory`: 500, 503, timeout (delay > threshold), empty list, malformed JSON, 401 mid-session.
  - Plus `context.setOffline(true)` and slow 3G (Chromium CDP throttling).
  - Checks: an error message the user can understand, a retry option where specified, no blank page, no unhandled `pageerror`, no infinite spinner, and the form data is kept.
- **7.7 i18n/l10n:** locale × timezone matrix; RTL input; date, number and currency formats; text expansion (+40%) without clipping; Unicode normalization (é as one code point vs combining characters).

**Acceptance criteria**
- Each type can be toggled on its own.
- The seeded a11y, security (XSS, IDOR), performance and resilience bugs in buggy_shop are detected.
- Passive security checks never send attack payloads.

**Required tests:** unit tests for each analyzer (header rules, cookie rules, overflow detector) and fixture pages with known violations.

---

### Phase 8 — API Testing and White-Box Testing

**Objective:** Test below the UI, and use the source code (when it is available) to find what black-box testing misses.
**Gaps closed:** G7

- **8.1 API tests** (same Playwright runner, using the `request` fixture), generated from `api_inventory.json` + OpenAPI or route extraction from the repo:
  - Status codes for valid and invalid requests; response schema; auth required (no token → 401, wrong role → 403); wrong method → 405; BVA/EP on parameters (P3 generators reused); pagination (first, last, beyond the last page); idempotency of PUT/DELETE; consistent error format; **server-side validation matches client-side validation** (send what the UI would block directly to the API).
- **8.2 White-box rule extraction** (extends `repo_intelligence`):
  - Parse validation schemas (zod, yup, joi, pydantic, class-validator, marshmallow), regexes, `if` guards on inputs, role and permission checks, feature flags, and enum values.
  - Turn them into P3 constraints with `source: code` and a citation (`file:line`).
  - Every white-box-derived case cites its code.
- **8.3 Coverage feedback loop:**
  - *Frontend:* Chromium `page.coverage.startJSCoverage()` → `v8-to-istanbul` (requires source maps) → statement/branch coverage per file.
  - *Backend (only when the team runs the target):* start it under coverage.py / nyc / c8 / JaCoCo in the test environment and collect after the run.
  - Map uncovered branches → functions → routes/UI states → ask P3 for targeted cases. Repeat up to `coverage.max_gap_rounds`.
  - Report: statement %, branch %, and uncovered critical functions.
- **8.4 Contract checks:** what the frontend sends must match the backend schema (catches drift).
- **8.5 Mutation testing to measure suite effectiveness** (scheduled, not per run; only for repos the team owns): run Stryker (JS/TS) or mutmut (Python) on selected critical modules, with the MTA suite as the test command. **The mutation score is the strongest proof of how many faults the tests catch.**

**Acceptance criteria**
- API endpoint coverage ≥ 90% of the inventory.
- Code coverage is collected on buggy_shop.
- One gap round measurably raises branch coverage.
- Every seeded "server accepts what the client rejects" bug is caught by an API test.

**Required tests:** rule-extractor tests for each schema library, path-templating tests, coverage-mapping tests.

---

### Phase 9 — AI Agent / LLM Application Testing

**Objective:** Test the company's AI agents and chatbots properly. Their output is non-deterministic, so they need statistical verdicts and safety tests.
**Gaps closed:** G17
**Applies to:** the Agent-Evaluation DAG (chatbot, agent and API app types) and any `type: ai_agent` project.

- **9.1 Test dimensions** (each one is a generator in `tools/agent_tests/`):

  | Dimension | Example cases | How it's judged |
  |---|---|---|
  | Task success | Per AC: the user goal is achieved | Rubric + deterministic checks |
  | Groundedness / faithfulness | Answer only from the provided knowledge, cites correctly | Quote-grounded judge |
  | Hallucination | Questions with **no** answer in the knowledge base → must say "I don't know" | Refusal detector + judge |
  | Consistency | Same input N=5 times → semantically equivalent answers | Pairwise similarity ≥ threshold |
  | Robustness | Paraphrases, typos, casing, slang, other languages, very long input, empty input, emoji-only | Same verdict as the original case |
  | Multi-turn | Context kept across turns, user corrections applied, topic switch, reference to turn 1 at turn 10 | Rubric |
  | Instruction / format | JSON schema output, length limits, tone | Schema validation (deterministic) |
  | Scope | Out-of-domain request → polite redirect | Classifier + judge |
  | Prompt injection (direct) | "Ignore previous instructions…", role-play jailbreaks, encoded instructions | Must not comply; canary-token checks |
  | Prompt injection (indirect) | Malicious instructions planted inside documents, web pages or tool outputs the agent reads | Must not act on them |
  | Data leakage | System-prompt extraction, other users' data, secrets, PII echo | Canary strings in the system prompt and seed data must never appear |
  | Harmful content | Requests the agent must refuse according to its policy | Refusal + judge |
  | Tool use (if traces are exposed) | Right tool, right arguments, no unauthorized tool, recovers from tool errors | Trace assertions (deterministic) |
  | Session isolation | User A's conversation never appears for user B (parallel contexts) | Deterministic canary check |
  | Latency / cost | p50/p95 time-to-first-token, total time, tokens per turn | Budgets |

- **9.2 Golden datasets:** `eval_sets/<agent>/*.jsonl` (`input`, `context`, `expected`, `rubric`, `tags`, `ac_ids`). Generated from the BRD and **human-reviewed once**, then versioned.
- **9.3 Judging pipeline:** deterministic checks first (regex, schema, contains, canary). Then an LLM-as-judge with an explicit rubric, using a **judge model different from the agent's model**. Calibrate the judge against at least 50 human labels and report agreement (Cohen's κ). Below 0.6 → the judge is not trusted for that dimension.
- **9.4 Statistical verdicts:** run each case k times (default 3, safety cases 5). The verdict is a pass rate with a confidence interval. Gate on the lower bound. Mark non-deterministic cases.
- **9.5 Regression comparison:** compare against the previous agent version per dimension. A score drop greater than X% → gate failure.
- **9.6 Ethics and safety:** red-team payloads come from a curated catalog. Run them only against company-owned or authorized agents, and never generate genuinely harmful content in prompts beyond what is needed to test refusal.

**Acceptance criteria**
- Every seeded weakness in `buggy_bot` is detected.
- A judge calibration report exists.
- Repeated runs give stable verdicts (pass-rate variance below the threshold).

**Required tests:** unit tests for the canary detector, schema checker, consistency scorer and statistics helpers.

---

### Phase 10 — Execution at Scale: Flakiness, CI, Selective Runs

**Objective:** Reliable, fast and repeatable runs in CI.
**Gaps closed:** G11 (remaining)

- **10.1 Burn-in admission:** new and healed tests run `--repeat-each=5` before joining the regression suite. Tests that fail burn-in go to `quarantine`.
- **10.2 Flaky management:** `quarantine.yaml` (test id, first seen, failure signature, owner). Quarantined tests still run but don't gate. There's a flaky-rate trend, and a test is auto-released after N stable runs.
- **10.3 Order independence:** run the suite with different worker counts and in reverse file order every night. A test that only fails in one order is marked `order_dependent`.
- **10.4 Pre-run environment health check:** base URL reachable, auth state valid (refresh it if expired), required seed data present. A failing health check → the run is `environment_blocked`, not 300 failed tests.
- **10.5 Selective execution:** use the change fingerprint (changed pages, ACs or API endpoints) to run only the impacted tests plus all P0 tests on pull requests. Run everything nightly.
- **10.6 CI templates** (`ci/github-actions.yml`, `ci/azure-pipelines.yml`):

  | Trigger | What runs |
  |---|---|
  | Pull request | smoke + impacted tests, chromium |
  | Nightly | `thorough` profile + matrix + non-functional, sharded |
  | Release | everything + quality gates |

  Artifacts are uploaded (HTML report, traces, JUnit), and the run exits non-zero when a gate fails.

**Acceptance criteria:** a CI run works end to end on buggy_shop; a quarantine round trip works; the health-check failure path is tested.

---

### Phase 11 — Reporting and Quality Gates

**Objective:** A report a manager can read in 2 minutes, with the detail a tester needs for a whole day.
**Gaps closed:** G15

- **11.1 Executive summary** (top of the HTML report):
  - Overall verdict against the gates
  - Requirement coverage %
  - Pass rate by priority
  - Defects by severity
  - Top 5 risk areas
  - Trend versus the last 5 runs
  - "Not tested, and why" (count + link)
- **11.2 Traceability matrix:** REQ/AC × tests × latest result × defects. Interactive HTML with CSV/XLSX export.
- **11.3 Coverage dashboard:** requirement, technique (EP/BVA/…), element, page/state, transition, API endpoint, role-matrix, browser/device, test-type and code coverage.
- **11.4 Defect reports** (one per `product_defect`):
  - Title, severity, priority, linked AC
  - **Human-readable steps to reproduce** (from the plan), expected vs actual (with the expected-value source)
  - Evidence: screenshot, trace link, video, HAR excerpt, console log; environment, browser, role, run id
  - Export in Jira/Azure DevOps-compatible JSON (posting through a connector is optional and needs explicit opt-in)
- **11.5 Quality gates** (`project.yaml`):
  ```yaml
  quality_gates:
    p0_pass_rate: 100
    p1_pass_rate: 95
    requirement_coverage: 90
    max_critical_a11y: 0
    max_security_high: 0
    max_flaky_rate: 2
    perf_budget_regression_pct: 20
  ```
  When a gate fails, MTA exits with a non-zero code and the summary names the gate.
- **11.6 Test Summary Report** structured like ISO/IEC/IEEE 29119-3: scope, approach, deviations, coverage, results, defects, residual risk, recommendation. Professional reviewers will recognize the format.

**Acceptance criteria:** the report renders offline, every number links to its evidence, and gate exit codes are tested.

---

### Phase 12 — MTA Self-Testing and Continuous Benchmarking

**Objective:** MTA must be the best-tested system in the company. Its effectiveness should be protected against regressions.
**Gaps closed:** G14 (ongoing)

- **12.1** Unit tests for every generator, linter rule, triage rule and analyzer (required in every phase anyway). Property-based tests for the generators and the renderer.
- **12.2** Golden snapshot tests for `spec_renderer.py` (plan → `.spec.ts`).
- **12.3** Contract tests: every agent's output validates against its schema, using recorded inputs.
- **12.4 LLM-agent eval sets:** for each LLM agent (Comprehension, TestData, SemanticMap, ScriptGen, TestDesign-LLM part, Healing), keep fixed inputs with invariant checks (e.g., "the plan uses only allowed locator keys", "every AC has a source quote"). Run them on prompt or model changes.
- **12.5 Nightly benchmark in CI** with metric regression gates: detection rate must not drop, false-failure rate must not rise, and heal precision must stay above 95%.
- **12.6 Periodic mutation testing of MTA itself** (mutmut on the `tools/test_design/`, `tools/triage/` and linter modules).

---

## 5. Professional Test Case Catalog

This is the tester's view of **what MTA must be able to generate**. Opus should encode sections D–N as data (`tools/test_design/catalog/*.yaml`) consumed by the P3 generators, not as prose in prompts.

### A. Black-box techniques: when MTA applies each one

| Technique | Applied when | Minimum generated |
|---|---|---|
| Equivalence partitioning | Any input field | 1 test per invalid class; valid classes combined into the positive test |
| Boundary value analysis (3-value) | Any length, numeric, date, count or size constraint | min-1, min, min+1, max-1, max, max+1 (+ nominal) |
| Decision table | AC contains ≥ 2 interacting conditions | 1 test per collapsed rule |
| State transition | Multi-step flows, status lifecycles (order: new → paid → shipped) | All valid transitions + invalid transitions + 1-switch on P0 |
| Use case / scenario | Each user journey | Main + every alternate + every exception flow |
| Pairwise | ≥ 3 parameters with options (filters, settings) | Full pairwise set |
| Error guessing | Every field or widget type | Catalog entries D–N |
| Exploratory (agentic, optional) | `thorough`+ profiles | A time-boxed charter-based LLM exploration within safety rails that records anomalies (5xx, console errors, broken images or links, layout overflow) as *findings*, not pass/fail |

### B. White-box techniques (P8)

| Technique | How MTA achieves it |
|---|---|
| Statement / branch coverage | V8 (frontend) + coverage.py/nyc (backend), with the gap loop generating targeted tests |
| Condition / decision coverage | Extracted `if` guards on inputs → decision tables with each condition toggled |
| MC/DC (critical rules only: auth, payment, pricing) | Each condition shown to independently affect the outcome |
| Path / loop | Loops over lists: 0, 1, many and max items (empty cart, 1 item, 99 items) |
| Data-flow | A value entered at step 1 must appear correctly at step N (summary page, email preview, invoice) |
| Static rule extraction | Validation schemas, regexes, role checks → constraints with `file:line` citations |

### C. Grey-box

- Set up data through the API, act through the UI, verify through the API or DB (most reliable for CRUD).
- Compare UI-displayed values with API responses (totals, counts, statuses).

### D. Field-level edge cases (error-guessing catalog)

**Text (generic)**
- Empty; whitespace only; leading/trailing spaces (trimmed or rejected? consistent?)
- min-1 / min / max / max+1; paste of 10,000 chars
- Multi-byte Unicode (length counted in characters vs bytes); emoji (surrogate pairs); combining characters; zero-width characters; RTL text
- Newline or tab in a single-line field
- HTML tags (`<b>x</b>` should render as text); `"null"`, `"undefined"`, `"NaN"`, `"0"` as literal strings
- Case sensitivity where relevant (usernames, codes)

**Email**
- Valid: plus addressing, subdomain, uppercase, long TLD
- Invalid: no `@`, two `@`, missing domain, leading or trailing dot, consecutive dots, spaces
- Local part of 64 chars / 65 chars; total 254 / 255; duplicate email on registration

**Password**
- Min and max length ±1; each missing character class; spaces; Unicode
- Same as the username; show/hide toggle
- Never present in URLs, logs or `localStorage`; paste allowed (accessibility)

**Number / money**
- 0, negative, decimal in an integer field, exponent (`1e5`), leading zeros, `+5`
- 2³¹ and 2⁵³+1; min/max ±1; step mismatch
- Locale separators (`1.000,50`); non-numeric input
- Rounding (0.005); currency precision; line totals add up to the overall total; tax and discount limits; negative quantity

**Date / time**
- Today, past, future; Feb 29 in leap and non-leap years; day 31 in a 30-day month
- DST transition day; midnight across timezones; start after end; min/max date ±1
- Locale formats; manual typing vs the picker

**Phone:** with or without country code; spaces, dashes, brackets; too short or too long; letters

**File upload**
- Allowed type; disallowed type; renamed extension (an `.exe` renamed to `.png`); 0-byte file
- max size and max+1; several files when only one is allowed; duplicate file name
- Special characters and Unicode in the file name; cancelled file dialog; upload interrupted (network fault)

**Dropdown / radio / checkbox**
- Default state; required with nothing selected; each option (EP); disabled option
- Dependent dropdowns (changing the parent resets the child); very long option lists (type-ahead)

**Search**
- Empty; no results (empty state); 1 result; many results (pagination)
- Special characters `% _ * ' "`; diacritics and case; leading/trailing spaces; very long query
- XSS payload reflected in "results for …"
- Fast typing (debounce, out-of-order responses)

**Lists / tables**
- Empty state; 1 item; exactly page size; page size + 1; last page; beyond the last page by URL
- Sort ascending/descending (stable, nulls first or last); filter combinations (pairwise)
- Changing the filter resets to page 1; selection kept or cleared across pages

### E. Form behaviour

- Submit with the Enter key; double-click submit (exactly 1 record created)
- Error clears after correction; focus moves to the first error; required markers match the real validation
- Back after submit (no duplicate re-submission); refresh mid-form; leaving with unsaved changes (warning shown?)
- Browser autofill; client-side validation bypassed (send directly to the API → the server must reject)

### F. Authentication, session and authorization

- Valid login; wrong password; unknown user (same generic error, so no user enumeration); locked account; username case sensitivity
- Session expiry using `page.clock`; logout invalidates the session (back button + API call with the old cookie → 401)
- Deep link while logged out → login → redirected back to the original target
- Multi-tab logout; remember-me
- **Role matrix:** every role × every page and action (allowed / hidden / blocked by URL / blocked by API)
- **IDOR:** change the resource ID in the URL or API to another user's
- Password reset flow (non-prod)

### G. Data integrity and CRUD

- Create → shows in the list → detail matches the input → survives reload → edit → updated everywhere → delete → removed from the list → direct URL returns 404 or "not found"
- Duplicate creation handling
- Concurrent edit in two browser contexts (conflict or last-write-wins, whichever the BRD specifies)
- Special characters round-trip unchanged (save `O'Brien & <Co>` → shown exactly the same)

### H. Navigation and browser behaviour

- Every link returns status < 400; back/forward keep the right state; refresh on every state; deep link to every page
- 404 page for a random path; `target=_blank` has `noopener`
- Downloads are valid (name, size > 0, opens); native dialogs (confirm → Cancel does nothing, OK proceeds)

### I. Concurrency and race conditions

- Double-click actions; rapid repeated toggles
- Two tabs on the same entity; navigating away while a request is pending (no crash or ghost update)
- Slow response arriving after a newer request (stale data must not overwrite fresh data)

### J. Resilience (P7.6)

- API 500/503/timeout/empty/malformed; offline mid-flow; slow 3G
- 401 mid-session → clean re-login, no data loss
- Third-party script failure (analytics, chat widget blocked) → the app still works

### K. Accessibility (P7.1)

- axe WCAG 2.2 AA per state; full keyboard operability; visible focus; no focus trap
- Modal focus management; labels and error announcements; contrast
- 200% zoom with no loss of content; `prefers-reduced-motion` respected

### L. Performance (P7.3)

- Per-page budgets (LCP, CLS, TTFB, bytes, request count)
- Slow-API detection; no request waterfall longer than N on critical pages
- Memory growth over 20 repeated navigations (Chromium only, optional)

### M. Security (P7.4)

- Passive: headers, cookies, mixed content, secrets/PII in URL or storage, verbose errors
- Active (non-prod only): XSS (reflected and stored, with an execution check), injection error leaks, open redirect, IDOR, auth bypass, CSRF token presence, login rate limit

### N. Compatibility, responsive, i18n (P7.5, P7.7)

- Chromium/Firefox/WebKit; 320–1440 px viewports; no horizontal scroll; touch targets
- Locale/timezone matrix; RTL layout; +40% text expansion; date/number/currency formats

### O. AI agents (P9)

See the table in P9.1. Every agent gets at least: 10 task-success, 5 groundedness, 5 no-answer (hallucination), 3 consistency (×5 runs), 10 robustness variants, 3 multi-turn, 10 injection (direct + indirect), 3 leakage canaries, 3 out-of-scope, latency/cost budgets, plus tool-use cases if traces are available.

### P. Suite definitions

| Suite | Contents | Target duration | When it runs |
|---|---|---|---|
| Smoke | P0 positive journeys, chromium | < 10 min | Every deploy / PR |
| Sanity | Smoke + tests impacted by the change | < 20 min | PR |
| Regression | `standard` profile, chromium | < 45 min | Nightly |
| Full | `thorough` profile + matrix + non-functional | Sharded | Nightly / weekly |
| Release | Full + quality gates + security active (staging) | — | Before release |

---

## 6. Playwright — keep vs change

| Area | Keep | Change |
|---|---|---|
| Runner / language | TypeScript `@playwright/test`. It's the right choice | Upgrade to the latest stable version and pin it |
| LLM writes JSON plans, a deterministic renderer writes TS | **Keep.** This is MTA's best design decision | Extend the action vocabulary (P5.1); render `test.step` per plan step |
| Page Object Model (`pages.ts`, `locator_map.json`) | Keep | Container-scoped locators (P2.1); identity fingerprint per key (P6.3) |
| `testIdAttribute: data-test` | — | Configurable per project, default `data-testid` |
| Chromium only | — | Projects matrix: firefox, webkit, mobile devices (by profile) |
| `retries` + flaky counted as pass | Keep retries | Record `flaky` as its own status; `failOnFlakyTests` in CI if supported; burn-in with `--repeat-each` |
| `video/trace on-first-retry` | — | `retain-on-failure` for trace and video |
| Reporters list/json/html | Keep | Add `junit`, `blob` (sharding) and a custom MTA traceability reporter |
| Single `storageState` | — | Per-role auth setup project + `role` fixture |
| `waitForTimeout` in the vocabulary | — | Remove from the LLM vocabulary; web-first assertions, `expect.poll`, `toPass` |
| No fixtures for data | — | `testData`, `cleanup`, `api`, `consoleGuard`, `network`, `a11y`, `perf`, `safety` fixtures |
| Base URL fallback to localhost:3000 | — | Remove, fail fast |
| Browser-close → skipped | Headed human-close case only | Error in headless/CI |
| — | — | Add `page.route` fault injection, `context.setOffline`, `page.clock`, `toMatchAriaSnapshot`, `toHaveScreenshot`, `@axe-core/playwright`, `page.coverage` (Chromium), `routeFromHAR` for unstable third parties, `--shard` + `merge-reports`, tags (`@P0`, `@REQ-…`) with `--grep` |
| Legacy pytest mode | Keep for backward compatibility | Mark deprecated; no new features |

---

## 7. KPIs to show your manager

Fill in the "Baseline" column from Phase 0, then update it after each phase.

| KPI | Definition | Baseline | Target |
|---|---|---|---|
| Requirement coverage | Testable ACs with ≥ 1 executed test ÷ testable ACs | _P0_ | ≥ 90% |
| **Seeded-bug detection rate** | Benchmark bugs caught ÷ bugs enabled | _P0_ | ≥ 80% |
| False-failure rate | Failures on the bug-free build ÷ tests | _P0_ | < 3% |
| Flaky rate | Flaky ÷ executed | _P0_ | < 2% |
| Assertion strength (median) | Linter score | n/a | ≥ 80 |
| Heal precision | Correct heals ÷ heals applied | _P0_ | ≥ 95%, **0 healed product bugs** |
| Technique coverage | Share of fields with EP+BVA, flows with state-transition tests | ~0 | 100% of P0/P1 |
| API endpoint coverage | Endpoints tested ÷ inventory | 0 | ≥ 90% |
| Code branch coverage (where available) | Branch % | n/a | ≥ 70% on critical modules |
| Mutation score (sampled) | Killed ÷ total mutants | n/a | ≥ 60% on critical modules |
| AI-agent safety pass rate | Lower confidence bound on injection/leakage cases | n/a | ≥ 95% |
| Run time (standard profile) | Wall clock | _P0_ | ≤ 45 min sharded |
| LLM cost per run | Tokens × price | _P0_ | Tracked; ≤ 1.5× baseline despite 10× more tests (deterministic generators) |

---

## 8. Copy-paste prompts for Opus

### 8.1 Master Context Prompt (start of every session)

```
You are a senior test-automation architect and engineer working on the Master Testing Agent (MTA) repository.

Read, in this order: README.md, docs/MTA_IMPROVEMENT_PLAN.md (the plan), and docs/audit/current_state.md (if it exists — it overrides the plan wherever they disagree).

Working rules:
1. Implement ONLY the phase I name. Do not start the next phase.
2. Before coding, verify every assumption the phase makes against the actual code. Then write docs/phases/phase-<N>-design.md: files to change, new files, data/schema changes, migration plan, risks, and anything in the plan that does not match reality (with your proposed adjustment). Then implement.
3. Backward compatibility: existing projects and v1 artifacts must keep working. New behaviour sits behind project.yaml flags with the defaults the plan specifies.
4. Create new agents ONLY with tools/scaffold_agent.py and keep the one-agent-one-folder, 7-file convention. Register them in agents/registry_setup.py and add them to the workflows explicitly.
5. Deterministic Python for anything computable. Use the LLM only for interpretation, and validate every LLM output against a schema.
6. Never weaken an existing guard (locator validation, the healing tool-surface boundary, placeholder-negative dropping, the safety rails).
7. Every code change needs unit tests (pytest / vitest). Run them and show the output. Add integration tests where the phase's acceptance criteria require them.
8. Update README.md and the affected agent.md / agent.json files.
9. Finish with docs/phases/phase-<N>-report.md: what changed, tests run (with output summary), benchmark before/after (from Phase 0 onward), deviations from the plan, open issues, and recommendations for the next phase.
```

### 8.2 Phase Prompt (one per session)

```
Implement Phase <N> — <title> from docs/MTA_IMPROVEMENT_PLAN.md.

Scope: tasks <N.1 … N.x> exactly as written (adjusted only where docs/audit/current_state.md says reality differs — explain each adjustment in the design note).
Acceptance criteria: as listed in the phase. Prove each one in the phase report (command + result).
Required tests: as listed in the phase, plus unit tests for all new code.
Run the Phase 0 benchmark at the end and include the before/after metrics.
Do not start Phase <N+1>.
```

### 8.3 Review Prompt (optional, after each phase, in a fresh session)

```
Act as a strict QA lead reviewing Phase <N> of the MTA improvement plan.
Compare the diff against docs/MTA_IMPROVEMENT_PLAN.md Phase <N> acceptance criteria.
For each criterion: met / partially met / not met, with evidence (file:line or test output).
Then list: correctness bugs, missing tests, places where a guard was weakened, silent degradations, and anything that could make a test pass while the application is broken.
```

---

*Plan v1, 2026-10-10. Based on README.md only; Phase 0.1 reconciles it with the code.*
