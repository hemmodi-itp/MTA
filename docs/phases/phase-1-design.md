# Phase 1 — Requirements and Traceability Backbone: Design

> Status: **DRAFT, awaiting approval.** No code has been changed yet.
> Inputs: `docs/MTA_IMPROVEMENT_PLAN.md` §Phase 1, `docs/audit/current_state.md` (it takes precedence over the plan), `docs/phases/phase-0-report.md`.
> Code verified at HEAD `2bf04b6` ("phase 0 completed"), with the uncommitted Phase 0 working tree as it is on disk. Unit-test baseline on that tree: `python -m pytest tests/unit` → **1,472 passed**.
> Scope: Phase 1 tasks **1.1–1.4** only. Nothing from Phase 2 or later is included (see D0 on the scope wording).

---

## 1. Summary

| Task | Deliverable | New agent? |
|---|---|---|
| 1.1 | `test_comprehension/requirements.json`: `REQ` → atomic `AC`. Each AC carries testability (with a reason), priority P0–P3, risk tags, a verified `source_quote` or `source: dom_inferred`, and an atomicity flag. `business_scenarios.json` scenarios gain `ac_ids`. | No. ComprehensionAgent calls the shared module. |
| 1.2 | `test_creation/traceability.json`: AC → test-case ids → spec file + test title → latest result → defect ids (reserved). Rebuilt after generation, updated after every Playwright run, and finalised and rendered by ReportingAgent, including "ACs with zero tests and why". | No |
| 1.3 | Every newly rendered test carries a Playwright details object with `tag` (`@P1`, `@negative`, `@REQ-01`, `@AC-01.2`, `@smoke`/`@regression`) and `annotation` (`ac`, `tc`, `scenario`). Results capture tags and annotations. A healing guard keeps the details object intact. | No |
| 1.4 | `tools/requirements/` shared package: quote verifier, requirement normaliser, explicit-ID parser, atomicity check, classifiers, linking, traceability. The legacy pipeline and the Agent-Eval DAG (`brd_builder`) both import it. | No |
| AC | `benchmarks/apps/buggy_shop/acs.yaml` (hand-labelled ground truth) plus an AC-extraction recall tool | — |

No new agent is needed. All logic is library code called from existing agents, so `tools/scaffold_agent.py` is not used. Everything new is behind `requirements.enabled` in `project.yaml` (D1). With the flag off, generated artifacts and specs are byte-identical to today's output (§9).

---

## 2. Plan vs. reality: adjustments

