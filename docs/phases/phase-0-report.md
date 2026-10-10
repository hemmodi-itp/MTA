# Phase 0 — Baseline, Benchmark and Safety Rails: Report

> Scope: tasks 0.1–0.7 of `docs/MTA_IMPROVEMENT_PLAN.md`, as adjusted by the approved design
> (`docs/phases/phase-0-design.md`, decisions D1–D6 = recommendations) and the audit
> (`docs/audit/current_state.md`). Phase 1 was not started.

## 1. Summary

| Task | Result |
|---|---|
| 0.1 Audit | `docs/audit/current_state.md` — every README claim later phases rely on, checked against the code, with 13 plan-vs-reality discrepancies (A1–A13). |
| 0.2 Benchmark apps | `benchmarks/apps/buggy_shop/` (FastAPI shop, **22 seeded bugs**, one env flag each, `bugs.yaml`, `brd.md` with 27 ACs, MTA project template) and `benchmarks/agents/buggy_bot/` (rule-based chatbot, 4 seeded weaknesses, `weaknesses.yaml`). |
| 0.3 Scoring | `tools/benchmark/` (`run.py`, `score.py`, `app_server.py`, `materialize.py`, `report_md.py`) + LLM token recorder `connectors/llm/usage.py` + `benchmarks/pricing.yaml`. |
| 0.4 Baseline | Two baselines (decision after the collision bug, §5): **as-is** and **after the locator-collision fix**, both in `benchmarks/results/`. |
| 0.5 Safety rails | `tools/safety/` (policy, hosts, action classifier + `destructive_rules.yaml`, payload detector, plan filter, test-data filter) wired into the manifest, ScriptGeneration, TestData, UIExecution and the TS runtime. |
| 0.6 Base URL | Every `localhost:3000` fallback removed (5 places); per-module resolution; fail fast; multi-module runs split per module; new specs pin `test.use({ baseURL })`. |
| 0.7 Contracts | `contracts/artifacts/` (Pydantic v2 models, v1→v2 migrations, atomic v2 writers, loaders), `schemas/*.schema.json`, orchestrator boundary validation (`contracts.enforce` warn/block), migration CLI. |

## 2. What changed

### New code
- `tools/safety/` — `policy.py`, `hosts.py`, `action_classifier.py`, `destructive_rules.yaml`, `payloads.py`, `plan_filter.py`, `testdata_filter.py`.
- `tools/base_url.py` — the single base-URL resolver (no default).
- `contracts/artifacts/` — `models.py`, `registry.py`, `migrations.py`, `io.py`, `paths.py`, `boundary.py`, `export_schemas.py`, `migrate.py`; `schemas/` (9 JSON Schemas).
- `connectors/llm/usage.py` — observe-only token recorder (+ JSONL sink via `MTA_LLM_USAGE_LOG`).
- `tools/benchmark/` — runner, scorer, app server, materialiser, Markdown report.
- `application_assets/_shared/runtime/baseUrl.ts`, `safety.ts` (+ vitest tests).
- `benchmarks/` — `apps/buggy_shop/`, `agents/buggy_bot/`, `pricing.yaml`, `results/`.
- `requirements-dev.txt` (pytest, httpx).

