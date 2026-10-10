# MTA — Current State Audit (README vs. code)

> **Phase 0.1 deliverable.** Audit date: 2026-10-10, at commit `48ee84d` ("Baseline before MTA v3 improvement plan").
> **Precedence:** where this document disagrees with `docs/MTA_IMPROVEMENT_PLAN.md`, **this document wins** for every later phase.
> Verdicts: **CONFIRMED** (code matches the README) · **CORRECTED** (code differs; the actual behaviour is stated) · **NOT FOUND** (claimed or assumed, but absent).
> Paths are repo-relative. `file:line` references are from the audit commit.

---

## 0. Test baseline at audit time

| Suite | Command | Result |
|---|---|---|
| Python unit | `.venv/Scripts/python -m pytest tests/unit -q` | **762 passed**, 8 warnings, 6m02s |
| TS unit | `npx vitest run` | **9 passed** (1 file: `application_assets/_shared/runtime/ActionEngine.test.ts`) |

`pytest` was **not installed** in `.venv` (nor declared in `requirements.txt` / `pyproject.toml`), even though the README says to run `pytest`. It was installed for this audit. `hypothesis` is not installed.

---

## 1. Project manifest (`project.yaml`)

| Claim | Verdict | Reality |
|---|---|---|
| Single `project.url` | **CORRECTED** | Real projects (and `aAprojectTemplate/project.yaml`) are **modular**: `modules[]: {id, name, url, brd_file, setup?, test_generation?}`. `project.url` is optional. |
| Manifest parsing | — | `tools/project_manifest.py:18-40`: plain `yaml.safe_load` dict. Only whitelisted keys are flattened into the request. **Unknown keys are silently discarded**, so new keys must be added here explicitly. No pydantic. |
| `environment` / `safety` / `allowed_hosts` | **NOT FOUND** | No project has them. Only the global `workflows/settings.yaml:1 environment: local` exists (display only, `main.py:118`). |
| Other direct readers of `project.yaml` (bypass the manifest) | — | `tools/config/test_generation_config.py:41` (good pattern: defaults → project → module), `healing/agent.py:215-220`, `script_generation/agent.py:913-915`, `tools/auth/auth_setup.py:38`, `tools/discovery/record_cli.py:35`, `playwright.config.ts:21-28` (regex). |
| `max_data_iterations: 1` (README example) | **CORRECTED** | The code default is **3** (`tools/config/test_generation_config.py:18-22`). |

## 2. Discovery and the DOM scanner (`tools/playwright_scanner.py` = PS)

| Claim | Verdict | Reality |
|---|---|---|
| goto `commit` → readyState poll 30 s → `networkidle` | **CONFIRMED** | PS:466-534. The networkidle wait is bounded to min(8 s, 40% of the remaining budget). The interactive scanner has no networkidle wait (`tools/interactive_scanner.py:425-429`). |
| Selector set `input, button, select, textarea, a, [role=combobox]` | **CONFIRMED** | PS:547-554. Identical in `interactive_scanner.py:215`. Hidden elements are kept (they are only flagged). |
| 12 attributes | **CONFIRMED** | PS:136-149. **No constraints are captured** (`required, maxlength, minlength, pattern, min, max, step, accept, readonly, aria-required`, select options: all absent). Note that `engines/runtime/discovery.py:104-106` (Agent-Eval) *does* capture required/readonly/select options. |
| Per-element round trips | **CONFIRMED** | About 19 Playwright round trips per element (PS:151-185, 302-303). There is no batched `page.evaluate`. |
| Locator priority `getByRole → getByLabel → getByPlaceholder → getByText → getByTestId → CSS` | **CORRECTED** | Actual scores (PS:628-726) are testid 100 > id 90 > label 80 > placeholder 70 > role 60 > name 50. `getByText` is never a candidate. CSS is used only when no candidate exists. `_rank_locator_candidates` hard-codes `unique=True, match_count=1` without querying the page (PS:733-741). |
| Role locator matching 2+ elements is demoted | **CONFIRMED** | PS:50-86 (−50, `unique=False`). Headless scan only; the interactive scanner does not demote. |
| 600 s safety ceiling + checkpoints | **CONFIRMED** | PS:478, 579-586. Atomic checkpoint every 10 s and after each selector (PS:21-39, 461, 606). Promoted on timeout (`agents/comprehension/discovery/agent.py:386-429`). |
| Frames / shadow DOM | **NOT FOUND** | Main frame only (`page.query_selector_all`). No `page.frames`. Open shadow roots are pierced only implicitly by Playwright CSS, but the hand-built CSS/XPath fallbacks walk `parentElement`/`document.querySelector` and break across shadow boundaries. |
| `dom_elements.json` merge-write; content-hash IDs | **CONFIRMED** (nuance) | `tools/discovery/dom_scan.py:103-146, 228-237`. The ID is a **persisted counter keyed by a content signature** (`tools/state/artifact_registry.py`), not the hash itself. The merge is skipped for multipage data. |
| Discovery modes BOTH / URL / BRD / none + `dom_synthesized` | **CONFIRMED** | `discovery/agent.py:127-148`. The fallback is gated by `agent_registry.yaml:49`; an `ns_http` hop is attempted first (`:616-645`). The docstring at `:190-191` is stale ("synthetic BRD via ComprehensionAgent"). |
| Output directory `comprehension/` | **CORRECTED** | Current code writes **`test_comprehension/`** (`discovery/agent.py:442, 654, 719`). Most existing projects still hold artifacts under legacy `comprehension/`; `sauceLabs` has both. |
| Destructive-action / host-allow-list logic | **NOT FOUND** | Only `_same_page` netloc comparison (PS:98). |