| # | Plan says | Reality (verified) | Proposed adjustment |
|---|---|---|---|
| R1 | Output to `comprehension/requirements.json` | Comprehension writes to `test_comprehension/`; old projects use `comprehension/` (audit A5). `contracts/artifacts/paths.py` already resolves both. | Write to `test_comprehension/requirements.json`. Register it in `paths._COMPREHENSION` so readers find either location. |
| R2 | IDs `REQ-###` → `AC-###.#` | Real BRDs often declare their own IDs. buggy_shop uses `REQ-01` / `AC-01.1`; the benchmark scorer and `brd.md` depend on them. Agent-Eval renumbers by position (`REQ-01`) and loses the document's IDs. The legacy pipeline restarts `REQ-001` per document, so IDs collide across modules. | **The document's own IDs are canonical when present** (testers recognise them). BRDs with no IDs get generated `REQ-###` / `AC-###.#` from a project-wide, content-keyed, persisted counter, stable across re-runs and unique across modules. If two modules declare the same ID with different text, the second gets a generated ID and keeps `doc_id` plus a warning. |
| R3 | "Atomic ACs, reuse Agent-Eval's atomic-criteria logic" | In Agent-Eval, atomicity is a prompt instruction only (audit A11; `brd_builder/prompt.py:133`). Nothing checks it. BRD ACs are often compound (buggy_shop AC-03.2 "50 accepted **and** 51 rejected"; AC-04.2 has two rules). | Reuse the prompt rule, then add a **deterministic atomicity check** (`atomicity.py`: multiple outcome clauses, multiple quoted messages, `;`/"and" between clauses that each have their own outcome verb). A non-atomic AC that the LLM splits gets child ACs **`AC-03.2.1`, `AC-03.2.2`**. Tests link to the children (leaves). The parent counts as covered only when all children are. The format keeps the scorer regex `\bAC-\d+\.\d+\b` rolling a child up to its parent. If a flagged AC is not split, it stays with `atomic: false` and a warning in the file and in the report. |
| R4 | "Quote-verified with Agent-Eval's verifier" | `BrdIndex.grounded(quote, min_ratio=0.85)` (`tools/agent_eval/brd_source.py:167`) does an exact normalised substring match first, then a difflib window ≥ 0.85. `support()` is token overlap (≥ 0.7) for restated criteria. Pure Python, no DB/LLM. | Move `BrdIndex` into `tools/requirements/brd_index.py` and re-export it from `brd_source.py` (same object, so Agent-Eval is unchanged). Each AC records `quote_match: exact \| fuzzy \| none` and `quote_verified: bool`. A BRD-sourced AC whose quote fails `grounded()` is **rejected** and listed in `rejected[]` with reason `quote_not_found`; it is never silently kept. This gives the plan's three required cases: exact → verified; paraphrased (below 0.85) → not verified (reported, with `support` recorded); fabricated → rejected. |
| R5 | Per AC: `testability` (ui \| api \| non_functional \| manual_only \| not_testable + reason), `priority` P0–P3, `risk_tags` | Agent-Eval has `verifiability` (static/runtime/both/non_technical) and `priority` high/medium/low, and no risk tags (agent B §4). The legacy pipeline has none of these. | New fields defined in `tools/requirements/models.py`. Priority and risk are **deterministic first** (§4.4). Testability is the LLM's interpretation, validated against the enum, with a mandatory reason for `manual_only`/`not_testable`. A deterministic heuristic is used when the LLM is unavailable. Mapping helpers convert to and from Agent-Eval's vocabulary. |
| R6 | "Keep `business_scenarios.json`, link each scenario to its `ac_ids`" | `tools/comprehension/models.BusinessScenario` uses pydantic's default `extra='ignore'`, so `ac_ids` would be **silently dropped** in three places: the field-by-field build (`generate_business_scenarios.py:121-136`), the merge round-trip (`export_scenarios.py:141,148`) and both `load_scenarios.py` loaders. The scenario prompt never sees ACs. | Add `ac_ids: List[str]` and `ac_link_source` to `BusinessScenario` and map them through all four places. They are serialised **only when non-empty**, so flag-off files are unchanged. Linking: the scenario prompt gets the module's ACs (flag on only) and returns `ac_ids`. A deterministic validator drops unknown IDs. A deterministic similarity linker fills scenarios the LLM left unlinked, as well as DOM- and flow-synthesised scenarios (`SC-…`, `SC-FLOW-…`). |
| R7 | Traceability: AC → `test_case_ids` | There is no `test_cases.json` until P3. A test today is an entry in `test_plans.json[sid].tests[]`, with no ID. Results know only the scenario ID, parsed from the filename (`ui_execution/agent.py:777`). | Assign each plan test a stable **`tc_id`** at generation through `ArtifactRegistry` (content-keyed, giving e.g. `M01_TC_003`). It is stored in `test_plans.json` and rendered as the `tc` annotation. P3's `test_cases.json` takes these IDs over or re-keys them. |
| R8 | Traceability: → `defect ids` | No defect concept exists until P6 (triage) / P11 (defect reports). Healing's `not_healable` is not a defect classification. | `defect_ids: []` is **reserved** in the schema and always empty in P1. The latest failure's first error line is recorded as `last_failure` so the report can still show *why* a test is red. |
| R9 | "Update it after generation and after every execution" | Executions happen in `UIExecutionAgent`, including healing's `run_tests` re-runs and the benchmark's `run_suite`. All of them go through `_write_execution_results` (`ui_execution/agent.py:780`). **Skipped tests are recorded as `failed`** (`:882`). The Playwright JSON's `tags`/`annotations` are ignored. | Hook the update in `_write_execution_results`, which covers every run. The parser also records `pw_status` (raw Playwright status), `tags`, `annotations` and `tc_id`, all additive. Traceability uses `pw_status`, so a skipped test is `skipped`, not `failed`. UIExecution's own pass/fail mapping is **not** changed in P1 (D6). |
| R10 | Playwright tags/annotations, e.g. `@bva` | The renderer appends `@smoke`/`@regression` to the **title** (`spec_renderer.py:245,290-300`). Playwright 1.61.0 is installed and supports `test(title, details, body)`, and the shared fixture keeps that signature. Healing's block regex (`healing/tools.py:211`) needs the whole `test(` header **on one line**, and healing can rewrite the header (stripping tags) with nothing checking it. Techniques (`@bva`) only exist from P3. | Render the details object **on the header line**. Move `@smoke`/`@regression` from the title into `tag`. Prefix the title with the test's primary AC (as in the plan example). Use type tags (`@positive`/`@negative`/`@boundary`) instead of techniques until P3. Add a **healing header guard**: when the old block's header has a details object, `apply_patch` rejects a new block whose header lacks an identical details object. The title may change, for example to `test.skip`. The healing prompt gains one line telling the model to keep the object. This only adds a guard and weakens none. |
| R11 | "The report lists every AC with zero tests, with a reason (`not_testable`, `budget`, `missing_locator`, …)" | ReportingAgent builds JSON + HTML from in-memory step outputs (`reports/report_writer.py:161-334`, `html_report.py`). The reasons exist but are scattered: `missing_locators`/`missing_actions` and `dropped_for_safety` in `test_plans.json`; the placeholder-negative and locator-type-mismatch drops are only logged; **TestData's caps drop variants silently** (`generate_test_data.py:114-125`). | Record drops where they happen, additively: plan `dropped_tests[]` for the placeholder and type-mismatch filters, and test-data `capped_variants` counts. Reasons are then computed deterministically (§5.3). Add a "Requirements traceability" section to the JSON and HTML reports. |
| R12 | "Every generated test maps to at least one AC" | A test can only link to ACs that exist and that its scenario links to. Forcing a link would fabricate traceability. | The LLM picks each test's ACs from its scenario's ACs (validated as a subset). If none is valid, the deterministic linker tries. Otherwise the test **inherits** the scenario's ACs (`link: inherited`). A test whose scenario has no AC at all is listed in `unlinked_tests[]` in the file and the report, never hidden. See D2. |
| R13 | (implicit) existing projects get requirements | When `dom_elements.json` + scenarios are cached, the orchestrator **skips discovery** (`orchestrator/agent.py:146-157`), so turning the flag on would not produce requirements for an existing project. | Add a standalone CLI `python -m tools.requirements.build --project X [--module M01]` (extraction + scenario linking, no DOM scan). The cached-discovery path logs a one-line hint when the flag is on and `requirements.json` is missing. |
| R14 | Tag `@REQ-012` / test id formats | The benchmark identifies a test by `"{spec_file}::{test_title}"` (`tools/benchmark/run.py:93`). New titles drop the ` @smoke` suffix and gain the AC prefix. | Fine within one benchmark run (all runs use the same suite). Before/after comparisons are by metric, not by test ID. Noted in the report. |
| R15 | "Opus writes the ground-truth list in `acs.yaml`" | The buggy_shop BRD declares all 27 ACs with IDs, so an explicit-ID parser gets 100% trivially. | `acs.yaml` holds the 27 BRD ACs plus their hand-labelled atomic sub-checks, testability, priority and risk tags. Recall is measured **twice**: on the normal BRD, and on an **ID-stripped** copy where the LLM path must find the ACs itself. Matching is by text (quote grounded in the ground-truth AC, or support ≥ 0.7), not by ID. Both runs must reach ≥ 90%. |