### Changed code
| File | Change |
|---|---|
| `tools/project_manifest.py` | passes `environment`, `safety` (resolved `SafetyPolicy`) and `contracts` into the request; warns on a missing `environment` |
| `agents/test_creation/script_generation/agent.py` | safety filter before render; module-aware `_load_base_url`; no localhost in the prompt; v2 readers/writers; **module-scoped reverse locator index** (collision fix) |
| `tools/test_creation/script_generator/build_dom_locator_map.py` | **locator-map merge/dedup/reconcile scoped per module** (collision fix) |
| `tools/test_creation/script_generator/spec_renderer.py` | `test.use({ baseURL })` for new specs |
| `agents/test_creation/testdata/agent.py` | security-payload filter (D1); v2 fallback writer |
| `agents/test_execution/ui_execution/agent.py` | base-URL fail fast, per-module split, `MTA_ALLOWED_HOSTS`, `execution_results` v2 record |
| `agents/orchestrator/agent.py` | contract validation at step boundaries |
| `agents/common/fallback_core.py`, `tools/suite_orchestrator.py`, `playwright.config.ts` | localhost fallback removed / env set explicitly |
| `ActionEngine.ts`, `fixtures/testFixture.ts` | host allow-list guard |
| `connectors/llm/{gemini,claude,bedrock,openai,ollama}.py`, `healing/agent.py` | token usage recording |
| Artifact readers/writers (semantic_map, healing, artifact_context, enrich_with_testdata, catalog_manager, export_scenarios, dom_scan, interactive_dom_scan, export_test_data ×2, review_queue) | v2 envelope via `contracts.artifacts` |
| Docs | README (manifest, Playwright table, execution, Safety Rails, Artifact Contracts, Benchmark, testing); agent.md/agent.json of ScriptGeneration, UIExecution, Orchestrator, TestData, Healing, SemanticMap; `aAprojectTemplate/project.yaml` |

No new agents were needed, so `tools/scaffold_agent.py` was not used. No existing guard was weakened:
locator validation, the healing tool surface and placeholder-negative dropping are untouched, and the
safety rails only remove things.

## 3. Tests

| Suite | Before Phase 0 | After Phase 0 |
|---|---|---|
| `python -m pytest tests/unit` | 762 passed | **1,471 passed, 0 failed** (count includes `test_every_existing_project_artifact_validates_or_migrates`, parametrised per artifact file on disk, so it grows with the generated (gitignored) benchmark project) |
| `npx vitest run` | 9 passed (1 file) | **36 passed (3 files)** |

New test files: `test_safety_action_classifier.py` (46 labelled names + step/URL rules),
`test_safety_policy.py`, `test_safety_plan_filter.py` (incl. the acceptance test through
`ScriptGenerationAgent.execute`), `test_base_url_resolution.py`, `test_artifact_contracts.py`
(round trips, every real project artifact, schema freshness, boundary enforcement),
`test_llm_usage_recorder.py`, `test_benchmark_scorer.py` (synthetic results), `test_bench_buggy_shop.py`
(each of the 22 bugs off/on), `test_bench_buggy_bot.py`, `test_locator_map_module_scoping.py`;
`baseUrl.test.ts`, `safety.test.ts`.

Existing tests changed on purpose: `test_ui_execution_agent_base_url.py::test_no_base_url_leaves_env_unset`
asserted the removed silent fallback — replaced by `test_no_base_url_fails_fast_instead_of_localhost`;
three UI-agent tests now pass an explicit `base_url`.

## 4. Acceptance criteria — proof

| Criterion | Command | Result |
|---|---|---|
| `python -m tools.benchmark.run --app buggy_shop` runs end to end and prints the metrics | `python -m tools.benchmark.run --app buggy_shop --label baseline_as_is` | exit 0 after 5,270 s; printed the KPI table (§5); wrote `benchmarks/results/2026-10-10_buggy_shop_baseline_as_is.{json,md}` |
| Baseline results are committed | `git log -- benchmarks/results` | pending your go-ahead to commit (results are in the working tree: `benchmarks/results/2026-10-10_buggy_shop_baseline_as_is.{json,md}`, `..._baseline_fixed.{json,md}`) |
| All existing project artifacts validate (or migrate) | `python -m contracts.artifacts.migrate --all` | `79 artifact file(s) in 23 project(s): migrates=73, valid=6; failing=0` before the benchmark project existed (81/24 with it, still `failing=0`); also `test_every_existing_project_artifact_validates_or_migrates` (parametrised per file) |
| A generated step that clicks "Delete account" is dropped when `allow_destructive: false` | `pytest tests/unit/test_safety_plan_filter.py -k acceptance` | `2 passed` — default project: the test is dropped, the spec has no `delete_account_btn`, `test_plans.json` records `dropped_for_safety`, `human_review_queue.json` has a `safety_drop` (environment `unspecified`); with `environment: local` + `allow_destructive: true` the step is kept |
| Required: classifier tests ≥ 30 labelled names | `pytest tests/unit/test_safety_action_classifier.py` | 46 labelled names (32 destructive, 16 safe) |
| Required: schema round-trip tests | `pytest tests/unit/test_artifact_contracts.py` | 120 passed |
| Required: scorer tests with synthetic results | `pytest tests/unit/test_benchmark_scorer.py` | 26 passed |

