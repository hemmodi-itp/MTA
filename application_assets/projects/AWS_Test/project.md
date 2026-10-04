# Project Overview

This file describes the project this folder represents. It is a companion to `project.yaml`, which holds the machine-readable configuration consumed by the agent pipeline at runtime.

## What belongs here

- A brief description of the application under test: what it does, who uses it, and the base URL
- A list of modules in scope (one module = one page or feature area)
- Any project-specific constraints (auth requirements, environment dependencies, known flaky areas)
- References to the input BRD files in `inputs/` that seed the pipeline

---

## Project folder structure

```
YourProjectName/
├── project.yaml                        ← machine-readable config (you edit this)
├── project.md                          ← this file (you edit this)
│
├── inputs/                             ← BRD documents (you create these)
│   ├── input_BRD.md                    ← optional master BRD (project overview)
│   ├── module_01_name.md               ← BRD for module 1
│   └── module_02_name.md               ← BRD for module 2
│
├── comprehension/                      ← discovery + BRD-comprehension outputs (pipeline writes these)
│   ├── dom_elements.json               ← locator source of truth for the last-scanned module/page
│   ├── dom_intents.json                ← intents inferred from the DOM scan
│   ├── business_scenarios.json         ← ALL scenarios, flat, across every module (each tagged module_id)
│   ├── business_scenarios.md           ← human-readable rendering of the same
│   ├── synthetic_brd.md                ← only written when a module has a URL but no BRD file
│   ├── run_summary.json                ← last discovery run's URL/mode/element/scenario counts
│   └── modules/                        ← per-module DOM-scan outputs when run with --module
│       └── M01/
│           ├── dom_elements.json
│           └── dom_intents.json
│
├── test_creation/                       ← generated test artifacts (pipeline writes these)
│   ├── intents.yaml                    ← DOM intents translated into a scriptable action list
│   ├── scenario_element_map.json       ← each scenario → its 3-7 relevant DOM elements (SemanticMapAgent)
│   ├── test_suite.json                 ← single source of truth: every spec, its status, last_run/last_result
│   ├── test_catalog.csv                ← human-readable, always-current view of test_suite.json + business_scenarios.json
│   ├── test_catalog.md                 ← same, as a markdown table — refreshed after every execution run
│   ├── test_data/
│   │   ├── test_data.json              ← positive + negative/boundary variants per scenario
│   │   └── test_data.md
│   └── test_scripts/
│       ├── test_SC-001_some_scenario.spec.ts   ← module-less scenarios sit flat here
│       ├── M01/                        ← every M01 spec, grouped
│       │   └── test_M01_BS_001_....spec.ts
│       └── M02/                        ← every M02 spec, grouped
│
├── test_suites/                        ← named suite definitions (you edit these, optional)
│   ├── smoke_suite.json                ← 1 positive scenario per module
│   ├── regression_suite.json           ← all scenarios across all modules
│   └── module_01_suite.json            ← focused run for M01 only
│
└── execution/                          ← test run outputs (pipeline writes these)
    └── reports/
        ├── index.json                  ← report index (newest first)
        ├── json/{timestamp}_{project}.json    ← full structured report (also a per-run raw Playwright JSON)
        └── html/{timestamp}_{project}.html    ← the report to open in a browser
```

---

## The pipeline — 7 steps, one full run

`python main.py --project YourProjectName [--module M01]` runs all 7 steps of `full_workflow` in order:

