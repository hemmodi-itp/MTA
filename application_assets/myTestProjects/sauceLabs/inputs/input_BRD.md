# Master BRD — [Your Application Name]

> **This file is optional.** Use it as a project-level overview if you want one central document.
> The real work is in the per-module BRD files (`module_01_name.md`, `module_02_name.md`, ...).
> Each module BRD is what the pipeline actually reads during discovery.

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
- Auth credentials: stored in `.env` as `APP_USERNAME` and `APP_PASSWORD`