## 3. Test data (`agents/test_creation/testdata/`)

| Claim | Verdict | Reality |
|---|---|---|
| 10-variant taxonomy (positive, empty, whitespace, special_chars, sql_injection, …) | **NOT FOUND in the live path** | The prompt forces `variant_type` ∈ {`negative`, `boundary`} (`testdata/prompt.py:154`); the validator accepts only these two (`tools/test_creation/testdata/validate_test_data.py:5`). The taxonomy exists only in docs (`agent.md:16-27`, README). The LLM may still put XSS or SQLi strings inside a `negative` variant's values. |
| Caps enforced | **CORRECTED** | Enforced **in code only in TestData** (`generate_test_data.py:114-133`; every non-`boundary` variant counts as negative). ScriptGeneration only *prompts* the caps (`script_generation/prompt.py:326-332`) and never counts tests afterwards. The NS tier receives no caps. |
| Boundary default 255 | **CONFIRMED** (prompt only) | `testdata/prompt.py:59-60`. Hard-coded only in `fallback_core.py:146-147`. |
| Python fallback = 3 variants in the same format | **CORRECTED** | `fallback_core.py:129-151` writes **2** variants in a **different shape** (`negative_variants[].data`, no `iterations`) and overwrites `test_data.json` without merging. |
| `coverage_pct` signal | **CONFIRMED** | `testdata/agent.py:301-336` (LLM path only). |

## 4. Script generation (`agents/test_creation/script_generation/agent.py` = SG)

| Claim | Verdict | Reality |
|---|---|---|
| `ALLOWED_ACTIONS` mirrors `ActionEngine.ts` 1:1 | **CONFIRMED** | SG:71-79, 34 entries (33 methods + `useFlow`). Includes **`waitForTimeout`**. Runtime: `application_assets/_shared/runtime/ActionEngine.ts`. |
| Plan validation (allowed keys, dead keys excluded, flows) | **CONFIRMED** | `_validate_plan` SG:951-1018. **Gap: steps inside `flows.json` are never validated** (`spec_renderer.py:378`). |
| Positive tests scale per cluster | **CORRECTED** | Prompt-only (SG:501-502 → `prompt.py:311-314`). Not enforced. |
| `_drop_placeholder_negative_tests` | **CONFIRMED** | SG:1035-1071. No-op if any variant has a truthy `expected_error`. Otherwise drops `negative` tests whose every verify step has `value == ""`. |
| `_flag_action_locator_type_mismatches` | **CONFIRMED** | SG:1085-1133. |
| Live locator validation `count() == 1` | **CONFIRMED** | SG:628-675, 729. Unknown type, exceptions and unreachable pages count as "resolves" (fail-open). |
| `python_stub_fallback_enabled` off by default | **CONFIRMED** | `workflows/agent_registry.yaml:98-99`. |
| `status: new` for tier 0 | **CORRECTED** | Tier-1 (NS/alt-model) plan specs are **also** marked `degraded_fallback` (SG:320). |
| Destructive-action filtering | **NOT FOUND** | No classification anywhere in plan validation or the renderer. The single choke point covering every plan tier is `execute()` just before `render_spec_from_plan` (SG:~296). |
| Base URL for prompts | — | SG:507 passes `base_url or "http://localhost:3000"`. `_load_base_url` (SG:912-923) reads only top-level `url`, never `modules[].url`. The per-module `effective_url` reaches the spec only as a comment (`spec_renderer.py:330`). |

