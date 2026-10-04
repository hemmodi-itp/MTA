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
├── comprehension/                      ← discovery outputs (pipeline writes these)
│   ├── dom_elements.json               ← locator source of truth
│   ├── business_scenarios.json         ← all scenarios (flat, cross-module)
│   ├── business_scenarios.md
│   └── modules/                        ← per-module scenario files
│       ├── module_01_name/
│       │   └── scenarios.json
│       └── module_02_name/
│           └── scenarios.json
│
├── test_creation/                      ← generated test artifacts (pipeline writes these)
│   ├── test_suite.json                 ← suite manifest + per-spec status
│   ├── scenario_element_map.json       ← scenario → relevant DOM elements
│   ├── test_data/
│   │   └── test_data.json              ← 8-10 variant types per scenario
│   └── test_scripts/
│       ├── individual/                 ← one .spec.ts per scenario (Level 1 execution)
│       │   └── test_SC-*.spec.ts
│       ├── M01/                        ← all M01 specs grouped (Level 2 execution)
│       ├── M02/                        ← all M02 specs grouped
│       └── workflows/                  ← multi-step cross-module specs (Level 4 execution)
│
├── test_suites/                        ← named suite definitions (you edit these)
│   ├── smoke_suite.json                ← 1 positive scenario per module
│   ├── regression_suite.json           ← all scenarios across all modules
│   └── module_01_suite.json            ← focused run for M01 only
│
└── execution/                          ← test run outputs (pipeline writes these)
    └── reports/
        ├── index.json                  ← report index (newest first)
        ├── json/{timestamp}_results.json
        └── html/{timestamp}/
```

---

## Modular workflow — how to build coverage module by module

```
Step 1: Define modules in project.yaml
        Add one entry per page/feature area with its URL and BRD file path.

Step 2: Write the BRD for module 1
        Create inputs/module_01_name.md — describe the page structure,
        business scenarios, and field constraints.

Step 3: Run the pipeline for module 1 only
        python main.py --project YourProjectName --module M01 --force-rediscover

Step 4: Review generated scripts
        Check test_scripts/M01/ — confirm the generated scenarios match your BRD.

Step 5: Execute module 1
        python cli_appevolve.py test --level 2 --module M01

Step 6: Wire module 1 scenarios into suites
        Edit test_suites/smoke_suite.json → add M01 scenario IDs.
        Edit test_suites/module_01_suite.json → scope to M01.

Step 7: Repeat steps 2-6 for M02, M03, ...

Step 8: Run the full suite once all modules are covered
        python cli_appevolve.py test --level 3 --suite regression
```

---

## Execution levels

| Level | What runs | Command |
|-------|-----------|---------|
| 1 — individual | Single `.spec.ts` file | `python cli_appevolve.py test --level 1 --file test_SC-001_name.spec.ts` |
| 2 — module | All specs in a module directory | `python cli_appevolve.py test --level 2 --module M01` |
| 3 — suite | A named JSON suite | `python cli_appevolve.py test --level 3 --suite smoke` |
| 4 — workflow | Multi-step cross-module spec | `python cli_appevolve.py test --level 4 --workflow complete_flow` |

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
2. Update `project.yaml` — set `name`, `application_name`, and define your `modules`
3. Write one `inputs/module_XX_name.md` BRD file per module
4. Update `test_suites/*.json` — fill in your scenario IDs once discovery runs
5. Run the pipeline module by module as described above

`BASE_URL` for each module is always sourced from `project.yaml` — never hard-code URLs in test scripts.