---

## 3. Configuration

```yaml
# project.yaml — new optional block
requirements:
  enabled: false        # P1 master switch: requirements.json, scenario ac_ids, tc_ids,
                        # test tags/annotations, traceability.json, report section
  # doc_id_patterns:    # optional override of the document-ID regexes (defaults below)
  #   requirement: '^#{2,4}\s*(REQ-\d+)\b'
  #   criterion:   '^\s*[-*]\s*(AC-\d+(?:\.\d+)+)\s*:'
```

- `tools/project_manifest.py` gets `resolve_requirements_config(raw)` and `flat["requirements"] = …`, the same pattern as `contracts` in Phase 0.
- `tools/requirements/config.py` exposes `requirements_enabled(project)` for agents that read `project.yaml` directly (ScriptGeneration, UIExecution, Reporting), following `tools/config/test_generation_config.py`.
- Defaults: off for existing projects (plan principle 4). **On** in `aAprojectTemplate/project.yaml` and the buggy_shop template (D1).

---

## 4. Task 1.1: `requirements.json`

### 4.1 Where it runs

Inside `ComprehensionAgent`, per BRD (modular: per module; flat: per document). It runs after `parse_document` and **before** scenario generation, so scenarios can be linked as they are generated:

```
parse_document ─► tools.requirements.extract_requirements(doc_text, llm, module, ...)   [NEW, flag on]
              ─► extract_requirements (legacy, unchanged) ─► generate_business_scenarios (+ AC list in prompt when flag on)
              ─► link_scenarios (deterministic validation + similarity backfill) ─► export_scenarios
              ─► save requirements.json (per-module upsert)
```

URL-only mode already writes `synthetic_brd.md` from the DOM. Requirements extracted from it get `source: dom_inferred`, `quote_verified` against the synthetic text, and confidence ≤ 0.6. BRD-only and BOTH modes extract from the real BRD.

### 4.2 Extraction pipeline (`tools/requirements/extract.py`)

1. **Explicit parse (deterministic).** `explicit.parse(text)` finds document-declared requirements and criteria (headings and bullets matching `doc_id_patterns`). Their `source_quote` is the exact line, so they are verified by construction.
2. **One LLM call per BRD** (interpretation only). The prompt (`tools/requirements/prompts.py`) is adapted from Agent-Eval's `REQUIREMENT_EXTRACTION_PROMPT` and keeps its rules for verbatim quotes, atomicity and "never invent thresholds". The BRD is fenced as untrusted (`FencedTemplate`). If explicit items exist, the model gets them and is asked to **classify** them (testability + reason, priority if inferable, risk tags), **split** non-atomic ones, and **add** requirements the document states without IDs. Output is validated by a pydantic model (`LlmRequirementsResponse`). The Gemini JSON schema is passed through `tools.agent_eval.llm_json.generate_json`. If validation fails, the call is retried once with the validation errors; if it fails again, step 6's heuristics are used.
3. **Merge (deterministic).** Explicit items are authoritative for ID, text and quote. LLM classifications are attached by ID. LLM additions get generated IDs (R2). **The LLM can add, never drop:** an explicit AC with no LLM classification is kept with `classification_source: "heuristic"`.
4. **Quote verification.** `BrdIndex.grounded(source_quote)` → `quote_match`. A failing LLM-added item goes to `rejected[]` (`quote_not_found`). Split children must each satisfy `criterion_grounded` against the parent text, or the split is discarded and the parent is kept as `atomic: false`.
5. **Atomicity check.** `atomicity.check(statement)` → `{atomic, issues[]}`, applied to every leaf.
6. **Classification.** `classify.py` (§4.4).
7. **Persist.** A per-module upsert into `test_comprehension/requirements.json` via `save_artifact("requirements", …)` (atomic write, v2 envelope).

