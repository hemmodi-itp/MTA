# Phase 1 — Requirements and Traceability Backbone: Report

> Scope: tasks 1.1–1.4 of `docs/MTA_IMPROVEMENT_PLAN.md`, implemented as specified in the approved design
> (`docs/phases/phase-1-design.md`; decisions D0–D6 taken as recommended).
> Phase 2 was not started. Nothing has been committed yet.

## 1. Summary

| Task | Result |
|---|---|
| 1.1 Requirements | `test_comprehension/requirements.json` lists each requirement (`REQ`) with its atomic acceptance criteria (`AC`). Each AC carries testability with a reason, a P0–P3 priority, risk tags, a verified `source_quote` (or `source: dom_inferred`), and an atomicity flag. Scenarios in `business_scenarios.json` gain `ac_ids`. |
| 1.2 Traceability | `test_creation/traceability.json` maps each AC to its test cases, then to spec file + test title, latest result and defect ids (defect ids are reserved for now). It is rebuilt after script generation and updated after every Playwright run, including healing re-runs. ReportingAgent finalises it and adds a "Requirements Traceability" section to the report, which lists every AC with zero tests and the reason. |
| 1.3 Playwright tags | Every traced test carries `{ tag: ["@P1", "@negative", "@regression", "@REQ-01", "@AC-01.2"], annotation: [ac, tc, scenario] }` on its `test(` line, and its title starts with the primary AC id. `--grep @AC-…` / `--grep @P0` work. Healing can no longer strip or alter the tags. |
| 1.4 Shared core | New package `tools/requirements/`. The legacy pipeline uses all of it. The Agent-Eval DAG (`brd_builder`) imports the same `BrdIndex` and `normalize_requirements`; both were moved, not copied, and are re-exported from their old locations. |
| Ground truth | `benchmarks/apps/buggy_shop/acs.yaml` holds 27 hand-labelled ACs. `tools/benchmark/ac_recall.py` measures extraction recall. |

**Off by default.** Everything sits behind `requirements.enabled` in `project.yaml`, default `false` (D1). It is
turned on in the project template and in the buggy_shop benchmark template. With the flag off, prompts,
artifacts and generated specs are byte-identical to Phase 0. Tests prove this against a golden spec captured from
the Phase 0 renderer and against the exact scenario prompt text.

## 2. What changed

### New code

**`tools/requirements/`**

| Module | What it does |
|---|---|
| `models.py` | Pydantic schemas for `requirements` / `traceability`, and the schema the LLM response must match. |
| `brd_index.py` | Quote verifier, moved from Agent-Eval, plus `quote_match()` returning exact / fuzzy / none. |
| `normalize.py` | Agent-Eval normaliser, moved, plus the additive D3 enrichment. |
| `explicit.py` | Parser for requirement and criterion ids the document declares itself. |
| `atomicity.py` | Deterministic check that a criterion states one behaviour. |
| `classify.py` + `risk_rules.yaml` | Risk tags, priority precedence, testability rules. |
| `ids.py` | Stable, content-keyed ids, via a new `ArtifactRegistry.get_or_create_sequence_number`. |
| `prompts.py`, `extract.py` | Extraction: explicit parse, then 1 schema-validated LLM call, then merge, verify, atomicity, classify. |
| `store.py` | Per-module upsert of `requirements.json`. |
| `service.py` | Project-level operations: extract a module, list criteria for the prompt, link and re-link scenarios. |
| `linking.py` | Scenario ↔ AC and test ↔ AC links. |
| `tracing.py` | Plan annotation: `tc_id`, `ac_ids`, priority, title, recorded drops. |
| `traceability.py` | Rebuild, result folding, zero-test reasons, summary, report section. |
| `config.py` | Reads the `requirements` block of `project.yaml`. |
| `build.py` | CLI: `python -m tools.requirements.build`. |

**Elsewhere**

- `tools/benchmark/ac_recall.py`
- `benchmarks/apps/buggy_shop/acs.yaml`
- `schemas/requirements.v2.schema.json`, `schemas/traceability.v2.schema.json`

### Changed code