## 5. Execution (`agents/test_execution/ui_execution/agent.py` = UI) and `playwright.config.ts`

| Claim | Verdict | Reality |
|---|---|---|
| `retries: 1 (2 on CI)` | **CORRECTED** | `retries: 0` (`playwright.config.ts:48`; the comment above it is stale). Consequences: **`video`/`trace: on-first-retry` never record**, and **Playwright's `flaky` status can never occur**. "Flaky counted as pass" (UI:750) is therefore dead code today. |
| baseURL chain `BASE_URL → project.yaml → localhost:3000` | **CONFIRMED and worse than described** | `playwright.config.ts:15-35` takes the **first `url:` line anywhere in project.yaml** (regex), which is wrong for modular projects. UI sets `BASE_URL` only when `request["url"]` is truthy (UI:387-392), and `request["url"]` = `project.url` unless `--module` is given (`project_manifest.py:27, 64-66`). **`localhost:3000` is also where the MTA web app runs (README:648)**, so a miss silently tests MTA's own UI. |
| Other default-URL fallbacks | **NOT IN README** | `fallback_core.py:162,215`; SG:507; `tools/suite_orchestrator.py:249-264` (sets no `BASE_URL`/`PW_PROJECT`/`--config`); old generated raw-TS specs carry `process.env.BASE_URL \|\| '<url>'`. |
| Multi-module runs | **NOT IN README** | One Playwright invocation shares one `baseURL`. Specs whose `navigate` has no URL resolve against the wrong module URL unless the run is narrowed with `--module`. |
| Missing Chromium fails fast | **CORRECTED** | Detected **after** the run by string matching on stderr (UI:436-447), not by a pre-flight check. |
| Exit code 4 → warning, not success | **CORRECTED (partly)** | It warns, and synthesizes `failed` per spec when there are no results, but the returned `status` is still `"success"` (UI:515). |
| Headed 3× close → headless; browser-close → skipped | **CONFIRMED** | UI:489, 565-626, 65-75, 791-811. |
| `@playwright/test` version | — | `package.json ^1.49.0`; installed **1.61.0**. vitest 4.1.10. |
| `testIdAttribute: data-test` | **CONFIRMED** | `playwright.config.ts:64`. |
| `reports/index.json` | **NOT IN README** | **Two writers with conflicting schemas**: UI writes a list (UI:967-995); ReportingAgent writes a dict (`tools/test_execution/reports/index_manager.py:37-94`). Each run wipes the other's data. |

## 6. Healing (`agents/test_execution/healing/`)

| Claim | Verdict | Reality |
|---|---|---|
| Tool list | **CONFIRMED** | `tools.py:879-890`: `read_failure_report, propose_{locator,timing,compilation,test_data,navigation,fixture}_fix, apply_patch, run_tests, mark_not_healable`. |
| `apply_patch` structural validation, atomic write | **CONFIRMED** | `tools.py:259-268, 691-721`. **Block content is otherwise unrestricted.** The LLM *can* change `expect()` values inside a spec; only the prompt forbids it. `spec_file` is not path-sanitized. |
| Tool surface cannot write business_scenarios / workflows | **CONFIRMED** | Writes are limited to `.spec.ts`, `locator_map.json`, reports (via `run_tests`) and `test_suite.json`. |
| `repair_named_locator` heals every spec that shares the key | **CONFIRMED** | But this path **does not increment `tests_healed` or stamp `healed`** (`tools.py:490-505`), so heal counts are understated. |
| Requires `GOOGLE_API_KEY`; Gemini only | **CORRECTED** | The model follows `connectors.llm` via `connectors/adk_model.py:48-83` (Gemini native; aws/external/openai/ollama via LiteLLM). The key is needed only for `gemini` (the current setting). **No automatic fallback** between providers. |