If the LLM is unavailable, `extract_requirements` never raises into comprehension: the explicit items plus heuristic classification are written with `status: "degraded"` and a `limitations[]` entry. With no explicit IDs and no LLM, it writes an empty module entry with `status: "failed"` plus the reason. Scenario generation continues as today in both cases.

### 4.3 Schema (`requirements`, v2 envelope, `kind: dict`)

```jsonc
{
  "schema_version": 2, "artifact": "requirements", "project": "bench_buggy_shop",
  "updated_at": "2026-10-11T09:00:00Z",
  "modules": { "M01": { "brd_file": "brd_M01.md", "status": "ok|degraded|failed", "limitations": [] } },
  "requirements": [{
    "id": "REQ-01", "doc_id": "REQ-01", "module_id": "M01", "title": "Authentication and session",
    "description": "…", "source": "brd|dom_inferred", "source_quote": "…", "quote_match": "exact",
    "acceptance_criteria": [{
      "id": "AC-01.2", "doc_id": "AC-01.2", "parent_id": null, "children": [],
      "statement": "Given a wrong password … shows exactly \"Invalid username or password\" …",
      "source": "brd", "source_quote": "…", "quote_match": "exact", "quote_verified": true, "support": 1.0,
      "atomic": true, "atomicity_issues": [],
      "testability": "ui", "testability_reason": "observable on the login page",
      "priority": "P1", "priority_source": "llm|brd|rule|default",
      "risk_tags": ["auth"], "classification_source": "llm|heuristic",
      "confidence": 0.95
    }]
  }],
  "rejected": [{ "module_id": "M01", "statement": "…", "reason": "quote_not_found" }],
  "warnings": [{ "id": "AC-03.2", "kind": "non_atomic_not_split" }]
}
```

Pydantic models live in `tools/requirements/models.py`, which is the single source of truth. `contracts/artifacts/models.py` registers a lenient envelope model `RequirementsV2` that reuses them. JSON Schema is exported to `schemas/requirements.v2.schema.json`.

### 4.4 Deterministic classification (`classify.py` + `risk_rules.yaml`)

| Field | Rule (in order) |
|---|---|
| `risk_tags` | Union of (a) the keyword catalog `risk_rules.yaml` (data, word-boundary matching over statement + requirement title): `auth` (login, password, session, token, role, permission, access denied, 401/403…), `payment` (pay, checkout, order, price, total, discount, invoice, card…), `data-loss` (delete, remove, overwrite, persist, permanently…), `PII` (email, phone, address, date of birth, SSN…), `compliance` (GDPR, HIPAA, WCAG, accessib…, audit, retention…); and (b) the LLM's tags filtered to that enum. |
| `priority` | BRD-stated `P0–P3` → that value. MoSCoW: Must → P1, Should → P2, Could → P3, Won't → P3 + `testability: not_testable` ("out of scope: Won't"). Otherwise the LLM's P0–P3. Otherwise P2. Then **floor rule**: `auth`/`payment`/`data-loss` → at least P1. `priority_source` is recorded. Agent-Eval mapping: P0/P1 ↔ high, P2 ↔ medium, P3 ↔ low. |
| `testability` | The LLM's value (enum-validated; a reason is required for `manual_only`/`not_testable`). Heuristic fallback: `/api/`, "HTTP 4xx/5xx", JSON → `api`; "within N seconds", accessible/WCAG/label, latency → `non_functional`; "manually", "visually inspect", "legal review" → `manual_only`; otherwise `ui`. |

### 4.5 Scenario ↔ AC linking (`linking.py`)

- **LLM (flag on):** `SCENARIO_GENERATION_PROMPT` gets one extra block, the module's leaf ACs (`id: statement`), plus one output field, `ac_ids`.
- **Validation:** unknown or other-module IDs are dropped, and the drop is logged in `warnings`. A parent ID is expanded to its children.
- **Backfill:** scenarios with no valid IDs are scored against leaf ACs of the same module. The score is `BrdIndex(scenario_text).support(ac.statement)` plus a requirement-ID hint from `traceability[].requirement_id`. IDs scoring ≥ 0.5 are linked, with `ac_link_source: "similarity"`.
- **No flag-off effect:** the prompt, the model fields and the output are unchanged when the flag is off.

---

## 5. Task 1.2: `traceability.json`

### 5.1 Schema (`traceability`, v2 envelope, `kind: dict`, at `test_creation/traceability.json`)

