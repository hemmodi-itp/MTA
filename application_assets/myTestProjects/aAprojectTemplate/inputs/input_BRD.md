# Master BRD — [Your Application Name]

> **This file is optional.** Use it as a project-level overview if you want one central document,
> or as the BRD for a module you haven't written a dedicated file for yet (reference it directly
> in that module's `brd_file:` in `project.yaml`).
>
> **The real work is in the per-module BRD files** (`module_01_name.md`, `module_02_name.md`, ...).
> Each module BRD is what ComprehensionAgent actually reads and extracts requirements/rules/actors/
> workflows from during discovery — see `module_01_name.md` in this folder for the structure that
> produces the best extraction results. This file has no required structure; the parser accepts
> plain prose, but unstructured prose reliably produces thinner, less traceable scenarios than a
> module BRD written with clear sections and numbered rules.

---

## 1. Application Overview

_Describe the application under test: what it does, who uses it, and what the critical user journeys are._

**Base URL:** `https://yourapp.com/`

**Primary users:**
- User type 1 (e.g., Admin, Customer, Guest)
- User type 2

---

## 2. Modules in Scope

List the modules you plan to automate. Each module maps to one entry in `project.yaml` and one BRD file in this folder.

| Module ID | Name | URL | BRD File |
|-----------|------|-----|----------|
| M01 | Module One Name | `https://yourapp.com/page1` | `module_01_name.md` |
| M02 | Module Two Name | `https://yourapp.com/page2` | `module_02_name.md` |

---

## 3. Out of Scope

_List anything explicitly excluded from this project's test coverage._

- External third-party integrations
- Performance / load testing
- Localisation / i18n
- Backend API testing (covered separately)

---

## 4. Environment Notes

_Any constraints the QA team needs to know: test accounts, environment URLs, known flaky areas, etc._

- Test environment: `https://staging.yourapp.com/`
- Auth credentials: stored in `.env`, referenced from `project.yaml` via `value_env` (e.g. `YOURPROJECT_USERNAME`/`YOURPROJECT_PASSWORD`) — never write real credentials into this file or into `project.yaml` directly