| File | Change |
|---|---|
| `agents/comprehension/comprehension_agent/agent.py` | Extracts requirements per BRD before scenario generation; offers ACs to the scenario prompt; links and validates scenarios; re-links still-unlinked scenarios project-wide after export. |
| `tools/comprehension/{models,generate_business_scenarios,prompts}.py` | `ac_ids` / `ac_link_source` on `BusinessScenario`, serialised only when set; AC block in the scenario prompt, empty when the flag is off. |
| `agents/test_creation/script_generation/{agent,prompt}.py` | `PlanTracer`: AC block in the plan prompt, per-test `tc_id` / `ac_ids` / `ac_link` / `priority` / `title`, `dropped_tests[]`, unexpressible plans kept, `traceability.json` rebuilt after every run. |
| `tools/test_creation/script_generator/spec_renderer.py` | One-line details object and AC title prefix for traced tests; untraced output unchanged. |
| `agents/common/fallback_core.py` | Python-fallback specs get describe-level `@degraded @AC-…` tags; they are not counted as coverage. |
| `tools/test_creation/testdata/{generate_test_data,models}.py` | `capped_variants` recorded (feeds the `budget` reason). |
| `agents/test_execution/ui_execution/agent.py` | Records `pw_status`, `tags`, `annotations`, `tc_id`, `ac_ids` per result; folds every run into traceability (never fatal). |
| `agents/test_execution/healing/{tools,prompt}.py` | Header-details guard in `apply_patch`, plus one prompt line. |
| `agents/test_execution/reporting/agent.py`, `tools/test_execution/reports/html_report.py` | Traceability section in the JSON and HTML reports. |
| `agents/orchestrator/agent.py` | Hint when cached discovery skips requirement extraction. |
| `agents/comprehension/discovery/agent.py` | URL-only mode marks requirements `source: dom_inferred`. |
| `agents/comprehension/brd_builder/agent.py`, `tools/agent_eval/brd_source.py` | Import the moved code from the shared core; re-export it. |
| `contracts/artifacts/{models,registry,paths,boundary}.py` | `requirements` and `traceability` contracts, paths and step mapping. |
| `tools/project_manifest.py` | Passes the `requirements` block through. |
| `tools/benchmark/{run,score,report_md,apps}.py` | Per-test AC links from `traceability.json`; child ids roll up to their BRD AC; direct-only coverage; AC-extraction recall in every run. |
| Templates | `requirements.enabled: true` in `aAprojectTemplate/project.yaml` and `buggy_shop/mta_project/project.yaml.tmpl`. |
| Docs | `README.md`, plus `agent.md` / `agent.json` for 9 agents: Comprehension, BrdBuilder, Discovery, ScriptGeneration, TestData, UIExecution, Healing, Reporting, Orchestrator. |

**No new agent.** Phase 1 is library code called by existing agents, so `tools/scaffold_agent.py` was not used.

**No guard weakened:**
- Locator validation, `_drop_placeholder_negative_tests`, `_flag_action_locator_type_mismatches`, the safety
  rails and the healing tool surface are unchanged. Drops are now only *recorded* as well.
- Healing gained one more guard.

## 3. Tests

| Suite | Before Phase 1 | After Phase 1 |
|---|---|---|
| `python -m pytest tests/unit` | 1,472 passed | **1,702 passed, 0 failed** (3 m 41 s) |
| `npx vitest run` | 36 passed (3 files) | **36 passed** (no TS runtime change) |

222 new tests in 13 files. The total also moves with the per-artifact contract test, which is parametrised per
artifact file on disk; the regenerated benchmark project changed that file set.

