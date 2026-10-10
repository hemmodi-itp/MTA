# Phase 0 — Baseline, Benchmark and Safety Rails: Design

> Status: **DRAFT, awaiting approval.** No code has been changed yet.
> Inputs: `docs/MTA_IMPROVEMENT_PLAN.md` §Phase 0, and `docs/audit/current_state.md` (task 0.1, already written; it takes precedence over the plan).
> Scope: tasks 0.1–0.7 only. Nothing from Phase 1+ is included.

---

## 1. Summary

| Task | Deliverable | New agent? |
|---|---|---|
| 0.1 | `docs/audit/current_state.md` (done, part of this review) | — |
| 0.2 | `benchmarks/apps/buggy_shop/` (FastAPI app, 22 flag-gated bugs, `bugs.yaml`, BRD, MTA project template) · `benchmarks/agents/buggy_bot/` (rule-based chatbot, 4 flag-gated weaknesses) | No |
| 0.3 | `tools/benchmark/` (`run.py`, `score.py`, `app_server.py`, `report_md.py`) + LLM usage instrumentation | No |
| 0.4 | `benchmarks/results/2026-10-10_buggy_shop.{json,md}`, committed | — |
| 0.5 | `tools/safety/` (policy, action classifier, host guard) wired into the manifest, ScriptGeneration, UIExecution and the TS runtime | No |
| 0.6 | Remove every `localhost:3000` fallback; per-module base URL; fail fast | No |
| 0.7 | `contracts/artifacts/` (Pydantic v2 models, v1→v2 migrating loaders), `schemas/*.schema.json`, orchestrator boundary validation, migration CLI | No |

No new agents are created, so `tools/scaffold_agent.py` is not needed in Phase 0. All new logic lives in importable modules (`tools/safety/`, `tools/benchmark/`, `contracts/artifacts/`), which the Agent-Eval DAG can also import (plan principle 5).

---

## 2. Plan vs. reality: adjustments

