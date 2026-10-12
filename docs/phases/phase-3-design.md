# Phase 3 — Test Design Agent: Design Note

> One-page note (fast-track process). Inputs checked against the code on 2026-10-11 at `34cf214`.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | **Placement:** `testdata → test_design → semantic_map → script_generation`. TestData stays per scenario. | Design cases carry their own concrete input values (BVA/EP/catalog). TestData's positive dataset is still the "fill all valid" baseline. Per-test-case data factories belong to P4.4 fixtures. |
| D2 | **Switch:** `test_generation.profile` (`smoke`/`standard`/`thorough`/`exhaustive`) turns test design on. No profile → TestDesignAgent skips and ScriptGeneration is byte-identical to Phase 2. Like Phase 1's `requirements.enabled`, the profile is set in the project template and the benchmark template only; existing projects stay off. Legacy caps with a profile → logged as deprecated (they no longer limit design cases). Needs `requirements.enabled` + `requirements.json`; Phase 2 artifacts are optional (missing ones disable their generators, recorded in `limitations`). | Plan principle 4 (opt-in). |
| D3 | **Bridge to ScriptGeneration:** each case is assigned to one scenario. ScriptGeneration sends a scenario's cases in chunks of ≤ 8 with a "test cases to implement" block. The LLM writes **one plan test per case** carrying `case_id`. Cases it can't express are recorded in `dropped_tests` (`not_expressed`). Every existing guard runs unchanged on the result. | The legacy plan → render → safety → trace path stays the single choke point. |
| D4 | **Locators for crawled pages:** fields + submit buttons of forms referenced by selected cases are merged into `locator_map.json` (new keys only, `_source: form_model`, `_page_url`). Live validation checks those entries on their own page, not the module page. | Phase 2 open issue #10: ACs went uncovered with `missing_locator` because only module landing pages reach the map. |
| D5 | **Case → scenario:** shared AC → scenario of the case's module whose role matches → first scenario of that module. Role cases go to a module whose setup logs in as that role (`guest` = log out first). Unassignable cases → `cut[]` with reason `no_scenario`. | Every case must land in a spec or be reported. |
| D6 | **Ids / determinism:** `TC-` + 8 hex chars of a SHA-1 over the case's content key. Generators are pure functions over sorted input. Output order is fixed (priority, risk, id). | "Same input → byte-identical output". |
| D7 | **LLM role:** one schema-validated call per module returns decision-table conditions/rules, AC links for cases deterministic linking could not map, and domain-specific extra cases. Extra cases are deduplicated by `SemanticDedupAgent` against the deterministic set (3.6). The LLM can add; it can never drop or rewrite a deterministic case. On failure → deterministic set only, `llm.status = degraded`. | Plan 3.3 / principle 1. |
| D8 | **Risk:** impact = AC priority weight + risk-tag bonus (auth/payment/data-loss/PII). Likelihood = input count, decision-table size, transitions touching the state, changed page (`structural_hash` differs from the last `test_cases.json`). `risk = impact × likelihood` → P0 ≥ 0.7, P1 ≥ 0.45, P2 ≥ 0.25, else P3 (calibrated on buggy_shop so that P0 ≈ 15–20% of the standard selection). A P0 AC's positive case is always P0. | Plan 3.4. |
| D9 | **Selection:** filter by profile level, keep every P0, then the profile's coverage floor (≥ 1 case per testable AC, plus a negative when the AC has a negative path), then descending risk until `max_tests` or `max_runtime_minutes` (per-case estimate) is reached. Everything cut is listed with `reason: budget`. | Plan 3.5; A9 (caps must be enforced in code). |
| D10 | **BRD vs observed:** when a probe shows the app accepting what an AC rejects (e.g. empty quantity accepted), or a permission cell shows access the BRD denies, the case keeps the BRD oracle and the conflict is listed in `conflicts[]` for human review. Observed behaviour is only the fallback oracle. | Plan 5.2 rule, Phase 2 recommendation; review finding 1. |
| D11 | **Plan ↔ case check:** after a plan test is retyped to its case's type, the placeholder-negative rule is re-applied, a test must assert something, and the value under test must actually be entered (`no_assertion`, `placeholder_negative_dropped`, `input_not_used`). | Review findings 2 and 11. |

## Files

- New: `agents/test_creation/test_design/` (scaffolded), `tools/test_design/` — `models, config, inputs, constraints, ep, bva, decision_table, state_transition, pairwise, use_case, crud, role_matrix, error_guessing (+ catalog/error_guessing.yaml), risk, select, assign, llm, locators, design, store`, `schemas/test_cases.v2.schema.json`.
- Changed: ScriptGeneration (case block, chunking, `_page_url` validation), `PlanTracer` (case ACs / priority), spec renderer (`@<technique>` tag), contracts registry/paths, `project_manifest`, `test_generation_config`, workflows (`full_workflow`, `test_test_creation_only`, `agents.yaml`, `agent_registry.yaml`), `registry_setup`, traceability (`budget` reason from `cut[]`), benchmark (design metrics + bug targeting), templates (`profile: standard`).

## Deviations from the plan

- Catalog lives in `tools/test_design/catalog/error_guessing.yaml` (§5 asks for `catalog/*.yaml`; task 3.2 names one file).
- Titles are deterministic templates; the LLM writes titles only for the cases it adds. This keeps the deterministic set byte-stable.
- "Has a test targeting it" is measured on `test_cases.json` (affected AC + a matching technique). The spec-level number is reported next to it.
- Security-probe catalog entries are generated only when `safety.allow_security_probes` is true.

## Risks

LLM output size per scenario (mitigated by chunking). Role switching inside a module spec (mitigated by D5 module/role routing; P4.3 adds proper role fixtures). Templated URLs (`/products/{id}`) use the crawled sample URL.