| Step | Agent | What it does |
|------|-------|---------------|
| 1. discovery | DiscoveryAgent (+ ComprehensionAgent) | Scans the module's live URL for DOM elements; reads the module's BRD file and extracts requirements/rules/actors/workflows, then generates business scenarios |
| 2. testdata | TestDataAgent | Generates realistic positive data + 1 representative negative/boundary variant per scenario |
| 3. semantic_map | SemanticMapAgent | Maps each scenario to its 3-7 relevant DOM elements, in one LLM call |
| 4. script_generation | ScriptGenerationAgent | Writes one `.spec.ts` per scenario, using ONLY the mapped elements' locators — validated live against the real page before being trusted (see `test_creation/artifacts.md`) |
| 5. ui_execution | UIExecutionAgent | Runs `npx playwright test` against the generated specs |
| 6. healing | HealingAgent | **Runs automatically after every execution** — re-locates and patches failing `test()` blocks whose root cause is a stale locator (skips real app/network/auth failures, which aren't locator problems) |
| 7. reporting | ReportingAgent | Aggregates real results into HTML + JSON reports, stamps `last_result`/`last_run` back onto `test_suite.json`, and refreshes `test_catalog.csv`/`.md` — always runs, even if an earlier step failed or the run was interrupted partway through |

---

## Modular workflow — how to build coverage module by module

```
Step 1: Define modules in project.yaml
        Add one entry per page/feature area with its URL and BRD file path.
        If the page needs a login first, add a `setup:` sequence (see project.yaml).

Step 2: Write the BRD for module 1
        Create inputs/module_01_name.md — describe the page structure,
        actors, business rules, user workflows, and test scenarios.
        (See inputs/module_01_name.md in this template — the more structure,
        the better ComprehensionAgent's extraction.)

Step 3: Run the full pipeline for module 1 only
        python main.py --project YourProjectName --module M01 --force-rediscover

Step 4: Review generated scripts and the run's report
        Check test_scripts/M01/ — confirm the generated scenarios match your BRD.
        Open the HTML report under test_execution/reports/html/ for real pass/fail + errors.
        Check test_creation/test_catalog.md — every M01 scenario should show a
        last_result now.

Step 5: Re-run execution only if you tweak a script by hand or want to retry
        python main.py --project YourProjectName --module M01 --force-execute

Step 6: (Optional) Wire module 1 scenarios into a named suite
        Edit test_suites/smoke_suite.json → add M01 scenario IDs from
        test_creation/test_suite.json (spec_id field).
        Run it with: python main.py --project YourProjectName --suite smoke

Step 7: Repeat steps 2-6 for M02, M03, ...

Step 8: Run everything once all modules are covered
        python main.py --project YourProjectName
```

---

## Useful CLI flags (`main.py`)

| Flag | What it does |
|------|--------------|
| `--project NAME` | Required — the project folder under `application_assets/projects/` |
| `--module M01` | Scope the run to a single module |
| `--force-rediscover` | Re-run discovery even if the target page's content is unchanged |
| `--force-execute` | Run all test scripts on disk even when there's nothing new to execute |
| `--suite smoke` | Run a named suite from `test_suites/*.json` instead of only new/changed scenarios |
| `--auth-setup` | One-time: opens a browser, saves a login session to `.auth/auth.json` (only if the top-level `auth:` block in project.yaml is enabled) |
| `--record` | Human-guided interactive recording session (only if `interactive_scan: true`) |
| `--show-state` | Print the persistent project-state summary and exit |

`cli_appevolve.py` is a separate, older tool hardcoded to one specific project directory — it is **not** part of this template's workflow and will not work correctly against a project copied from this template. Use `main.py` for everything above.

---

## Prerequisites

- **Python ≥ 3.11** — `python --version`
- **Node.js ≥ 18** — `node --version`
- Install Python dependencies: `pip install -r requirements.txt`
- Install Node.js dependencies: `npm install`
- Install Playwright browser: `npx playwright install chromium`

---

## Initializing from this template

1. Copy this folder and rename it to your project name
2. Update `project.yaml` — set `name`, `application_name`, and define your `modules` (add `setup:` if a module sits behind a login)
3. Write one `inputs/module_XX_name.md` BRD file per module — structure it like the example in this template; a well-structured BRD (actors, numbered business rules, workflows, a test-scenario table) produces measurably better extraction than a loose paragraph
4. (Optional) Update `test_suites/*.json` — fill in your scenario IDs once discovery runs
5. Run the pipeline module by module as described above

`BASE_URL` for each module is always sourced from `project.yaml` — never hard-code URLs in test scripts.