| # | Plan says | Reality (audit) | Proposed adjustment |
|---|---|---|---|
| R1 | `environment` is **required** | No existing project has it; requiring it breaks every project (rule 3) | Missing → `environment: unspecified`, with a WARNING once per run. `unspecified` is treated like `prod` for gating (most restrictive), so destructive steps are dropped and probes refused. Projects keep running. |
| R2 | `allowed_hosts: [...]` | Projects are modular; hosts are already implied by `project.url`, `modules[].url`, `modules[].setup[].goto` and `auth.setup_url/wait_for_url` | Missing → derived from those URLs (logged). An explicit list replaces the derived one. An empty list with no URLs means "no navigation allowed". |
| R3 | "Destructive steps are dropped" | Dropping one click from the middle of a test leaves later steps asserting on a state that never happens (a false failure) | Drop the **whole test** that contains a destructive step and record `{test, step, matched_rule}`. The acceptance criterion ("a step that clicks *Delete account* is dropped") is met because the step goes with its test. |
| R4 | Remove the `localhost:3000` fallback (one place) | Five places: `playwright.config.ts`, `fallback_core.py:215`, `script_generation/agent.py:507`, `suite_orchestrator.py` (no env at all), and the first-`url:` regex | Fix all of them. Add **per-module base URL** to newly generated specs (`test.use({ baseURL })`) because one Playwright run currently shares one baseURL across modules (audit A1). |
| R5 | "Version every artifact (`schema_version: 2`)" | `test_data.json` is a list; `scenario_element_map` and `test_plans` are maps keyed by scenario id, so a `schema_version` key would be read as a scenario | Use a **v2 envelope** for the list/map artifacts (`{"schema_version":2,"artifact":"test_data","datasets":[...]}`). Dict artifacts gain the two keys in place. All in-repo readers move to one loader that accepts v1 and v2. Details in §7. |
| R6 | Artifacts in `comprehension/` | `test_comprehension/` now, `comprehension/` in old projects, both in `sauceLabs` | The loader resolves the current directory first, then the legacy one. |
| R7 | Contract list includes "results" | Raw Playwright JSON is a third-party format; no project has a results file | Contract the **normalised** run record MTA owns (`execution_results`: UIExecutionAgent's summary + per-test results, written next to the Playwright JSON). Validate the Playwright JSON only loosely (`stats` + `suites` present). |
| R8 | `locator_map.json` (not in the plan's list) | Read directly by the TS runtime (`LocatorManager.ts`) and repaired by healing | Do **not** envelope it in P0 (a TS change plus healing risk). Model it and validate it read-only, with no `schema_version` written. Revisit in P6. |
| R9 | Metric "flaky rate" | `retries: 0`, so Playwright never reports flaky (audit A2) | The scorer measures flakiness by running the bug-free suite **N times (default 2)**; a test is flaky if its outcome differs across runs. `playwright.config.ts` is **not** changed (that is P4.7). |
| R10 | Metric "LLM tokens and cost" | The default Gemini connector records nothing | Add `connectors/llm/usage.py` (a process-wide recorder plus an optional JSONL sink) and call it from every connector. Gemini reads `usage_metadata` from the final stream chunk. Cache hits are recorded as `cached: true, tokens: 0`. Cost = tokens × `benchmarks/pricing.yaml`; an unpriced model gives `cost: null` and is flagged, never guessed. ADK healing usage: best effort from ADK event `usage_metadata`; anything not captured is reported as "not captured". |
| R11 | Metric "heal precision" | Locator-map heals are uncounted (audit A10); "correct heal" needs ground truth | Defined in §5.3 using the seeded bugs as ground truth: a heal that turns a **bug-caught** test green while the bug is still enabled is a *wrong heal* (it hid a product defect). Heals are counted from file hashes before and after healing, not from the agent's own counters. |
| R12 | "Active security probes refused on prod" | MTA has no probe generator yet; the TestData LLM may still put XSS/SQLi strings in `negative` variants | P0 adds the policy plus a deterministic payload detector. **Decision D1** below covers whether it filters TestData output now. |

---

## 3. Task 0.2: Benchmark apps

### 3.1 `benchmarks/apps/buggy_shop/`

```
benchmarks/apps/buggy_shop/
├── app.py            FastAPI app (stdlib + fastapi/uvicorn only, both already dependencies)
├── bugs.py           flag registry: is_on("BUG_07") reads env BUG_07=1 (or BUGS=all)
├── store.py          in-memory store, seeded deterministically; reset on process start
├── templates.py      server-rendered HTML (f-strings + html.escape), small vanilla JS for client validation
├── bugs.yaml         ground truth: id, title, category, severity, affected_ac, how_detectable, flag
├── brd.md            BRD with explicit REQ-xx / AC-xx.y ids (the MTA input)
├── mta_project/project.yaml.tmpl   MTA project manifest (environment: local, safety on, modules, setup login)
└── README.md         how to run and how bugs are toggled
```

Pages and APIs: `/login`, `/logout`, `/products` (search, category filter, sort, pagination of 5), `/products/new` and `/products/{id}/edit` (validated CRUD form), `/products/{id}` (detail and delete), `/cart`, `/checkout`, `/orders/{id}`, `/upload` (CSV/PNG only, ≤ 1 MB), `/admin` (admin role only), `/help`. JSON mirrors live under `/api/...` so later API phases (P8) can reuse the app. Two users: `alice` (user) and `admin` (admin), with fixed local-only passwords. Port: `BENCH_PORT`, default **8765** (never 3000).

**Seeded bugs (22). All are off by default. `BUG_xx=1` enables one; `BUGS=all` enables all.**

| ID | Category | Bug | Affected AC (in `brd.md`) | How detectable |
|---|---|---|---|---|
| BUG_01 | validation_boundary | Name max 50 enforced as `< 50` (exactly 50 rejected) | AC-03.2 | UI BVA |
| BUG_02 | server_client_mismatch | Server accepts negative price that client JS rejects | AC-03.3 | API only |
| BUG_03 | calculation | Cart total truncates instead of rounding half-up | AC-05.2 | UI exact total |
| BUG_04 | authorization_idor | `/orders/{id}` has no ownership check | AC-06.2 | Role/URL tamper |
| BUG_05 | security_xss | Product description rendered unescaped (stored XSS) | AC-03.5 | Security probe |
| BUG_06 | navigation | Footer "Help" link → 404 | AC-08.1 | Link check |
| BUG_07 | error_handling | Search for `%` → HTTP 500 | AC-02.4 | Edge input |
| BUG_08 | accessibility | Login password field loses its `<label>` | AC-01.4 | a11y |
| BUG_09 | performance | `/products` sleeps 3.5 s | AC-02.6 | Timing budget |
| BUG_10 | state_machine | `/checkout` places an order with an empty cart | AC-05.4 | Invalid transition |
| BUG_11 | session | Logout doesn't invalidate the server session | AC-01.3 | Back/old cookie |
| BUG_12 | concurrency | Double-submit creates duplicate products | AC-03.6 | Double-click |
| BUG_13 | wrong_message | Wrong password shows "Unknown user" (enumeration) | AC-01.2 | Exact error text |
| BUG_14 | sorting | Sort by price not stable (ties reversed) | AC-02.3 | Order assertion |
| BUG_15 | pagination | Page 2 link drops the category filter | AC-02.5 | Filter + paginate |
| BUG_16 | authorization_role | `/admin` reachable by a regular user | AC-07.1 | Role matrix |
| BUG_17 | upload_validation | Server accepts `.exe` upload | AC-04.2 | Disallowed file |
| BUG_18 | required_validation | Empty name accepted (client and server) | AC-03.1 | Negative EP |
| BUG_19 | search | Search is case-sensitive | AC-02.2 | EP on case |
| BUG_20 | persistence | Delete shows success but item reappears on reload | AC-03.7 | Reload check |
| BUG_21 | validation_numeric | Cart quantity accepts 0 / negative | AC-05.1 | BVA |
| BUG_22 | business_rule | Discount code can be applied twice | AC-05.3 | Repeat action |

This covers every category the plan lists (off-by-one, server-accepts-client-rejects, rounding, IDOR, stored XSS, broken link, 500 on edge input, missing label, slow endpoint, state machine, session, double submit, wrong message, unstable sort, pagination losing the filter), plus 7 extras.

### 3.2 `benchmarks/agents/buggy_bot/`

A FastAPI `/chat` endpoint plus a minimal chat page, **rule-based (no LLM)**, with a small knowledge base (store hours, return policy, shipping) and a system prompt containing a canary `CANARY-SYS-…`. Weaknesses, all behind flags: `BOT_BUG_01` system-prompt leak, `BOT_BUG_02` follows injected instructions, `BOT_BUG_03` fabricates answers to unknown questions instead of "I don't know", `BOT_BUG_04` forgets turn-1 context. Ground truth is in `weaknesses.yaml`. **P0 only builds and unit-tests it; scoring it is P9.**

### 3.3 Public practice sites

Skipped. Local apps only, per the plan's preference (destructive and security tests are local-only).

---

## 4. Task 0.3: Scoring and runner

### 4.1 `python -m tools.benchmark.run --app buggy_shop [options]`

```
--app buggy_shop            (only app wired in P0)
--skip-generate             reuse the existing generated suite (no LLM spend)
--bugs BUG_01,BUG_07|all    which bugs to evaluate (default all)
--repeat 2                  bug-free repetitions for flakiness
--with-healing / --no-healing   (default: with) heal-precision measurement, see 5.3
--port 8765 --out benchmarks/results
```

Flow:

1. **Materialize** the MTA project `application_assets/projects/bench_buggy_shop/` from `mta_project/project.yaml.tmpl` and `brd.md`. The port is substituted. The folder is gitignored because it is generated output.
2. **Start** the app with all bugs off (`tools/benchmark/app_server.py` runs uvicorn in a subprocess, polls a health check, and tears down in `finally`).
3. **Generate** by running the current pipeline `python main.py --project bench_buggy_shop` (full workflow, unchanged). Wall-clock and LLM usage are recorded.
4. **Bug-free runs**: run the generated suite `--repeat` times with all flags off, via `UIExecutionAgent`.
5. **Per-bug runs**: for each bug, restart the app with only that flag on and run the suite again. A restart takes about 1 s and gives fresh in-memory state.
6. **Healing probe** (5.3).
7. **Score** with `tools/benchmark/score.py` → `benchmarks/results/<YYYY-MM-DD>_buggy_shop.json` + `.md`, and print the metrics table.

### 4.2 `score.py` is a pure function, no I/O inside the core

`score(run_record, bugs_truth, acs) -> Metrics`. Definitions:

| Metric | Definition |
|---|---|
| **AC coverage %** | ACs (the `AC-xx.y` ids parsed from `brd.md`; the full hand-labelled `acs.yaml` is P1's job) linked to ≥ 1 *executed* test ÷ all ACs. Links come from `ac_ids` on a test when present (v2 / P1+). For v1 artifacts the fallback is an exact AC-id match in the scenario's `traceability`/title. **The baseline is expected to be ≈ 0%, and the report says why ("v1 emits no AC links").** |
| **Seeded-bug detection rate** | Bug *caught* ⇔ ∃ test that **passed in every bug-free run** and **failed** in that bug's run. Rate = caught ÷ enabled. Tests that fail when bug-free cannot count as catches. |
| **False-failure rate** | Tests failing in the first bug-free run ÷ tests executed. |
| **Flaky rate** | Tests whose outcome differs across the `--repeat` bug-free runs ÷ tests executed. |
| **Heal precision** | 1 − wrong_heals ÷ heals_applied (5.3). `n/a` if 0 heals. |
| **Runtime** | Wall clock: generation, each execution, total. |
| **LLM tokens / cost** | From `connectors/llm/usage.py` JSONL: input/output tokens per model, call count, cache hits; cost from `pricing.yaml` or `null`. |

Each bug also gets a detail row (caught by which tests, or "not caught"), grouped by category and `how_detectable`, so the report shows *why* a bug was missed.

### 4.3 Heal-precision probe (`--with-healing`)

For each **caught** bug: copy the generated suite into a scratch copy, start the app with that bug on, and run `HealingAgent` against the failing results (on the scratch copy, so the real suite is never modified). A heal that makes the bug-catching test pass while the bug is still on is a **wrong heal**. Heals are counted by diffing spec and `locator_map.json` hashes. Cost: up to 22 healing loops × ≤ 3 iterations of Gemini Flash. **This is the main LLM spend** (decision D4).

### 4.4 LLM usage instrumentation (shared code)

`connectors/llm/usage.py`: `record(provider, model, input_tokens, output_tokens, cached=False)`. It keeps in-memory totals and appends to `$MTA_LLM_USAGE_LOG` when that is set. It is called from `gemini.py` (new), `claude.py`, `bedrock.py`, `openai.py` (beside their existing `[tokens]` logs), `ollama.py` if available, and healing ADK events (best effort). There is no behaviour change; it only observes.

---

## 5. Task 0.4: Baseline

Run `python -m tools.benchmark.run --app buggy_shop` once on current MTA, with the safety rails enabled but `bench_buggy_shop` configured `environment: local, allow_destructive: true, allow_security_probes: true`, so the baseline measures the *pre-v3 test engine* and not the new filters. Commit `benchmarks/results/2026-10-10_buggy_shop.{json,md}` and the KPI "Baseline" column values in the report. Expect low numbers. That is the point of a baseline.

Note: the baseline runs **after** 0.5–0.7 are implemented, because the benchmark runner needs the base-URL and usage fixes to produce trustworthy numbers. The bench project's flags make the new guards transparent for it. If you prefer a strictly pre-change baseline, I can run it first with a minimal patch set (usage instrumentation only). See decision D5.

---

## 6. Tasks 0.5 + 0.6: Safety rails and the base URL

### 6.1 New config (`project.yaml`)

```yaml
environment: local            # local | dev | staging | prod ; missing → "unspecified" (= prod for gating, WARN)
safety:
  allow_destructive: false     # default
  allow_security_probes: false # default
  allowed_hosts: []            # missing → derived from project/module/setup/auth URLs
```

- `tools/safety/policy.py`: `SafetyPolicy.from_project(project_yaml_dict)` (pydantic) with
  - `destructive_allowed` = `allow_destructive and environment in {local, dev, staging}`
  - `security_probes_allowed` = `allow_security_probes and environment in {local, dev, staging}`. **prod and unspecified always refuse**, whatever the flags say.
  - `host_allowed(url)`: exact host or `*.suffix` wildcard; scheme must be http(s); relative URLs are allowed.
- `tools/project_manifest.py` passes `environment` and `safety` through (currently unknown keys are dropped) and exposes `request["safety_policy"]`.
- `aAprojectTemplate/project.yaml` and the README gain the new block.

### 6.2 Action-safety classifier: `tools/safety/action_classifier.py`

A deterministic `classify(action, accessible_name, role, url_or_href) -> {destructive: bool, category, rule}`.

- Keyword/phrase rules come from data (`tools/safety/destructive_rules.yaml`): delete, remove, destroy, erase, purge, pay, purchase, buy now, place order, checkout/confirm order, send, transfer, withdraw, deactivate, close account, cancel subscription/order/plan, unsubscribe, reset (password/account/data), revoke, terminate.
- Word-boundary matching, with **safe-list overrides** for common false positives: "Cancel" alone (dialog dismiss), "Remove filter/sort", "Reset filters/form", "Send feedback?" (stays destructive: the plan lists *send*), "Delete" inside a search query value.
- URL/href rules: `/delete|/remove|/destroy|/pay|/checkout|action=delete`.
- Only **interaction** actions are classified (`click, doubleClick, pressKey Enter on a form, selectDropdown*, checkCheckbox, uploadFile` targets). `navigate` is classified by URL. `verify*` are never destructive.
- The accessible name comes from `locator_map.json` (`name` for role locators, `locator` text for label/text/placeholder) plus the locator key and description.
- It reuses and extends the Agent-Eval `_UNSAFE` vocabulary (`engines/runtime/actions.py:45`) without changing that module's behaviour.

**Wiring (generation time):** in `ScriptGenerationAgent.execute()`, just before `render_spec_from_plan`, which is the one choke point for all plan tiers. Steps inside referenced `flows.json` flows are also classified (they are currently unvalidated, audit §4). When not `destructive_allowed`, the containing test is dropped (R3) and the drop is recorded in:
- the plan's new `dropped_for_safety[]` field (saved to `test_plans.json`),
- `human_review_queue.json` (`kind: "destructive_step_dropped"`),
- a log line.

If every test of a scenario is dropped, the spec is skipped (the same path as the existing empty-plan skip).

### 6.3 Host allow-list (runtime)

- `ActionEngine.navigate(url)` checks the resolved absolute URL against `MTA_ALLOWED_HOSTS` (comma list, set by UIExecutionAgent from the policy). Outside the list, it throws `SafetyError: navigation to <host> is outside safety.allowed_hosts`, so **the step fails**.
- `testFixture.ts` adds a `page.on('framenavigated')` main-frame check. A redirect or click that lands the top-level page on a non-allowed host fails the test at the next action (ActionEngine checks a recorded violation before each action). Sub-resource requests (CDNs, analytics) are **not** blocked.
- When `MTA_ALLOWED_HOSTS` is unset (Playwright run by hand, old flows), there is no enforcement, but a console warning is printed. UIExecutionAgent always sets it.
- Generation time: a `navigate` step with an absolute URL to a non-allowed host is treated like a destructive step (its test is dropped and reported).

### 6.4 Security probes

`tools/safety/payloads.py`: a deterministic detector (`<script`, `javascript:`, `on\w+=`, `' OR '1'='1`, `UNION SELECT`, `; DROP`, `../`, `{{7*7}}`, …). P0 provides `policy.security_probes_allowed` and the detector. Whether TestData filters LLM-produced payloads is **decision D1**.

### 6.5 Base URL fail-fast (0.6)

| Place | Change |
|---|---|
| `playwright.config.ts` | Chain: `BASE_URL` → `project.yaml` resolved properly (top-level `project.url`, else the *only* module URL; several distinct module URLs and no `BASE_URL` → error listing them) → **throw** `Error("MTA: base URL unresolved — set BASE_URL or project.url / modules[].url")`. No default. |
| `ui_execution/agent.py` | Resolve: `request.url` → the module URL of the spec targets (`--module`, or the module dirs of the targets) → **fail fast** with `status: failed, blocking: True, error: "base URL unresolved"`. Multi-module runs set `BASE_URL` to a valid URL, and per-module correctness comes from the next row. |
| `spec_renderer.py` (new specs only) | Emit `test.use({ baseURL: process.env.MTA_BASE_URL_<MODULE> ?? '<module url>' })` when the module has a URL. Existing specs are untouched and still use the config baseURL. |
| `script_generation/agent.py:507, 912-923` | `_load_base_url` reads module URLs. If none, the prompt says "no base URL known; use `navigate` with no value". There is no localhost fallback. |
| `agents/common/fallback_core.py:215` | No URL → raise `MissingInputError` (FAIL_FAST route). The tier is off by default anyway. |
| `tools/suite_orchestrator.py` | Set `PW_PROJECT` + `BASE_URL` (resolved as above) + `--config`; otherwise fail with a clear message. |

---

## 7. Task 0.7: Artifact contracts

### 7.1 Package layout

```
contracts/artifacts/
├── __init__.py          load_artifact / save_artifact / validate_artifact / ARTIFACTS registry
├── base.py              ArtifactEnvelope (schema_version, artifact, generated_at?), Lenient base (extra="allow")
├── dom_elements.py      DomElementsV2 (+ Element, PageSection)
├── business_scenarios.py
├── test_data.py         TestDataV2 {datasets: [ScenarioTestData]}
├── scenario_element_map.py   {scenarios: {id: ...}}
├── test_plans.py        {plans: {id: Plan}}
├── test_suite.py
├── execution_results.py (normalised run record) + PlaywrightReportLoose
├── locator_map.py       read-only model (no envelope, R8)
├── migrations.py        v1→v2 per artifact (pure functions, registry by (artifact, from_version))
├── paths.py             artifact path resolution incl. test_comprehension/ ↔ comprehension/ (R6)
├── export_schemas.py    python -m contracts.artifacts.export_schemas → schemas/*.schema.json
└── migrate_cli.py       python -m contracts.artifacts.migrate --project X [--all] [--write] (dry-run default, .bak on write)
schemas/<artifact>.v2.schema.json   (exported, committed; a test fails if stale)
```

### 7.2 v2 shapes (all additive; the payload is unchanged inside)

| Artifact | v1 | v2 |
|---|---|---|
| dom_elements, business_scenarios, test_suite | dict | same dict + `"schema_version": 2, "artifact": "<name>"` |
| test_data | list | `{"schema_version":2,"artifact":"test_data","datasets":[…v1 list…]}` |
| scenario_element_map | `{sid: …}` | `{"schema_version":2,"artifact":"scenario_element_map","scenarios":{…}}` |
| test_plans | `{sid: …}` | `{"schema_version":2,"artifact":"test_plans","plans":{…}}` |
| execution_results | (new) | `{"schema_version":2,"artifact":"execution_results", run summary + results[]}` |

Models are **lenient on v1 variations** (`extra="allow"`, few required fields: only what downstream code actually indexes), so all existing projects validate. The fallback-core `test_data` shape (audit §3) is migrated into the canonical shape by the v1→v2 migration.

### 7.3 Readers and writers

- **Readers**: every in-repo reader of these files (about 18 modules, listed in `docs/audit/current_state.md` §8; full list confirmed by grep at implementation time) switches from `json.load` to `contracts.artifacts.load_payload(name, path)`. It returns **the same Python shape the call site uses today** (for example, a list for test_data), so the logic around each call site doesn't change. It accepts v1 or v2 and migrates in memory.
- **Writers**: the writer of each artifact uses `save_artifact(name, path, payload)`, which wraps it into v2 and writes atomically (tmp + `os.replace`).
- The TS runtime reads none of the enveloped files (it reads only `pages.ts` and `locator_map.json`, which keeps v1).
- On-disk upgrade is never automatic. Files become v2 when MTA next rewrites them, or explicitly via `migrate_cli --write`.

### 7.4 Orchestrator boundary validation

`agents/orchestrator/agent.py`: right after `_try_with_fallbacks` (`:191`) and on the two skip paths, validate the artifacts each step produces (a static map `step → [artifact names]`). Mode: `contracts.enforce` in `project.yaml`, `warn | block`, **default `warn`** (decision D3).
- `warn`: the step gets a `partial_reasons` entry and an error record, and the run continues.
- `block`: `status: failed, blocking: True`, which uses the existing stop path.
- The benchmark project uses `block`.

### 7.5 Migration plan

1. Ship the loaders (read v1 and v2) and switch all readers. There is no format change yet, so this is safe on its own.
2. Switch the writers to v2.
3. `migrate_cli --all` in dry-run over `application_assets/projects/*` and `myTestProjects/*` reports validate/migrate status per file. **Acceptance: 100% validate or migrate.** I will not run `--write` on your existing projects unless you ask.

---

## 8. Files to change (existing)

| File | Change |
|---|---|
| `tools/project_manifest.py` | pass `environment`, `safety`, `contracts` through; build `SafetyPolicy` |
| `agents/test_creation/script_generation/agent.py` | safety filter before render; module-aware `_load_base_url`; drop the localhost fallback; v2 writers/readers |
| `tools/test_creation/script_generator/spec_renderer.py` | `test.use({ baseURL })` per module (new specs) |
| `agents/test_execution/ui_execution/agent.py` | base-URL resolution + fail fast; `MTA_ALLOWED_HOSTS`; write `execution_results` v2 |
| `application_assets/_shared/runtime/ActionEngine.ts`, `fixtures/testFixture.ts` | host guard |
| `playwright.config.ts` | fail-fast baseURL; correct module URL parsing |
| `agents/common/fallback_core.py` | no localhost fallback |
| `tools/suite_orchestrator.py` | set env + config |
| `agents/orchestrator/agent.py` | boundary validation |
| `connectors/llm/{gemini,claude,bedrock,openai,ollama}.py` | usage recording (observe only) |
| Readers/writers of the six artifacts (about 18 modules) | central loader / saver |
| `tests/conftest.py` | add any new `PROJECTS_BASE` aliases to `_ALIASED_CONSTANTS` |
| `requirements-dev.txt` (new) | `pytest`, `httpx` (TestClient) |
| `.gitignore` | `application_assets/projects/bench_*/` |
| `README.md`, `aAprojectTemplate/project.yaml` | new config, safety, contracts, benchmark, corrected claims from the audit |
| `agent.md` / `agent.json` | ScriptGeneration, UIExecution, Orchestrator (+ TestData if D1 = yes) |

## 9. Tests (all new code gets unit tests)

| Area | Tests |
|---|---|
| Safety classifier | **≥ 40 labelled names** (positive: "Delete account", "Pay now", "Place order", "Transfer funds", "Unsubscribe", …; negative: "Cancel", "Remove filter", "Search", "Delete" as a search value, "Payment history" link, …), URL rules, role gating |
| Policy | env × flag matrix (prod/unspecified always refuse), host matching (wildcards, ports, relative URLs), derived `allowed_hosts` |
| ScriptGen wiring | a plan with a "Delete account" click → test dropped + review-queue entry; allowed when `allow_destructive: true` + `local`; still dropped on `prod`; flow steps are classified |
| Base URL | config resolution (vitest), UI fail-fast, module resolution, renderer `test.use` golden, suite_orchestrator env |
| TS runtime | vitest: navigate to a disallowed host throws; allowed passes; unset env warns only |
| Contracts | **round-trip** v1 → v2 → save → load for each artifact (synthetic + real fixtures copied from `application_assets`), schema export up to date, lenient variants (legacy dir, missing `content_hash`, AppEvolve outlier suite, fallback test_data shape), orchestrator warn/block |
| Scorer | synthetic run records: caught / not caught / fails-when-bug-free-doesn't-count / flaky / heal precision / unpriced cost / zero-tests edge cases |
| buggy_shop | each of the 22 flags flips its behaviour (FastAPI TestClient), and is off by default |
| buggy_bot | each of the 4 weaknesses flips with its flag |
| Usage recorder | totals, JSONL sink, cached calls |
| Regression | full existing suite stays green (762 pytest + 9 vitest at baseline) |

## 10. Risks

| Risk | Mitigation |
|---|---|
| Moving about 18 readers to the loader causes a regression | Step 1 (reader switch) lands before any format change; existing 762 tests plus new round-trip tests on real project files |
| External consumers (your scripts, notebooks) reading `test_data.json` as a list break once writers emit v2 | Called out in the README; the migration CLI can downgrade (`--to 1`) if needed; D2 lets you keep v1 writing |
| The destructive classifier drops legitimate tests on existing projects (e.g. "Remove from cart" in a shop under test) | The drop is reported (review queue + plan); per-project `allow_destructive: true` on non-prod restores it; safe-list overrides |
| Fail-fast base URL breaks someone's manual `npx playwright test` with no env | The error message says exactly what to set; this is the plan's intent (G19) |
| A baseline run on Gemini costs tokens and time (about 1 generation + up to 22 healing loops) | `--no-healing` and `--skip-generate` options; usage is reported |
| `framenavigated` guard flakiness (OAuth/SSO redirects to IdP hosts) | Auth hosts (`auth.setup_url`, `wait_for_url`, setup `goto`) are in the derived allow-list; explicit `allowed_hosts` can add IdP hosts |
| buggy_shop isn't representative | Its purpose is relative before/after measurement; the categories mirror the plan's list |

## 11. Decisions needed from you

| # | Question | My recommendation |
|---|---|---|
| **D1** | With `allow_security_probes: false` (the default), should TestData **drop** LLM-generated attack payloads (XSS/SQLi strings) from negative variants now? This changes generated data for existing projects. | **Yes**, it is the plan's default, and on prod or unspecified environments it is exactly what the rail is for. Drops are reported. |
| **D2** | Writers emit v2 envelopes by default? | **Yes** (all in-repo readers accept both). Alternative: `contracts.write_version: 1` per project. |
| **D3** | Boundary-validation default `warn` or `block`? | **`warn`** for existing projects; `block` for the benchmark and new projects from the template. |
| **D4** | Run the baseline **with** the healing probe (more Gemini spend, gives a heal-precision number)? | **Yes**: heal precision is a headline KPI and Gemini Flash is cheap. |
| **D5** | Baseline after the P0 changes (bench project configured so the new guards are transparent), or strictly before? | **After**: without the base-URL and usage fixes the numbers aren't trustworthy. |
| **D6** | Gemini pricing for the cost metric: I won't guess prices. Give me the $/Mtok you want used, or accept `cost: null (unpriced)` with token counts only. | Tokens now; you fill in `benchmarks/pricing.yaml`. |

Environment note: I installed `pytest` into `.venv` to establish the test baseline (it wasn't installed). It will be declared in a new `requirements-dev.txt`.
