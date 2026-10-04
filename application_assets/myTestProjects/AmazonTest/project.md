# Project Overview

This file describes the project this folder represents. It is a companion to `project.yaml`, which holds the machine-readable configuration consumed by the agent pipeline at runtime.

## What belongs here

- A brief description of the application under test: what it does, who uses it, and the URL being tested
- The browser and headless configuration used for test execution
- A summary of the scope covered by this project — which workflows, modules, or pages are in scope
- Any project-specific constraints relevant to the QA team (e.g., auth requirements, environment dependencies, known flaky areas)
- References to the input BRD files in `inputs/` that seed the pipeline

## How it fits into the pipeline

This project folder is the root of a single end-to-end QA pipeline run.

```
project.yaml  — machine-readable config; BASE_URL read from here and injected via playwright.config.ts
inputs/       — BRD documents; processed by ComprehensionAgent
comprehension/— dom_elements.json, business_scenarios.json, interaction_catalog.json
test_creation/
  test_data/  — test_data.json (8-10 variants per scenario)
  test_scripts/ — test_BS-*.spec.ts (TypeScript Playwright, one per business scenario)
  scenario_element_map.json — which DOM elements are relevant to each scenario
  test_suite.json           — suite manifest (new/existing/healed/degraded per spec)
execution/
  reports/    — Playwright JSON + HTML reports
```

## Prerequisites

- **Node.js ≥ 18** must be installed (`node --version`)
- Run `npm install` at project root to install `@playwright/test`
- Run `npx playwright install chromium` to install the Chromium browser binary

## Running tests

```bash
npx playwright test                        # run all specs, headless
npx playwright test --headed               # run all specs, headed (visible browser)
npx playwright test test_BS-007_*.spec.ts  # run single spec
npx playwright test --reporter=html        # generate HTML report
```

`BASE_URL` is always sourced from `project.yaml` — never hard-code a URL in a test script.

## Template instructions

When initializing a new project from this template:
1. Copy this folder and rename it to your project name
2. Update `project.yaml` with the correct `name`, `application_name`, `url`, and `brd_dir`
3. Place your BRD or requirements documents in `inputs/`
4. Run the pipeline — downstream folders will be populated automatically by the agents
