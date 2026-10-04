# Test Suites

This folder holds named suite definitions — JSON files that specify which scenarios run together and how.

---

## Suite files

| File | Type | When to run |
|------|------|-------------|
| `smoke_suite.json` | smoke | After every deployment — 1 positive per module, fast |
| `regression_suite.json` | regression | Before releases — all scenarios across all modules |
| `module_01_suite.json` | module | During M01 development — full coverage for one module |

Duplicate `module_01_suite.json` for each new module you add. Rename it to `module_02_suite.json`, `module_03_suite.json`, etc.

---

## Suite JSON format

```json
{
  "suite_id": "smoke",
  "name": "Smoke Tests",
  "description": "...",
  "type": "smoke | regression | module",
  "scope": "cross_module | all_modules | M01",

  "scenarios": ["M01_BS_001", "M02_BS_001"],
  "all_modules": false,
  "modules": []
}
```

The `execution: {...}` block from earlier versions of this format (`headless`/`retries`/`timeout`/
`parallel`) is no longer read by the current suite runner — headless mode comes from `project.yaml`,
and Playwright's own retries/timeout come from `playwright.config.ts`. Omit it; it's inert if present.

**`scenarios`** — list of scenario IDs (`spec_id` values from `test_creation/test_suite.json`) — either
legacy hyphenated (`BS-001`) or the current module-scoped form (`M01_BS_001`); both resolve correctly.
The suite runner (`tools/suite_orchestrator.resolve_suite_spec_files`) looks each one up directly
against `test_suite.json`'s manifest and resolves it to its real `.spec.ts` file.

**`all_modules: true`** — runs every spec listed in `test_suite.json` whose file still exists on disk. Use this for regression only. When true, the `scenarios` list is ignored.

---

## How to run a suite

```bash
python main.py --project YourProjectName --suite smoke
python main.py --project YourProjectName --suite regression
python main.py --project YourProjectName --suite module_01
```

Headed vs headless is controlled by `project.yaml`'s `headless:` setting, not a per-suite flag.

(`cli_appevolve.py` is a separate, older tool hardcoded to one specific project directory — it is not
part of this template's workflow. Use `main.py --suite` for everything above.)

---

## How to add a module suite

1. Copy `module_01_suite.json` → `module_02_suite.json`
2. Update `suite_id`, `name`, `scope`, `scenarios`, and `modules`
3. Run the pipeline for the new module to generate its specs:
   `python main.py --project YourProjectName --module M02 --force-rediscover`
4. Fill in the scenario IDs from `test_creation/test_suite.json`'s `spec_id` field (filter by
   `module_id: "M02"`), or read them straight from `test_creation/test_catalog.md`

---

## File types allowed

`.json` and `.md` only. Suite definitions are JSON. YAML is not used — JSON is the single source of truth for suite configuration.