## 7. Reporting, metrics, LLM accounting

| Item | Verdict | Reality |
|---|---|---|
| Run duration | Available | `workflow_status.total_duration_ms` + per-step `duration_ms` in the report (`tools/report_writer.py:161-334`). |
| Flaky rate | **NOT FOUND** | A per-result `flaky` bool exists but is always false (`retries: 0`). |
| Heal count | Partial | `specs_healed`, `tests_healed`, `rounds[]`, `not_healable[]`. Locator-map heals are not counted. |
| LLM tokens / cost | **NOT FOUND** | Only `[tokens]` log lines in `connectors/llm/{claude,bedrock,openai}.py`. **The default `gemini.py` connector records no usage.** ADK/LiteLLM healing usage is not captured. No cost computation, nothing persisted. Gemini also has an on-disk response cache (`call_policy.response_cache`), so a cached call costs 0 tokens. |

## 8. Orchestrator and artifacts

| Item | Reality |
|---|---|
| Step loop | `agents/orchestrator/agent.py:134-241`, strictly sequential. `full_workflow.yaml` uses `depends_on`, which the loader ignores. The legacy orchestrator uses only `always_run` (not `needs`/`critical`/`provides`). |
| Validation hook point | Directly after `result = self._try_with_fallbacks(step, request)` (`agent.py:191`). Setting `status=failed, blocking=True` triggers the existing stop path (`:212-223`). Two skip paths bypass it: cached discovery (`:146-157`) and execution "no new_additions" (`:164-188`). |
| `schema_version` on artifacts | **NOT FOUND**. Only `project_state.json` has it (string `"1.0"`, `tools/state/project_state_manager.py:21-25`). No `schemas/` folder; `model_json_schema` is unused. |
| Pydantic models | Exist but are not used as contracts: `tools/comprehension/models.py` (`BusinessScenario`), `tools/test_creation/testdata/models.py` (`ScenarioTestData`), `tools/discovery/models.py`, `tools/artifact_generator/models.py`. `contracts/` holds only dataclasses (`RequestModel`, `WorkflowState`). |
| Central read/write helpers | None used consistently. Most agents call raw `open`+`json.dump` and hard-code `os.path.join(_ASSETS_BASE, safe, ...)`. `tools/context/artifact_context.py` is the best reader plug-in point but swallows all errors. |

**On-disk shapes (v1):**

| Artifact | Top level | Notes / variations seen in `application_assets/` |
|---|---|---|
| `dom_elements.json` | dict `{url, project, elements[]}` | Interactive variant adds `scan_mode, total_element_count, pages[]`; elements gain `page_id, blast_radius_*`. Some files have empty `elements`. |
| `business_scenarios.json` | dict `{project, total_scenarios, scenarios[], modules?}` | Older files lack `content_hash` / `module_id`. ID schemes `BS-001`, `M01_BS_001`, `SC-001`, `GEN_BS_001` (sometimes mixed). |
| `test_data.json` | **list** of `{testdata_id, scenario_id, scenario_title, actor, positive_dataset[], negative_variants[]}` | The fallback writes a different shape (see §3). |
| `scenario_element_map.json` | **dict keyed by scenario id** | Consistent. Shape is LLM-decided and not validated. |
| `test_plans.json` | **dict keyed by scenario id** `{tests[], missing_actions, missing_locators}` | Consistent. |
| `test_suite.json` | dict `{specs[], project, updated_at, total_scenarios, new_additions}` | Older files lack `generation_mode` / `module_id`. Outlier: `myTestProjects/AppEvolve` uses `{…, modules, suites, specs}` with `module` instead of `module_id`. |
| `locator_map.json` | dict keyed by locator key | **Read by the TS runtime** (`LocatorManager.ts:42`). |
| Execution results | Playwright JSON at `test_execution/reports/json/{ts}_results.json` | **No project in the repo currently has any results file.** |

## 9. Agent-Evaluation DAG