## 5. Benchmark — before (baseline)

`buggy_shop`, 22 seeded bugs, Gemini `gemini-3.6-flash`, full workflow per module, 2 bug-free runs,
1 run per bug, heal probe on.

| KPI | As-is (commit `48ee84d` + P0) | After locator-collision fix |
|---|---|---|
| Tests generated / executed | 40 / 40 | 53 / 53 |
| Requirement (AC) coverage | 0.0 % (0/27) | 0.0 % (0/27) |
| **Seeded-bug detection rate** | **0.0 % (0/22)** | **4.5 % (1/22)** |
| False-failure rate (bug-free build) | 70.0 % (28/40) | 28.3 % (15/53) |
| Flaky rate (2 bug-free runs) | 0.0 % | 0.0 % |
| Heal precision | n/a — nothing caught, so nothing to probe | n/a — 1 probe (BUG_08): healer changed 0 files, **0 wrong heals** |
| Generation runtime | 2,494 s (6 modules) | 2,992 s (6 modules) |
| Total runtime | 5,271 s | 7,471 s |
| LLM calls / tokens in / out | 203 / 960,853 / 497,276 | 223 / 1,094,320 / 439,939 |
| LLM cost | unpriced (`benchmarks/pricing.yaml` is empty, D6) | unpriced |