```jsonc
{
  "schema_version": 2, "artifact": "traceability", "project": "…", "updated_at": "…",
  "acs": {
    "AC-01.2": { "req_id": "REQ-01", "module_id": "M01", "priority": "P1", "testability": "ui",
                 "risk_tags": ["auth"], "parent_id": null,
                 "tc_ids": ["M01_TC_002"], "status": "covered|partial|not_covered",
                 "result": "passed|failed|skipped|not_run|mixed",
                 "uncovered_reason": null, "defect_ids": [] }
  },
  "tests": {
    "M01_TC_002": { "scenario_id": "M01_BS_002", "spec_file": "M01/test_M01_BS_002_….spec.ts",
                    "test_title": "AC-01.2 wrong password shows generic error", "type": "negative",
                    "ac_ids": ["AC-01.2"], "link": "direct|similarity|inherited|legacy",
                    "latest_result": { "status": "failed", "pw_status": "unexpected", "run": "20261011T…",
                                       "at": "…", "last_failure": "expect(locator).toHaveText …" },
                    "defect_ids": [] }
  },
  "unlinked_tests": ["M03_TC_011"],
  "summary": { "acs_total": 31, "acs_testable": 27, "acs_covered": 22, "coverage_pct": 81.5,
               "by_reason": { "not_supported:non_functional": 2, "missing_locator": 1 } }
}
```

### 5.2 Update points (pure functions in `tools/requirements/traceability.py`, thin I/O wrappers)

| When | Where | What |
|---|---|---|
| After generation | End of `ScriptGenerationAgent.execute` (beside `update_catalog`) | `rebuild(project)`: a deterministic rebuild from `requirements.json` + `business_scenarios.json` + `test_plans.json` + `test_suite.json`. It is idempotent. Previous `latest_result`s are kept by `tc_id`. |
| After every Playwright run | `UIExecutionAgent._write_execution_results` (also covers healing re-runs and benchmark runs) | `apply_results(project, execution_results)`: match each result to a test by its `tc` annotation, then by (spec_file, test title) via `test_plans`, then (legacy specs) by spec → scenario with `link: legacy`. Updates `latest_result` and recomputes AC `result`/`status`. |
| Final | `ReportingAgent` (always runs, sees the post-healing state) | `rebuild` + `apply_results(latest)`, then the summary goes into the JSON/HTML report. |

All three are no-ops when the flag is off or `requirements.json` is absent. Each is wrapped so that a traceability failure becomes a logged `partial_reasons` entry and never fails the step.

### 5.3 "Zero tests" reasons (deterministic, first match wins)

1. `not_testable` / `manual_only`: from testability (the reason is shown).
2. `not_supported:api` / `not_supported:non_functional`: MTA generates no API tests (P8) or non-functional tests (P7) yet.
3. `no_url`: BRD-only discovery (no locators).
4. `module_not_generated`: no spec exists for any scenario of the AC's module.
5. `no_scenario`: no scenario links to the AC.
6. `dropped_for_safety`, `missing_locator`, `missing_action`, `placeholder_negative_dropped`, `locator_type_mismatch`: the linked scenario's plan recorded that drop (R11).
7. `budget`: TestData capped variants for a linked scenario (`capped_variants > 0`) and the AC has no test.
8. `generation_failed`: the scenario has no spec and the suite entry is missing or failed.
9. `no_test_targets_ac`: the scenario has tests, but none links to this AC.

---

## 6. Task 1.3: tags and annotations

**Renderer** (`spec_renderer._render_test`). With the flag on and a test that has `ac_ids`/`tc_id`, the output is (one line, R10):

```ts
  test("AC-01.2 wrong password shows generic error", { tag: ["@P1", "@negative", "@regression", "@REQ-01", "@AC-01.2"], annotation: [{ type: "ac", description: "AC-01.2" }, { type: "tc", description: "M01_TC_002" }, { type: "scenario", description: "M01_BS_002" }] }, async ({ action }) => {
```

- **Priority tag:** the highest priority among the linked ACs.
- **Type tags:** the type tag plus the existing `@smoke`/`@regression` mapping. These move from the title into `tag`, so `--grep @smoke` keeps working.
- **Requirement/AC tags:** one tag per linked REQ and AC. An inherited link gets `{ type: "ac_link", description: "inherited" }`.
- **Title prefix:** the primary AC, unless the name already contains it.
- **Flag off, or a plan without links:** byte-identical to today.

**Python fallback spec** (`fallback_core.fallback_generate_script`, off by default): puts the same details on its `test.describe(…, { tag, annotation }, () => {`, so the stubs inherit them.

**Plan fields:** `PlanTest` gains `tc_id`, `ac_ids` and `ac_link` (lenient model, no contract break). The ScriptGeneration prompt (flag on only) shows the scenario's ACs and asks for `ac_ids` per test. `_validate_plan` keeps the subset check. Invalid IDs are dropped, never fail the plan.