| File | Covers |
|---|---|
| `test_requirements_models.py` | AC extraction schema: id formats, enums, mandatory reasons, child ids, duplicates, LLM response contract, contract registration, round trips, exported schemas |
| `test_requirements_quote_verifier.py` | Exact, near-exact (fuzzy), **paraphrased** (not verified), **fabricated** (rejected), too-short quotes; Agent-Eval re-export is the same object |
| `test_requirements_deterministic.py` | Explicit parser (buggy_shop: 8 REQ / 27 AC), atomicity (10 atomic + 7 compound labelled statements), risk catalog, priority precedence and floor, testability heuristics, stable ids, config, manifest |
| `test_requirements_extract.py` | Merge: the LLM can't drop declared ACs; splits are validated; fabricated additions rejected; repair retry; transient retry; degraded paths; cross-module collisions and duplicates; verified-quote fallback; `dom_inferred` |
| `test_requirements_linking.py` | Scenario and test linking: validation, similarity, cross-module fallback, inheritance, unlinked |
| `test_traceability.py` | Traceability update: every zero-test reason, split parents, legacy specs, late linking, result matching (annotation → title), `pw_status`, aggregation, summary, report section, I/O no-ops when the flag is off |
| `test_spec_renderer_traceability.py` | One-line details, title prefix, golden byte-identity with the Phase 0 renderer, healing block extraction on traced specs, fallback describe tags, `PlanTracer` |
| `test_healing_details_guard.py` | Patch keeping details → applied; dropping or changing them, or multi-line details → rejected; specs without details unaffected |
| `test_ui_execution_trace_fields.py` | Parsing of tags / annotations / `pw_status`; traceability hook is never fatal |
| `test_report_traceability_section.py` | HTML lists uncovered ACs with reasons and unlinked tests; escaping; absent when off |
| `test_phase1_pipeline_integration.py` | ComprehensionAgent and ScriptGenerationAgent end to end with a stubbed LLM, flag on and off; failure isolation; orchestrator hint |
| `test_requirements_store_service.py` | Per-module upsert, build CLI, D3 enrichment, `ac_ids` surviving the scenario model, shared prompt criteria, re-link, capped variants |
| `test_benchmark_phase1.py` | `acs.yaml` integrity, id stripping, recall matcher (best match, project-wide fallback), coverage roll-up, inventory from traceability |

Existing Agent-Eval tests ran unchanged against the moved code: 44 passed. These were
`test_brd_builder_grounding`, `test_mta_evaluation_core`, `test_trace_static_runtime`, `test_llm_prompt_fencing`
and `test_brd_compliance`. No existing test needed changing.

## 4. Acceptance criteria — proof

| Criterion | Command | Result | Verdict |
|---|---|---|---|
| ≥ 90% of hand-labelled ACs extracted on buggy_shop | `python -m tools.benchmark.ac_recall --app buggy_shop` | **27/27 = 100%** → `benchmarks/results/2026-10-10_buggy_shop_ac_recall.json` | **Met** |
| (same, LLM must find the ACs itself) | `python -m tools.benchmark.ac_recall --app buggy_shop --strip-ids` | **27/27 = 100%** with every REQ/AC id removed; matching is by text → `…_ac_recall_stripped.json` | **Met** |
| (same, inside the real pipeline) | `python -m tools.benchmark.run --app buggy_shop --label phase1` | "AC extraction recall (vs acs.yaml) 100.0%" for the pipeline's own `requirements.json` | **Met** |
| The report lists every AC with zero tests, with a reason | Same run; HTML report `bench_buggy_shop/test_execution/reports/html/20261010_115257_bench_buggy_shop.html` | "Requirements Traceability — 13 AC(s) with no test". Each is listed with a reason: `generation_failed` 9, `missing_locator` 3, `not_supported:api` 1. JSON report key `traceability.uncovered` | **Met**, with one correction: see the note below |
| Every generated test maps to at least one AC | Same run; `test_creation/traceability.json` | **64 / 67 tests linked** (59 direct, 3 similarity, 2 inherited). 3 unlinked, listed in `unlinked_tests` and in the report, never hidden | **Partially met** — see the note below |
| Required: AC extraction schema tests | `pytest tests/unit/test_requirements_models.py` | passed | Met |
| Required: quote-verifier tests (exact, paraphrased, fabricated) | `pytest tests/unit/test_requirements_quote_verifier.py` | passed | Met |
| Required: traceability update tests | `pytest tests/unit/test_traceability.py tests/unit/test_ui_execution_trace_fields.py` | passed | Met |

**Note on the 3 unlinked tests.** The benchmark showed why they were unlinked; I fixed it after the run.

*Cause:*
- Modules run one at a time. M01's role-access scenario was linked before M04's and M06's criteria existed
  (AC-06.2.x, AC-07.1.x).
- M06's `/api/health` scenario failed for a different reason. Cross-module de-duplication had kept AC-01.6
  (owned by M01) out of M06's scenario prompt.

*Fixes:*
- Still-unlinked scenarios are re-linked project-wide after each comprehension run, and in memory during tracing
  and traceability rebuild.
- Criteria another module owns are offered to the prompt of every module whose BRD states them.

*Effect:* applied deterministically to a copy of the benchmark project, the re-link took the result to
**66 / 67**. The last test only links once the suite is regenerated with the prompt fix; that fix is unit-tested.
A fresh generation run is needed to show 67/67 end to end; see §8.