**Why the as-is numbers are zero.** 26 of the 28 bug-free failures were caused by a pre-existing
defect, not by test logic: every module's DOM scan numbers its locators from `LOC-0001`
(`tools/discovery/dom_scan.py:85` drops the registry's module prefix), and the project-wide
`locator_map.json` merge matched entries by that bare id and by identical locator value across
modules. Generating module M02 therefore overwrote module M01's `username`/`password` entries and
moved them to M02's Page class; M01's Page class disappeared from `pages.ts` entirely
(12 × "no Page class registered for module 'M01'", 14 × "'<key>' is not a property on the active Page
object"). Every multi-module project is affected (very likely including `AWS_Test`). With 70 % of the
suite red on the bug-free build, no test could catch a bug. With your approval, Phase 0 fixed the defect
(module-scoped merge, dedup, LLM reconcile and reverse index; ids unchanged, so existing maps and
artifacts stay valid) and recorded the second column. **Later phases compare against the fixed column.**

**What the fixed baseline says about current MTA (the real "before").**

- **Bug-free pass rate 72 % (38/53).** The 15 remaining false failures: 6 × upload tests whose fixture
  file TestData referenced but never created (`Upload fixture not found`), 9 × positive "smoke" tests whose
  LLM-chosen expected redirect/text does not match the app (e.g. "protected profile endpoint should redirect
  to login" — there is no profile page). Deterministic oracles (P5) and observed behaviour (P2.3) target
  exactly these.
- **Detection 1/22.** The single catch, BUG_08 (missing login-field label), is *incidental*: removing the
  `<label>` breaks the label-based locators of 5 login tests — no test asserts accessibility. None of the
  validation, boundary, authorization, session, state-machine, calculation, security or performance bugs is
  caught: the generated tests exercise happy paths and at most one shallow negative per scenario (G1, G2, G6).
- **Flakiness 0 %** across two bug-free runs; **0 wrong heals** — the healer correctly declined to patch the
  BUG_08 failures.
- **AC coverage 0 %** in both runs: no generated test carries an AC id (P1).
- Cost per full run ≈ 1.1 M input + 0.44 M output tokens of `gemini-3.6-flash` (223 calls); price it by
  filling `benchmarks/pricing.yaml` and running `python -m tools.benchmark.run --app buggy_shop --rescore benchmarks/results/<file>.json` (no new run needed).

## 6. Deviations from the plan

| # | Plan | What was done | Why |
|---|---|---|---|
| 1 | `environment` required | Missing → `unspecified`, gated like prod + warning | Requiring it would break every existing project (rule 3) |
| 2 | Destructive *steps* dropped | The whole *test* containing the step is dropped | Removing one click leaves later assertions on a state that never happens (false failures) |
| 3 | `schema_version: 2` on every artifact | Envelope for list/map artifacts; `locator_map.json` stays v1 (validated only) | `test_data` is a list and two artifacts are id-keyed maps; the TS runtime reads `locator_map.json` |
| 4 | "results" contract | Contract for MTA's own normalised run record (`reports/mta/*.execution_results.json`); Playwright JSON checked loosely | Playwright's JSON is a third-party format; healing scans `reports/json/` for the latest Playwright report |
| 5 | Flaky rate from Playwright | Measured by repeating the bug-free run (`--repeat`, default 2) | `retries: 0`, so Playwright never reports `flaky` (A2); retries are Phase 4.7 |
| 6 | Results file `benchmarks/results/<date>.json` | `<date>_<app>[_<label>].json` | Several apps/runs per day without overwriting |
| 7 | One baseline | Two (as-is, after the collision fix) + a minimal defect fix outside 0.1–0.7 | Approved by you after the as-is run proved the defect |
| 8 | Generation via `main.py --project` | `main.py --project … --module <id>` per module | Without `--module`, modular projects run BRD-only discovery (A13) |
| 9 | BRD per project | `brd.md` split per module by requirement section | Comprehension parses each module's `brd_file`; one shared BRD would make every module generate scenarios for the whole app |
| 10 | Public practice sites (optional) | Not added | Local apps only (destructive/security testing is local-only) |

## 7. Open issues (not fixed in Phase 0)

1. **Healing can change assertion values inside a spec block** (prompt-only guard; audit A7) → P6.
2. **Locator-map heals are not counted** in `tests_healed` (A10) → P6.9. The benchmark counts heals from file hashes instead.
3. **`reports/index.json` has two writers with conflicting schemas** (A12) → P11.
4. **Runtime host guard** covers top-level navigations and `navigate`; WebSocket/service-worker
   traffic and destructive clicks *at run time* (e.g. a healed spec) are not yet checked → P4.4 `safety` fixture.
5. **Healing token usage** is best effort (ADK event `usage_metadata`); LiteLLM providers may report nothing.
6. **Cost** is `null` until `benchmarks/pricing.yaml` has the account's Gemini prices (D6).
7. `tests/test_suite_orchestrator.py` (outside `tests/unit`) points at `application_assets/projects/AppEvolve`,
   which does not exist (the project lives under `myTestProjects/`); pre-existing, not touched.
8. Projects with an already-corrupted `locator_map.json` (multi-module projects generated before the fix)
   keep the wrong `_module_id`s until their locator map is rebuilt (delete `locator_map.json` and rerun
   script generation per module).
9. SemanticMapAgent's informational `playwright_expr` lookup is still by bare locator id (ScriptGeneration
   no longer relies on it); module-scope it in P2.

## 8. Recommendations for Phase 1

- Use the **fixed** baseline column as "before".
- AC coverage is 0 % in both baselines because v1 artifacts carry no AC ids — P1's `requirements.json`
  / `ac_ids` links will move this metric first; the scorer already prefers explicit `ac_ids`.
- Reuse `BrdIndex.grounded` (quote verifier) and add a deterministic atomicity check (A11).
- `buggy_shop/brd.md` already has 27 hand-written ACs — a ready start for `acs.yaml`.