**Execution:** `_parse_playwright_json` adds `pw_status`, `tags`, `annotations`, `tc_id` and `ac_ids` (from annotations) to each result. These are additive, and `_write_execution_results` already spreads `{**r}`.

**Healing guard** (`healing/tools.py::_apply_patch`): if the old block's header contains a details object, the new block's header must contain the identical object, otherwise the result is `{"ok": false, "error": "patch must keep the test's { tag, annotation } object unchanged"}`. Old specs without details are unaffected. A prompt line is added saying the same.

---

## 7. Task 1.4: shared module `tools/requirements/`

```
tools/requirements/
├── __init__.py          public API: extract_requirements, link_scenarios, rebuild_traceability, apply_results
├── models.py            pydantic: AcceptanceCriterion, Requirement, RequirementsDoc, LlmRequirementsResponse,
│                        Traceability models; enums Testability, Priority, RiskTag
├── brd_index.py         BrdIndex + _norm/_stem (MOVED from tools/agent_eval/brd_source.py, re-exported there)
├── normalize.py         normalize_requirements + _criterion/_origin (MOVED from brd_builder/agent.py, re-exported there)
├── explicit.py          document-declared REQ/AC parser (deterministic)
├── atomicity.py         deterministic atomicity check
├── classify.py          risk tags, priority rules, testability validation + heuristic, Agent-Eval mappings
├── risk_rules.yaml      risk keyword catalog (data)
├── ids.py               stable ID allocation (project-wide, content-keyed; ArtifactRegistry gains a global sequence)
├── prompts.py           legacy-pipeline extraction prompt (adapted from Agent-Eval's)
├── extract.py           explicit + LLM + merge + verify + atomicity + classify → RequirementsDoc
├── linking.py           scenario↔AC and test↔AC validation and similarity backfill
├── traceability.py      rebuild / apply_results / uncovered reasons / summary (pure) + I/O wrappers
├── config.py            requirements_enabled(project), doc_id_patterns
└── build.py             CLI: python -m tools.requirements.build --project X [--module M01]
```

How each pipeline uses it:

- **Legacy pipeline:** ComprehensionAgent, ScriptGeneration, UIExecution, Reporting and the benchmark call the public API.
- **Agent-Eval DAG:** `brd_builder` imports `BrdIndex` and `normalize_requirements` from the shared package (moved code, identical behaviour). The names stay importable from their old locations, so existing tests and monkeypatch targets keep working.
- **Agent-Eval enrichment (D3, additive only):** `normalize_requirements` adds `risk_tags`, `priority_p` (P0–P3) and `atomic`/`atomicity_issues` to each requirement or criterion. DB persistence ignores unknown keys (agent B §3), and scoring is unchanged.
- **Not shared (on purpose):** Agent-Eval's extraction **prompt** and its `verifiability`/`oracle_hint` vocabulary. They feed DB columns and scoring, and changing them is outside P1.

---

## 8. Task: `acs.yaml` and the recall measurement

`benchmarks/apps/buggy_shop/acs.yaml`, hand-labelled from `brd.md`:

```yaml
- id: AC-03.2
  req: REQ-03
  module: M03
  statement: "Name must be 1–50 characters; …"
  atomic: false
  checks: ["name of exactly 50 characters is accepted", "51 or more is rejected with 'Name must be at most 50 characters'"]
  testability: ui
  priority: P1
  risk_tags: []
```

There are 27 entries, one per BRD AC.

**Recall tool:** `python -m tools.benchmark.ac_recall --app buggy_shop [--strip-ids]`.

- Runs `extract_requirements` per module BRD with the configured LLM.
- **Match rule:** an extracted leaf AC matches a ground-truth AC when its `source_quote` is grounded in the ground-truth statement, or `support ≥ 0.7`. IDs are ignored when `--strip-ids` is set.
- **Report:** recall plus, informatively (not gated), testability, priority and risk-tag agreement.
- **Acceptance:** ≥ 90% in both modes.

The scorer is also updated:

- **AC coverage:** `tools/benchmark/run.py::test_inventory` reads per-test `ac_ids` from `traceability.json` (fallback: scenario `ac_ids`, then the existing regex).
- **New metric:** `ac_extraction_recall` is added to the result JSON when an `acs.yaml` exists.

---

## 9. Backward compatibility and migration

| Item | Flag off | Flag on |
|---|---|---|
| `requirements.json`, `traceability.json` | not written | new artifacts, registered contracts; absent file = feature off |
| `business_scenarios.json` | unchanged (`ac_ids` only serialised when non-empty) | scenarios gain `ac_ids`, `ac_link_source` (lenient contract already allows extra keys) |
| `test_plans.json` | unchanged | tests gain `tc_id`, `ac_ids`, `ac_link`; plans gain `dropped_tests[]` |
| `test_data.json` | `capped_variants` added (count only, additive) | same |
| Specs | byte-identical renderer output | details object, AC title prefix |
| `execution_results` | gains `pw_status`, `tags`, `annotations` (additive; harmless) | + `tc_id`, `ac_ids` |
| Existing (v1) specs | unaffected | traced with `link: legacy` (spec → scenario → its ACs) until regenerated |
| Agent-Eval | moved code re-exported; outputs + D3's additive fields | n/a (flag is legacy-pipeline only) |