**Note on the reasons.** The 9 `generation_failed` entries were really scenarios ScriptGeneration skipped as
"plan has no tests the action library can express". They were missing locators, and in some cases actions. The
log shows the exact counts per scenario. That plan was never saved, so the reason was lost. With tracing on, the
plan is now kept, and these ACs report `missing_locator` / `missing_action`; this is covered by tests. The
benchmark numbers above predate this fix.

## 5. Benchmark — before / after

`buggy_shop`: 22 seeded bugs, Gemini `gemini-3.6-flash`, full workflow per module, 2 bug-free runs, 1 run per bug,
heal probe on. "Before" is the Phase 0 **fixed** baseline, as recommended in the Phase 0 report.

| KPI | Before (P0 fixed baseline) | After (Phase 1) |
|---|---|---|
| Tests generated / executed | 53 / 53 | 67 / 67 |
| **Requirement (AC) coverage** | **0.0 % (0/27)** | **85.2 % (23/27)** |
| AC coverage, direct links only | n/a | 85.2 % (23/27) |
| AC extraction recall (vs `acs.yaml`) | n/a | 100 % (27/27) |
| Seeded-bug detection rate | 4.5 % (1/22) | 4.5 % (1/22) |
| False-failure rate (bug-free build) | 28.3 % (15/53) | 22.4 % (15/67) |
| Flaky rate (2 bug-free runs) | 0.0 % | 0.0 % |
| Heal precision | n/a — 1 probe, 0 files changed | n/a — 1 probe (BUG_08, 6 catching tests), 0 applied, **0 wrong** |
| Generation runtime | 2,992 s | 2,636 s |
| Total runtime | 7,471 s | 7,598 s |
| LLM calls / tokens in / out | 223 / 1,094,320 / 439,939 | 228 / 1,240,952 / 491,623 |
| LLM cost | unpriced | unpriced (`benchmarks/pricing.yaml` still empty) |

Results: `benchmarks/results/2026-10-10_buggy_shop_phase1.{json,md}`.

**Reading the numbers:**
- **AC coverage moved from 0% to 85%.** This is the metric Phase 1 targets. In the baseline, no test carried an
  AC id. Now 64 of 67 tests do.
- **The 4 BRD ACs without an executed test** are AC-02.2, AC-02.4, AC-03.7 and AC-05.1. Each has a reason in the
  report; all four are locator gaps, which Phase 2's deeper discovery addresses.
- **Detection is unchanged (1/22, BUG_08 again, still incidental).** That is expected. Phase 1 adds traceability,
  not test logic. Stronger tests come in P3 (test design) and P5 (oracles).
- **The false-failure rate fell (28.3% → 22.4%).** This is regeneration variance, not a Phase 1 effect. The same
  causes remain: 9 upload tests whose fixture files were never created, 3 session/logout tests, and 3 others
  (double-click, invalid discount code, order placement).
- **Cost:** +5 LLM calls (one requirement extraction per module, minus run-to-run variance), +13% input tokens.
  Generation was faster this run.
- **Traceability detail (finer than the 27 BRD ACs):**
  - The LLM split 20 BRD criteria into atomic children, giving 60 leaf ACs.
  - 47 of the 60 leaves have tests (78.3%): 39 passing, 8 failing.
  - At BRD level a split criterion counts as covered when any of its children is (the benchmark rolls children up
    to their parent); `traceability.json` is stricter and only marks a split parent covered when every child is.

## 6. Deviations from the plan

