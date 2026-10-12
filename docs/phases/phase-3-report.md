# Phase 3 — Test Design Agent: Report

> Fast-track report (≤ 1 page). Design: `docs/phases/phase-3-design.md` (D1–D11). Not committed yet.

## What changed

- **New agent** `agents/test_creation/test_design/` (scaffolded), step `test_design` between `testdata` and
  `semantic_map`. Off unless `test_generation.profile` is set (on in the template and the buggy_shop benchmark).
- **Shared core** `tools/test_design/`: generators `ep, bva, decision_table, state_transition, pairwise, use_case,
  crud, error_guessing (+ catalog/error_guessing.yaml), role_matrix`; `inputs` (constraint precedence DOM > BRD >
  observed > default), `linking`, `risk`, `assign`, `select` (profiles + budget), `llm` + `prompts` + `hint_cache`
  (one schema-validated call per module, additive only), `locators`, `design`, `store`, `models`.
- **Artifact** `test_creation/test_cases.json` (contract `test_cases`, `schemas/test_cases.v2.schema.json`):
  selected cases, `cut[]` with reasons, `conflicts[]` (BRD vs observed, incl. permission cells).
- **ScriptGeneration** implements exactly each scenario's selected cases (chunks of 6, `case_id`), re-applies the
  guards after retyping, requires an assertion and the value under test (`no_assertion`, `input_not_used`), records
  every unimplemented case (`not_expressed`, …) as the AC's uncovered reason. Form fields of crawled pages are merged
  into `locator_map.json` as `#form [name=…]` CSS + the observed error area, validated on their own page.
- **Tracing / renderer / traceability**: case ACs + risk priority, `@<technique>` tag, `{type: "case"}` annotation,
  `budget` / `not_expressed` reasons (only with a profile).
- **Benchmark**: `tools/benchmark/design_metrics.py` — coverage and bug targeting at three honesty levels (any
  technique / excluding AC-restating `use_case` / implemented in specs); added to the run record and report.

## Tests

| Suite | Result |
|---|---|
| `pytest tests/unit` (full) | **1,657 passed, 0 failed** (count lower than Phase 2's 1,953 only because the per-artifact contract test is parametrised per file on disk and the benchmark project was re-materialised) |
| Phase 3 files (`test_test_design_*.py`) | **114 passed** — exact BVA values incl. leap years / month ends, decision-table collapse, pairwise all-pairs proof, hypothesis properties (BVA, dates, collapse, pairwise, selection), determinism across processes/hash seeds, every review finding |
| `npx vitest run` | 49 passed (no TS change) |

## Acceptance criteria

| Criterion | Evidence | Verdict |
|---|---|---|
| ≥ 90% of testable ACs covered (standard) | Design level, frozen buggy_shop: 54/54 = 100% (any technique); excluding `use_case`: see `test_doc_accounting_and_honest_metrics`. Spec level (quick run): 41.0% of testable ACs have an implemented case | Met at design level; **not met** at spec level (cart/order elements missing, see open issue 1) |
| Every seeded validation / state-machine bug targeted | Design level 5/5 (BVA/EP on BUG_01/BUG_21, EP+BVA on BUG_18, use case on BUG_10/BUG_17). On the app: 3/5 caught (BUG_01, BUG_18, BUG_21); BUG_10 not implemented; BUG_17 not run | Met at design level for 5/5; partially met at spec level |
| Budget respected | 167 cases, est. 25 min ≤ 400 / 45 min; P0 + floor over budget is reported, never hidden | Met |
| Deterministic generators | Byte-identical across runs, processes and `PYTHONHASHSEED` 0/1/4242 | Met |

## Benchmark (reduced, per the 18:30 time box)

Quick run, 18:05–18:43: `.aqp_artifacts/benchmark/quick_phase3/quick_phase3.json`. Only modules M03 (product form)
and M04 (cart) were generated; one bug-free run, then one run for each of the 5 acceptance bugs.

| Metric | Phase 2 (full run, 22 bugs) | Phase 3 quick (M03+M04, 5 bugs) |
|---|---|---|
| Acceptance bugs caught (BUG_01/18/21/10/17) | 0 / 5 | **3 / 5**: BUG_01 (7 tests, incl. BVA "max 50 chars accepted"), BUG_18 (2), BUG_21 (2: BVA "min-1 (0)", EP "negative number") |
| Tests generated | 74 (all modules) | 61 (2 modules) |
| False-failure rate, bug-free build | 18.9% | 19.7% (12/61) |
| Designed cases that became tests | n/a | 60 of 111 selected; M03 49/77 = 64% |
| AC coverage of selected cases: any technique / excl. use_case / implemented in specs | n/a | 100% / 35.9% / 41.0% (of the 39 testable ACs designed so far) |

Not caught: BUG_10 (empty-cart checkout) and BUG_17 (upload type). BUG_10's cases need cart and order elements that
are missing from the locator map (state-dependent UI, Phase 2 open issue #1), so M04 implemented 1 of 8 scenarios.
BUG_17's module M05 was not generated in this quick run.

**False failures, 12 tests in 3 groups:**
- Native-validation login/name cases: the browser blocks the submit, so the app's own error text is never shown.
- "Violate the AC" exception flows whose expected text is too vague to check.
- Quantity cases: the expected error message is shown in the cart, not on the product page.

The full 22-bug benchmark (`python -m tools.benchmark.run --app buggy_shop --label phase3 --repeat 1 --no-healing`,
≈ 2.5 h) was **not** run; Phase 2's numbers are not directly comparable to the reduced run above.

## Deviations from the plan

- Catalog lives in `tools/test_design/catalog/error_guessing.yaml`; titles are templated, the LLM titles only its own
  cases; SemanticDedup runs on the LLM's extra cases (deterministic duplicates are removed by input signature).
- Cases above the profile are counted (`excluded_by_profile`), not listed. Per-test-case TestData is left to P4.4.
- "Targeted" is measured at design level and, separately, on implemented specs.

## Open issues / recommendations for Phase 4

1. **Highest impact:** state-dependent UI (cart lines, totals, order pages) has no locators, so most M04 cases are
   `not_expressed`. P4.4 data fixtures (put items in the cart first) plus a crawl of those states will fix it.
2. **False failures (19.7%):** native-validation and vague "violate" cases need the P5 oracle work (page-text
   assertions, choosing native vs. app messages). Until then, consider `design_llm` cases at `thorough` only.
3. Role switching inside one spec: role cases go to a module that signs in as that role; P4.3 per-role fixtures
   will remove the routing.
4. File-upload BVA/EP cases need fixture files (`needs_fixture`) — P4.4.
5. Page-level text assertions ("Access denied" without a locator) need a page-text action — P5.1.
6. With a profile, scenarios that already have a spec keep it; their new cases are logged, not implemented.
7. Phase 2's `form_model` records wrong role locators for `type=search` inputs and `<select>`s (Phase 3 works
   around it with form-scoped CSS); fix at the source.