There is no on-disk migration. `python -m contracts.artifacts.migrate --all` must still report `failing=0`, and the new artifacts are included when present. Schemas are re-exported, and `test_exported_schemas_are_up_to_date` guards them. To turn the feature on for an existing project: set `requirements.enabled: true`, run `python -m tools.requirements.build --project X`, then regenerate scripts (or `--force-rediscover`).

---

## 10. Files to change (existing)

| File | Change |
|---|---|
| `tools/agent_eval/brd_source.py` | `BrdIndex`, `_norm`, `_stem` moved out; re-exported |
| `agents/comprehension/brd_builder/agent.py` (+ `agent.md`, `agent.json`) | import `normalize_requirements` from the shared package (re-exported); D3 enrichment |
| `agents/comprehension/comprehension_agent/agent.py` (+ md/json) | call `extract_requirements` + `link_scenarios`, save `requirements.json` (flag on) |
| `tools/comprehension/models.py`, `generate_business_scenarios.py`, `prompts.py`, `export_scenarios.py`, `tools/testdata/load_scenarios.py`, `tools/test_creation/testdata/load_scenarios.py` | `ac_ids` field end to end; AC block in the scenario prompt (flag on) |
| `agents/comprehension/discovery/agent.py` | cached-path hint (R13); pass the flag; synthetic/flow scenarios get linked |
| `tools/test_creation/testdata/generate_test_data.py` (+ TestData md/json) | record `capped_variants` |
| `agents/test_creation/script_generation/agent.py`, `prompt.py` (+ md/json) | `tc_id` allocation, per-test `ac_ids` (prompt + validation), `dropped_tests[]`, traceability rebuild |
| `tools/test_creation/script_generator/spec_renderer.py` | details object + title prefix (flag on) |
| `agents/common/fallback_core.py` | describe-level details |
| `agents/test_execution/ui_execution/agent.py` (+ md/json) | parse `pw_status`/tags/annotations; traceability `apply_results` |
| `agents/test_execution/healing/tools.py`, `prompt.py` (+ md/json) | header-details guard |
| `agents/test_execution/reporting/agent.py` (+ md/json), `tools/test_execution/reports/report_writer.py`, `html_report.py` | traceability section |
| `contracts/artifacts/models.py`, `registry.py`, `paths.py`, `boundary.py`; `schemas/` | register `requirements` (comprehension dir; steps `discovery`, `comprehension`) and `traceability` (test_creation; steps `script_generation`, `ui_execution`, `healing`, `reporting`) |
| `tools/state/artifact_registry.py` | global (non-module) ID sequence for REQ/AC |
| `tools/project_manifest.py` | `requirements` block |
| `tools/benchmark/run.py`, `score.py`, `apps.py` | per-test `ac_ids` from traceability; `ac_extraction_recall` |
| `benchmarks/apps/buggy_shop/mta_project/project.yaml.tmpl`, `application_assets/projects/aAprojectTemplate/project.yaml` | `requirements.enabled: true` |
| `README.md` | Requirements & Traceability section, manifest, data model/artifact chain, report, test tags |

**New:** `tools/requirements/*` (§7), `tools/benchmark/ac_recall.py`, `benchmarks/apps/buggy_shop/acs.yaml`, tests (§11).

---

## 11. Tests

| Area | Tests (pytest unless noted) |
|---|---|
| AC extraction schema (required) | pydantic models accept or reject: enums, mandatory reason for `manual_only`/`not_testable`, child-ID format, P0–P3, risk enum; LLM response validation + one repair retry + heuristic fallback (fake LLM); round trip through `save_artifact`/`load_payload`; exported schema is fresh |
| Quote verifier (required) | exact → `exact`; whitespace/markdown/punctuation variants → `exact`; small transcription diff → `fuzzy`; **paraphrased** → not verified (`support` recorded); **fabricated** → rejected and listed; < 12 chars; Agent-Eval's existing grounding tests still pass via the re-export |
| Explicit parser | buggy_shop BRD → 8 REQ / 27 AC with exact quotes; custom patterns; no IDs → empty |
| Atomicity | ≥ 15 labelled statements (AC-03.2, AC-04.2 flagged; single-outcome ACs not flagged) |
| Classification | risk catalog hits and safe misses; priority precedence (BRD > MoSCoW > LLM > default) + floor rule; testability heuristics |
| Merge | the LLM can't drop explicit ACs; additions get stable generated IDs; cross-module ID collision → re-keyed + `doc_id` + warning; split children validated |
| IDs | same content → same ID across runs; new content → next number; project-wide uniqueness |
| Linking | unknown IDs dropped; parent → children; similarity backfill; flow/DOM scenarios linked; flag off → no `ac_ids` key written |
| Traceability update (required) | rebuild from synthetic artifacts; result matching by `tc` annotation, then title, then legacy; `pw_status: skipped` → `skipped`; preserved results on rebuild; every reason in §5.3; partial parent coverage; summary maths; no-op when the flag is off |
| Renderer | golden strings: details on one line, AC title prefix, tags, annotations; flag off → byte-identical to today (existing assertions kept) |
| Healing guard | patch dropping or changing the details object → rejected; same object with changed body → accepted; `test.skip` with the same object → accepted; old specs unaffected; the existing regex still extracts a block with a details object |
| UI parsing | Playwright JSON fixture with tags/annotations → result fields |
| Reporting | JSON + HTML section with zero-test reasons and unlinked tests |
| Benchmark | scorer prefers traceability `ac_ids`; recall matcher (ID and text modes) with synthetic extractions |
| Contracts | the two new artifacts in `ARTIFACTS`, `STEP_ARTIFACTS`, `iter_project_artifacts`; `migrate --all` still `failing=0` |
| TS | vitest: none needed (no runtime change). One Playwright `--list` check confirms the rendered details parse (`npx playwright test --list --grep @AC-01.2` on a generated benchmark spec) |
| Regression | full `tests/unit` (baseline 1,472) + `npx vitest run` (baseline 36) stay green |

