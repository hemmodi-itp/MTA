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

  "scenarios": ["SC-M01-001", "SC-M02-001"],
  "all_modules": false,
  "modules": [],

  "execution": {
    "headless": true,
    "retries": 1,
    "timeout": 60000,
    "parallel": 4
  }
}
```

**`scenarios`** — list of scenario IDs from `comprehension/business_scenarios.json`. The suite runner resolves these to `.spec.ts` files in `test_scripts/individual/`.

**`all_modules: true`** — runs every spec in `test_scripts/individual/`. Use this for regression only. When true, the `scenarios` list is ignored.

---

## How to run a suite

```bash
python cli_appevolve.py test --level 3 --suite smoke
python cli_appevolve.py test --level 3 --suite regression
python cli_appevolve.py test --level 3 --suite module_01
python cli_appevolve.py test --level 3 --suite module_01 --headed
```

---

## How to add a module suite

1. Copy `module_01_suite.json` → `module_02_suite.json`
2. Update `suite_id`, `name`, `scope`, `scenarios`, and `modules`
3. Run discovery for the new module to get its scenario IDs:
   `python main.py --project YourProject --module M02 --force-rediscover`
4. Fill in the scenario IDs from `comprehension/modules/M02/scenarios.json`

---

## File types allowed

`.json` and `.md` only. Suite definitions are JSON. YAML is not used — JSON is the single source of truth for suite configuration.