| # | Plan | What was done | Why |
|---|---|---|---|
| 1 | IDs `REQ-###` / `AC-###.#` | The BRD's own ids are kept when present (`REQ-01`, `AC-01.2`). Generated ids are `REQ-###` / `AC-###.#`. Atomic children are `AC-03.2.1`. | Testers and the benchmark ground truth use the document's ids. Children roll up under `\bAC-\d+\.\d+\b`. (Design R2) |
| 2 | `comprehension/requirements.json` | `test_comprehension/requirements.json`; the loader also finds `comprehension/` | Audit A5 |
| 3 | "Reuse Agent-Eval's atomic-criteria logic" | Reused its prompt rule. Added a deterministic atomicity check. An LLM split is kept only if every part is grounded in the parent. | In Agent-Eval, atomicity was prompt-only (A11) |
| 4 | `test_case_ids` | Stable `tc_id` per plan test, from `artifact_registry.json` | `test_cases.json` does not exist until P3 |
| 5 | Defect ids | `defect_ids` reserved, always empty | No defect concept until P6 / P11 |
| 6 | Tags such as `@bva` | Type tags instead: `@positive` / `@negative` / `@boundary`, plus `@smoke` / `@regression` | Techniques arrive in P3 |
| 7 | "Every test maps to ≥ 1 AC" | Allowed link kinds: direct, similarity, or inherited from the scenario (D2). Tests with no possible link are reported as unlinked, never given an invented link. | Honest traceability |
| 8 | Results "after every execution" | Hooked in UIExecution, which covers healing re-runs and benchmark runs. Raw `pw_status` is recorded; UIExecution's own skipped→failed mapping is unchanged (D6). | Changing pass/fail counts belongs to P4.7 |
| 9 | (not in plan) | Healing guard for the details object | Otherwise healing could silently strip traceability (design R10) |
| 10 | (not in plan) | Recall measured twice: as written, and with ids stripped | The BRD declares every id, so a parser alone scores 100% (design R15) |
| 11 | (not in design) | Extra safeguards found while measuring: cross-module de-duplication of LLM-added criteria; a criterion with no stated criteria is checked against its verified BRD quote, never the LLM's summary; one retry on transient connector errors; best-match recall scoring | Each was found by the LLM recall runs, which initially showed 74.1% stripped recall (a Gemini 5xx), duplicates, and unverifiable summaries |
| 12 | (not in design) | After the benchmark: late re-link of unlinked scenarios, shared criteria in the scenario prompt, unexpressible plans kept for the reason | Gaps the benchmark exposed (§4); applied after the measured run |

## 7. Open issues

1. **67/67 linked tests not yet shown end to end.**
   - The recorded run has 64/67. The deterministic fix reaches 66/67 on a copy.
   - The last test needs regeneration with the shared-criteria prompt fix.
   - A generation-only rerun takes about 45 min of Gemini time, and showing 67/67 needs exactly that. I have not
     started it.
2. **The benchmark's uncovered reasons predate the plan-keeping fix.** In the recorded report 9 entries say
   `generation_failed`; the next run will say `missing_locator` / `missing_action`.
3. **Classification agreement with the hand labels is moderate** (informational, not gated):
   - testability 96–100%
   - risk-tag Jaccard 0.87
   - priority only 44–48%: the LLM rates many criteria P0 where I labelled them P1
   - atomicity 67–78%: the LLM over-splits, e.g. AC-01.2 into wrong-password / unknown-user
   - P3's risk-based selection uses priority, so calibrate it there: tighten the prompt rubric, or let the
     deterministic rules decide more.
4. **Over-splitting inflates the leaf count** (27 → 60) and makes "partial" coverage common for split parents.
5. **Late linking doesn't update tags.** A test linked after generation is traced correctly, but its spec's tags
   lack the AC until the spec is regenerated.
6. **Skipped still counts as failed in UIExecution** (D6). Traceability is correct (it uses `pw_status`).
   Fix it with P4.7.
7. **Healing guard effectiveness is unmeasured.** The guard only rejects; whether the healing LLM keeps the details
   object on its first try is not yet measured. P6's heal audit log should count these rejections.
8. **Pre-existing:** `application_assets/myTestProjects/alterDomusInvest/.../test_BS-011_*.spec.ts` has a syntax
   error. Because `playwright.config.ts` `testMatch` spans all projects, it breaks
   `npx playwright test --list` unless a path is given. Not touched.
9. **Pricing:** `benchmarks/pricing.yaml` is still empty, so cost stays `null` (carried over from Phase 0).
10. **Healing prompt:** one prompt line was added for every project. It is harmless for specs without details.

## 8. Recommendations for Phase 2

- Run one generation-only benchmark pass first, to show the post-run fixes on fresh output:
  - 67/67 tests linked
  - `missing_locator` instead of `generation_failed` in the reasons
- Every uncovered BRD AC in this run is a locator gap: `missing_locator`, or a skipped scenario with missing
  locators. That is exactly what P2.1–2.2 (wider element capture, constraint capture) target, so P2 should move AC
  coverage further without touching Phase 1 code.
- When P2 adds `app_map` / `form_model`, give those artifacts AC ids through the same `tools/requirements` linking,
  so P3 can build `test_cases.json` with real `ac_ids` from the start.