---

## 12. Acceptance criteria — how each will be proven

| Criterion | Proof planned |
|---|---|
| Every generated test maps to at least one AC | After the benchmark generation: a command over `traceability.json` printing `unlinked_tests == []` and the link-source mix (direct / similarity / inherited); plus a unit test |
| The report lists every AC with zero tests, with a reason | HTML/JSON report of the benchmark run, with the section excerpted; unit tests for each reason |
| ≥ 90% of hand-labelled ACs extracted on buggy_shop | `python -m tools.benchmark.ac_recall --app buggy_shop` and `… --strip-ids`, both ≥ 90% |
| Required tests | named test files + pytest output |
| Benchmark before/after | `python -m tools.benchmark.run --app buggy_shop --label phase1` (full regeneration with the flag on) vs the Phase 0 **fixed** baseline. Expected movement: AC coverage from 0% up. Detection and false-failure should not regress, since P1 adds no new test logic. |

---

## 13. Risks

| Risk | Mitigation |
|---|---|
| Prompt changes to scenario generation / ScriptGeneration change outputs | Flag-gated; flag-off output proven byte-identical by tests; benchmark measures the effect |
| One extra LLM call per module BRD (cost/time) | ~6 calls on buggy_shop (≈ 3% of 223); reported in the benchmark token numbers; explicit-ID BRDs still need it only for classification |
| LLM mislinks ACs (inflated coverage) | Subset validation; link source recorded and shown in the report; `inherited` shown separately from `direct`; the 90% recall test is text-matched |
| Moving `BrdIndex`/`normalize_requirements` breaks Agent-Eval | Pure move + re-export; Agent-Eval tests (`test_brd_builder_grounding.py`, `test_mta_evaluation_core.py`, `test_trace_static_runtime.py`, …) must stay green unchanged |
| Healing guard blocks legitimate patches | Only for specs with a details object; clear error text the healing LLM can act on; the prompt tells the model up front |
| A multi-line details object would break healing's block regex | Renderer always emits it on the header line; a unit test asserts `_extract_test_block` on rendered output |
| ID instability across re-runs | Document IDs are stable; generated IDs are content-keyed and persisted |
| Benchmark run time (~2 h, ~1.1 M input tokens) | Run once at the end; `--skip-generate` is not valid here because generation changes |

---

## 14. Decisions needed from you

| # | Question | My recommendation |
|---|---|---|
| **D0** | Your message says "tasks 0.1 to 0.7", but those are Phase 0's tasks (done). Phase 1's tasks are **1.1–1.4**. Implement 1.1–1.4? | **Yes, 1.1–1.4** (this design). |
| **D1** | `requirements.enabled` default | **Off** for existing projects (plan principle 4, opt-in until validated); **on** in the project template and the buggy_shop benchmark. |
| **D2** | A test whose own AC link can't be established: inherit its scenario's ACs (`link: inherited`, shown separately), or leave it unlinked? | **Inherit** (the test exercises that scenario), clearly marked. Unlinked only when the scenario itself has no AC. Both counts are reported. |
| **D3** | Add the deterministic enrichment (`risk_tags`, `priority_p`, atomicity flags) to Agent-Eval's requirement rows now? | **Yes**: additive only, no scoring or DB change, and it starts closing G18. |
| **D4** | Run the full benchmark (regeneration with the flag on, ~2 h + Gemini spend) for the before/after numbers? | **Yes**: tags and AC links only appear on regenerated specs. |
| **D5** | Prefix new test titles with the primary AC ID (as in the plan example)? | **Yes** (flag on only). |
| **D6** | UIExecution maps Playwright `skipped` to `failed`. Fix that now, or only record `pw_status` and let traceability use it? | **Record `pw_status` only** in P1. Changing pass/fail counts is a behaviour change better made with P4.7's flaky/skip handling. Logged as an open issue. |