| Claim | Verdict | Notes |
|---|---|---|
| DAG fields `needs/critical/timeout_s/provides` | **CONFIRMED** | `workflows/workflow_loader.py:14-97`, `api/pipeline.py:193-272`. `provides` is checked only at load; runtime overwrites only warn. |
| 18 steps | **CONFIRMED** | |
| runtime_discovery bounds 12 pages / 40 visits / 10 min | **CONFIRMED** | `engines/runtime/discovery.py:31-33`. Login only when credentials exist. **Reusable crawler**: `discover(...)` at `:150` has no DB dependencies. No transition graph (links only). |
| Quote-verified requirements, atomic criteria | **CONFIRMED / CORRECTED** | Quote verifier `BrdIndex.grounded(quote, min_ratio=0.85)` (`tools/agent_eval/brd_source.py:167`). Criteria grounding is token overlap only (`:194-216`). **"Atomic" is a prompt instruction only.** IDs: `REQ-01`, `AC-01.1`. |
| Deterministic checks + quote-grounded judge | **CONFIRMED** | `engines/validation/output.py:45, 208-236`. |
| AI-agent test categories | **Mostly NOT FOUND** | Variant labels include security/hallucination/out_of_scope but are used only when the BRD states them. Injection/leakage exist as judge rubric text only (`live_agent_execution/prompt.py:61-63`). **No** consistency/repeat-run, multi-turn memory or tool-use tests. G17 is confirmed. |
| Private-target refusal | **CONFIRMED (caveats)** | `tools/agent_eval/net_guard.py` (`check_target`, `is_allowed_url`, `install_browser_guard`, `same_origin`). These are reusable pure functions for an `allowed_hosts` check. Caveats: WebSocket/service-worker requests are not covered; DNS rebinding window. |
| Destructive guard | **PARTIAL** | `engines/runtime/actions.py:45` `_UNSAFE` (logout / delete account / deactivate / unsubscribe) and `discovery.py:46-48` `_SKIP_LINK`. Pay/purchase/checkout/generic delete are not covered. |
| Scoring `compliance-v1.2` | **CONFIRMED** | `engines/scoring/v1.py:35`. |
| Token / cost accounting, schema_version | **NOT FOUND** | |

## 10. Discrepancies that change later phases

| # | Plan assumption | Reality | Consequence |
|---|---|---|---|
| A1 | Single project URL | Modular manifest; per-module URLs; one shared `baseURL` per Playwright run | P0.6 must resolve **per module**; P2 crawl seeds = all module URLs |
| A2 | Flaky counted as pass (G11) | `retries: 0`, so flaky never occurs; trace/video never recorded | P4.7 must first turn retries on; the P0 benchmark measures flakiness by **repeated clean runs** |
| A3 | 10-variant taxonomy exists | Only `negative`/`boundary` | P3 builds the taxonomy from scratch (as data) |
| A4 | Healing is Gemini-only | Provider follows `connectors.llm`; no automatic fallback | P6.8 = add a fallback chain, not "add LiteLLM" |
| A5 | Artifacts under `comprehension/` | `test_comprehension/` now; legacy `comprehension/` in most projects | Every artifact loader resolves both |
| A6 | `test_data.json` etc. can simply gain `schema_version` | `test_data.json` is a list; `scenario_element_map`/`test_plans` are id-keyed maps | A v2 **envelope** is needed (see Phase 0 design) |
| A7 | Healing can't change expected values | It can, inside a spec block (prompt-only guard) | P6 must add a structural assertion-diff guard |
| A8 | Token cost is measurable | The default Gemini connector records nothing | P0 adds usage instrumentation |
| A9 | Caps are enforced | Prompt-only in ScriptGeneration | P3 budget selection must be enforced in code |
| A10 | Heal counts are reliable | Locator-map heals are uncounted | P0 scorer counts heals from the audit of changed files; P6.9 fixes it at source |
| A11 | Atomic ACs exist in Agent-Eval | Prompt-only atomicity | P1.1 "reuse atomic-criteria logic" means reusing the prompt + quote verifier, then adding a deterministic atomicity check |
| A13 | `python main.py --project X` runs the whole pipeline (found while recording the P0 baseline) | For a **modular** project with no `project.url`, `request["url"]` is empty unless `--module` is given, so DiscoveryAgent runs **BRD-only**: no DOM scan, no locators, and execution is skipped. In practice modular projects must be run module by module (`--module M01` …) | The benchmark runner generates per module; P2's crawl should seed from every module URL so a whole-project run discovers the UI |
| A12 | `reports/index.json` is a reliable run index | Two writers clobber each other | The P0 scorer reads per-run files; the fix is scheduled for P11 (logged as an open issue) |
