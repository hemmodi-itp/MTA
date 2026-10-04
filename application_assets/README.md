# application_assets

All runtime artifacts produced and consumed by the agentic QA platform.
Everything here is **project-namespaced** — no files should live directly under this directory.

## Layout

```
application_assets/
  projects/
    <project_name>/       ← one folder per target application
      project.yaml        ← project config (url, browser, headless, pages)
      README.md           ← artifact manifest for this project
      inputs/             ← source documents (BRD, specs, JSON requirements)
      comprehension/      ← ComprehensionAgent output (business_scenarios.json/md)
      test_data/          ← TestDataAgent output (test_data.json/md)
      artifacts/          ← ArtifactGeneratorAgent output
        intents.yaml          intent definitions
        test_cases.yaml       test case definitions
        test_suite.yaml       test suite grouping
      locators/           ← LocatorAgent output (locators.json)
      test_scripts/       ← ScriptGenerationAgent output (TC-*.py)
      ui/                 ← UI scanner assets (locators, intents, pages, scenarios)
      discovery/          ← DiscoveryAgent output (dom scan, synthetic BRD)
      reports/            ← Execution reports (future)
```

## Supported file types

| Extension | Where used |
|---|---|
| `.yaml` | Project config, intents, test cases, test suites, scenarios |
| `.json` | Business scenarios, test data, locators, DOM scan output |
| `.md` | Human-readable exports of scenarios and test data |
| `.py` | Generated Playwright test scripts |
| `.txt`, `.pdf`, `.docx` | Input source documents (BRD, requirements) |

## Rules

- Every artifact is scoped under `projects/<project_name>/`.
- Agents write to their designated subdirectory only.
- Input documents go into `inputs/` — do not mix with generated output.
- `project.yaml` is the single source of truth for project-level settings.
