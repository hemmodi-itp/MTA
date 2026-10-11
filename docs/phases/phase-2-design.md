# Phase 2 — Deep Discovery: Design

> Status: **DRAFT, awaiting approval.** No code has been changed yet.
> Inputs: `docs/MTA_IMPROVEMENT_PLAN.md` §Phase 2, `docs/audit/current_state.md` (it takes precedence over the plan), `docs/phases/phase-1-report.md`.
> Code verified at HEAD `3c39c3a` ("Phase 1"), clean working tree. Unit-test baseline on that tree: `pytest tests/unit` → **1,703 passed**, `npx vitest run` → **36 passed**.
> Scope: Phase 2 tasks **2.1–2.7** only. Nothing from Phase 3 or later is included (see D0 on the scope wording).

---

## 1. Summary

| Task | Deliverable | Where |
|---|---|---|
| 2.1 | **Deep element capture**: wider selector set, all frames, open shadow roots, one batched `page.evaluate()` per frame instead of ~19 round trips per element, and **container-scoped role locators** in place of the CSS fallback for duplicate role names. The TS runtime and Python validators learn `frame` and `scope` on a locator entry. | `tools/discovery/deep/extract.py` (+ JS), `PlaywrightScanner`, `build_dom_locator_map.py`, `LocatorManager.ts`, a shared Python resolver |
| 2.2 | **Constraint capture** on every form control: `required`, `aria-required`, `maxlength`, `minlength`, `pattern`, `min`, `max`, `step`, `type`, `inputmode`, `accept`, `multiple`, `autocomplete`, `readonly`, `disabled`, default value, `<select>` options, radio groups, error containers (`aria-describedby` / `aria-errormessage`). | same extractor → `dom_elements.json` (additive `constraints` key) |
| 2.3 | **Observed validation oracle**: per form, submit empty, then each field invalid in turn. Records native `validationMessage`, visible error text, `aria-invalid`, focus and network calls. | `tools/discovery/deep/forms.py` → `test_comprehension/form_model.json` |
| 2.4 | **Multi-page crawl + state model**: BFS within `allowed_hosts`, bounded by `max_pages`, `max_depth` and `max_minutes`, states deduped by URL template + DOM structural hash, non-destructive expanders opened, transitions recorded. | `tools/discovery/deep/crawl.py` → `test_comprehension/app_map.json` |
| 2.5 | **Network inventory** captured during the crawl and probes. | `tools/discovery/deep/network.py` → `test_comprehension/api_inventory.json` |
| 2.6 | **Role-aware discovery**: `auth.roles`, one crawl per role, diffed into a permission matrix. | `tools/discovery/deep/roles.py` → `test_comprehension/permission_matrix.json` |
| 2.7 | **Baseline capture**: console errors, page errors and navigation timing per state. | `tools/discovery/deep/baseline.py` → `test_comprehension/baseline.json` |
| AC | Ground truth (`elements.yaml`, `validation_messages.yaml`) and measurement tools (element recall, constraint coverage, page coverage, oracle match, scan time) | `benchmarks/apps/buggy_shop/`, `tools/benchmark/discovery_metrics.py` |

**No new agent.** Phase 2 is discovery work, and DiscoveryAgent stays the single gateway step. Everything new is
library code under `tools/discovery/deep/`, called from DiscoveryAgent and from a standalone CLI, so
`tools/scaffold_agent.py` is not used.

**Off by default.** Everything sits behind `discovery.deep` in `project.yaml`, default `false` (D1). With the flag
off, the scanner runs today's code path unchanged, and `dom_elements.json`, `locator_map.json` and `pages.ts` are
byte-identical to Phase 1 output. The flag is turned on in the project template and in the buggy_shop benchmark
template.

---

## 2. Plan vs. reality: adjustments

| # | Plan says | Reality (verified) | Proposed adjustment |
|---|---|---|---|
| R1 | 2.1 "Add to the selector set …" | `tag` is the **selector string** that matched (`playwright_scanner.py:598`), not the tag name. It is part of the locator identity signature (`dom_scan.py:40-72`). New `tag` values would give existing elements new `LOC-` ids, and the old entries would linger as "possibly removed". `_mint_key` (`build_dom_locator_map.py:322-345`) builds an un-slugified key such as `[role=tab]_loc_0001`, which pages.ts cannot resolve. | Elements matched by a classic selector keep the **same `tag` value** as today, using the same selector order, so their identity and `LOC-` ids do not change. Newly captured elements get `tag` = the real lower-case tag name (`div`, `summary`, `li`) plus `capture_reason` (`role:tab`, `contenteditable`, `onclick`, `tabindex`, `cursor_pointer`, `summary`, `input:date` …). `_mint_key` slugifies its fallback. This is a bug fix, and it is a no-op for every key minted today because those tags are already plain words. |
| R2 | 2.1 "Go through all frames" | Main frame only. No consumer resolves a frame: `LocatorManager.ts` always starts from `page` and **throws on an unknown type**; live validation (`script_generation/agent.py:779-807`, duplicated at `healing/tools.py:434-466`) resolves on the top-level page, so a frame element counts 0 and is excluded as dead. | Extract every frame (`page.frames`, including cross-origin frames, which Playwright can evaluate). Elements record `frame: {path: [<iframe selector>, …], url}`. A locator entry gains an optional **`frame: [selector, …]`**, which `LocatorManager.resolve` applies as a `frameLocator` chain. The Python validators share one new resolver (`locator_resolve.py`) that applies the same chain. `frame` is added to the identity signature **only when non-empty**, so main-frame ids are unchanged and identical elements in two frames no longer collide. |
| R3 | "Confirm open shadow roots are pierced" | Playwright's `getBy*` and CSS engines pierce open shadow roots. `querySelectorAll` inside `page.evaluate` does **not**, and neither do the hand-built CSS/XPath fallbacks (audit §2). | The batched extractor walks open shadow roots explicitly (closed roots cannot be reached and are recorded as a count in `scan.limitations`). For a shadow element, the CSS fallback is a host-prefixed descendant selector, which Playwright's piercing CSS accepts and which is verified with `count() == 1`. `xpath` is set to `null`, because XPath cannot cross shadow boundaries. |
| R4 | "One `page.evaluate()` … removes the reason for the 600 s cap" | ~19 round trips per element (audit §2). Browser APIs do not exactly match Playwright's `is_visible`/`is_enabled`/`inner_text` (bounding box, `visibility`, disabled `fieldset` ancestors, `aria-disabled`). A subtle difference changes `display_text`, the identity signature and the merge comparison. | Deep mode uses the batched extractor. Its JS mirrors Playwright's documented rules (visible = non-empty bounding box and not `visibility:hidden`; enabled = not natively disabled, including a disabled `fieldset` outside its `legend`, and not `aria-disabled=true`; text = `innerText.trim()`). A **parity test** runs the old and new extractors on the same fixture pages and on buggy_shop's pages. The legacy fields must be equal for every classic element. With the flag off the old per-element loop runs unchanged. In deep mode, the 600 s per-element ceiling is replaced by a 60 s timeout on the single evaluate call plus the crawl's `max_minutes`. |
| R5 | "Scope by container before falling back to CSS" | The demotion **never takes effect downstream**: `_best_locator_entry` (`build_dom_locator_map.py:224-282`) prefers `playwright_locators.get_by_role` over `recommended_locator`, so a duplicate role name still becomes a `role` entry. Live validation then excludes it as ambiguous (`count() == 2`). There is no chained or scoped locator support anywhere in the runtime. | For each element whose `(role, name)` pair is duplicated, find the nearest container with an accessible name: a dialog, form, landmark (`main`, `nav`, `aside`, `header`, `footer`, `region`), `fieldset`/`group`, `section`/`article` with a heading, list item or table row. **Verify it in the browser**: `page.get_by_role(crole, name=cname).get_by_role(role, name=name).count() == 1`. Only verified candidates are kept, as `{type: "scoped_role", value: {container: {role, name}, role, name}}`. A locator entry gains an optional **`scope: {type, locator, name?}`**, resolved first by `LocatorManager` and by the Python resolver. In deep mode, `_best_locator_entry` uses the scoped entry when the role pair is duplicated, and otherwise falls back to the existing chain (testid/id/CSS). `_locator_value_key` includes `scope` and `frame`, so two buttons with the same name in different dialogs stay two entries. |
| R6 | 2.2 constraint list | The scanner captures no constraints (audit §2). Agent-Eval captures `required`/`readonly`/options only (`engines/runtime/discovery.py:101-107`). buggy_shop declares few DOM constraints: `required`, `aria-required`, `min`/`max` on quantity, `accept`, `inputmode`, `autocomplete`, select options. There is no `maxlength`/`pattern`, and **no `aria-invalid`/`aria-describedby`** at all. Its real rules live in JS and on the server. | Capture every listed attribute into `constraints` (§5). "Every constrained field has its constraints captured" is measured against the constraints the **DOM declares**: the ground truth lists them per field. The app's undeclared rules (name ≤ 50, price format) are exactly what 2.3 observes. |
| R7 | 2.3 "only when `environment != prod`, or for forms with no destructive submit" | Read literally, this allows full submissions of non-destructive forms on prod (for example, a login form, which risks account lockout). | **Stricter.** Non-prod: full probes. Prod and `unspecified`: probes run only on forms with a non-destructive submit, and **every non-GET request is aborted** with `page.route`. That records native/client-side validation and the request the form *would* have sent, but nothing reaches the server. Forms with a destructive submit (classifier `tools/safety/action_classifier.py`) are never probed unless `destructive_allowed`. Forms with no fillable field (checkout, delete) are never probed. |
| R8 | 2.3 "too long" | When `maxlength` is present, `max+1` chars are typed (Playwright `fill` respects `maxlength`, so the probe records whether truncation happened). Without `maxlength` there is no declared bound. | Long-text probe = `maxlength + 1` when declared, else `discovery.validation.long_text_length` (default **1000**). The value used and its source are recorded. Number inputs get `min-1` / `max+1` / a non-integer when `step` is integral; text cannot be typed into `type=number`. |
| R9 | 2.4 "Reuse Agent-Eval's `runtime_discovery` logic, don't duplicate it" | `engines/runtime/discovery.py::discover()` is a page-**profiling** crawler. It follows `<a href>` only and records no transitions, no structural hash and no state dedup. It does not open expanders, has a single identity, returns summarised strings (no element records), owns its own `sync_playwright()` instance, and its SSRF guard blocks localhost by default. Its outputs feed Agent-Eval's classifier and DB. | **Share the primitives, not the loop.** Move route templating (`_normalise`), the skip-link rules (`_SKIP_LINK`), the readiness probe (`_READY_JS`) and the login helper (`_log_in` and its helpers) into `tools/discovery/web/`. Re-export them from `engines/runtime/discovery.py` (same objects, as Phase 1 did with `BrdIndex`). The new crawler uses them. Agent-Eval keeps its own loop in P2, because switching it would change its classifier inputs and scoring (D5). Host control for the legacy pipeline is `SafetyPolicy.allowed_hosts`, not the SSRF guard: legacy targets are often local by design. |
| R10 | 2.4 output → test design | Locators and `pages.ts` are per module, and every spec starts at its module URL (`build_dom_locator_map`, live validation `_get_validation_page`). An element found on another page or behind an expander would be checked against the module page, counted 0 and excluded as dead. | In P2, **`dom_elements.json` keeps today's meaning**: the module page as loaded, now with deep capture. Elements of every other state live in `app_map.json` `states[].elements`, in the same element shape and with state-local ids. P3 consumes `app_map` (state-transition, CRUD and journey generators) and decides how those elements reach `locator_map.json`, with navigation. See D2. |
| R11 | 2.4 seeds | Modular projects are run **one module per process** (audit A13). Each has its own URL and its own setup/login. The benchmark runs `--force-rediscover` per module, which would repeat a project-wide crawl six times. | The crawl is **project-level**. Seeds are every module URL plus `project.url`. It runs once and is reused: a fresh `app_map.json` is reused when its `config_hash` (the discovery block, roles, seed URLs and safety policy) is unchanged and it is younger than `discovery.reuse_minutes` (default 60). `--force-recrawl` (new `main.py` flag) or the CLI forces a crawl. The benchmark runner calls the CLI once before generating modules. |
| R12 | 2.5 "record requests … triggering UI action" | buggy_shop's pages make **no fetch/XHR calls**; the app is server-rendered. Its `/api/*` routes are never called by the UI. | The inventory records `document` navigations and form submissions (`kind: page | form_submit | xhr | fetch`) as well as XHR/fetch, not only XHR/fetch, so server-rendered apps get a real inventory. Static assets are excluded. API routes that no UI action calls stay out of scope until P8 (route extraction from code). This is recorded in the report rather than faked. |
| R13 | 2.6 `auth.roles` | `auth:` is flattened only when `auth.enabled` (`project_manifest.py`). buggy_shop logs in through **module setup steps** (alice; admin for M06), with `auth.enabled: false`. Credentials exist only as env-var names (`live_login.perform_login`) or as literal setup values. | `auth.roles` is read **independently of `auth.enabled`**. Role strategies: `credentials` (reuses `live_login.perform_login`, env vars only), `storageState` (path), `setup` (a module-style step list, which buggy_shop uses) and `anonymous: true`. Without `auth.roles`, there is one implicit role, `default`: the project's existing auth, plus each seed module's own setup steps executed before that seed. |
| R14 | 2.4 "dedupe by URL template + DOM structural hash" | Element `id`s often embed record ids (`qty-3`), and text varies with data. | The structural hash covers the **sorted multiset** of `(tag, role, type, name-attr, id with digit runs replaced by #)` for interactive elements, plus the landmark/heading skeleton (tags only). It excludes text, values and order. The state id is `sha1(url_template + structural_hash)[:12]`. One sample is visited per URL template by default (`samples_per_template: 1`, as Agent-Eval does). |
| R15 | AC "Scan time is the same or better than baseline" | The benchmark records **no discovery or scan time** (`tools/benchmark/run.py` only has generation/total). From the Phase 1 logs: the discovery step takes 52–124 s per module, of which the browser takes 2.4–4.6 s and element extraction 0.6–1.7 s. The rest is LLM comprehension. The crawl is new work and has no baseline. | Measure what is comparable: **single-page scan time, classic vs deep, on each module URL, same machine and same run** (median of 3), with `tools/benchmark/discovery_metrics.py --scan-time`. Crawl time and the discovery step time are reported separately and not gated. The benchmark result JSON gains `runtime_s.discovery` (per module, from the step results) and a `discovery` metrics block. |
| R16 | AC "element recall ≥ 95% against a hand-labelled list" | buggy_shop has **no** custom widgets, frames, shadow DOM, dialogs or menus. Some elements exist only after a state change (cart lines need items in the cart) or are reachable only by deep link (`/orders/{id}` is not linked from any page). | `benchmarks/apps/buggy_shop/elements.yaml` labels every interactive element per page and role, with `reachability: link | deep_link | requires_state`. Recall is **gated on `link`** (what a non-destructive crawl can reach) and reported, ungated, on the full list. The plan's widget, frame, shadow-DOM and duplicate-dialog cases are proven on **fixture pages** (required tests), not on buggy_shop. See D4. |
| R17 | 2.7 baseline | buggy_shop seeds no console errors. | Implemented as specified; the fixture tests prove the capture. The buggy_shop baseline is expected to be empty, and the report will say so. |
| R18 | (merge) | `merge_elements` keeps the **old dict** when the compared fields are equal (`dom_scan.py:131-132`), so new keys would never be written for unchanged elements. Adding them to `_MERGE_COMPARE_FIELDS` would flag every element as "updated" (review-queue drift noise) on the first deep scan. | Add `_ENRICHMENT_FIELDS` (`constraints`, `frame`, `shadow`, `container`, `capture_reason`, `tag_name`, `scoped` candidates). When the legacy fields are equal, enrichment fields are **copied** from the fresh scan. They count as an "update" only if the existing element already had them and they changed (for example, `maxlength` 50 → 100). |

---

## 3. Configuration

```yaml
# project.yaml — new optional block
discovery:
  deep: false               # P2 master switch: deep capture + crawl + forms + network + roles + baseline
  max_pages: 25             # per role
  max_depth: 4              # link/expander hops from a seed
  max_minutes: 10           # whole deep pass, all roles
  samples_per_template: 1   # /products/{id}: visit one sample
  reuse_minutes: 60         # reuse a fresh app_map.json with the same config_hash
  capture:                  # 2.1 / 2.2
    frames: true
    shadow: true
    cursor_pointer: true
  expanders: true           # open tabs / accordions / menus / dialog triggers (non-destructive only)
  validation:               # 2.3
    enabled: true
    max_probes_per_form: 20
    long_text_length: 1000
  network: true             # 2.5
  baseline: true            # 2.7

auth:
  roles:                    # 2.6 — read even when auth.enabled is false
    admin: { strategy: credentials, login_url: …, username_env: ADMIN_USER, password_env: ADMIN_PASS,
             username_selector: …, password_selector: …, submit_selector: …, success_url: … }
    user:  { strategy: storageState, storage_state_path: .auth/user.json }
    alice: { strategy: setup, steps: [ {goto: …}, {fill: {selector: "#username", value_env: ALICE_USER}}, … ] }
    guest: { anonymous: true }
```

- `tools/project_manifest.py` gains `resolve_discovery_config(raw)`, giving `flat["discovery"]`, and `flat["auth_roles"]` (validated with pydantic; an unknown strategy is a config error logged once, and that role is skipped). This follows the pattern of the `contracts` and `requirements` blocks.
- **Defaults:** off for existing projects (plan principle 4). **On** in `aAprojectTemplate/project.yaml` and the buggy_shop template. buggy_shop gets roles `user` (alice, `setup`), `admin` (`setup`) and `guest` (`anonymous`), reusing the literal benchmark credentials its module setup steps already contain.
- `interactive_scan: true` projects never crawl. Their discovery is human-paced by design (`--record`).

---

## 4. Task 2.1: wider element capture

### 4.1 Where it runs

`scan_dom(..., deep=True)` → `PlaywrightScanner.scan_page(..., deep_config=…)`. After navigation and readiness, which are unchanged, it calls `tools.discovery.deep.extract.extract_page(page, cfg)` instead of the selector loop. The return shape is unchanged (`{url, title, element_count, elements}`), plus a `scan` stats block. The crawl (§7) calls the same `extract_page` on every state.

### 4.2 The extractor (`extract.py` + `extract.js`)

One `frame.evaluate(EXTRACT_JS, cfg)` per frame returns an array of raw records. Python then builds the same element dict the legacy scanner builds (`semantic_locators`, `attribute_locators`, `playwright_locators`, `technical_locators`, `recommended_locator`, `locator_candidates`, `quality`, `intent_hints`), using the **existing** Python helpers (`_resolve_display_name`, `_build_locator_candidates`, `_rank_locator_candidates`, intent hints). They move into module-level functions so both paths share them.

**Selection.** The classic set comes first, in today's order: `input, button, select, textarea, a, [role=combobox]`. Then:

- `[role=button|link|tab|menuitem|menuitemcheckbox|menuitemradio|checkbox|radio|switch|slider|spinbutton|option|treeitem|searchbox|textbox]`
- `[contenteditable=""|"true"|"plaintext-only"]`, `[onclick]`, `[tabindex]:not([tabindex="-1"])`, `summary`, `details`
- elements whose computed `cursor` is `pointer`, that have no interactive ancestor and no interactive descendant (only the outermost pointer element is kept; capped at `capture.max_pointer` = 300 per frame, in document order)

`input[type=file|date|datetime-local|time|range|color]` are already covered by `input`; they get a `capture_reason` for reporting. Dedup is by element identity inside the walk, not by CSS string. The legacy dedup-by-CSS behaviour is reproduced for classic elements only, so the parity test holds.

**Walk.** Recursive over `document` and every **open** `shadowRoot`, then every frame through `page.frames`. Records include `frame_path` (a chain of iframe selectors, each built and verified to match exactly one iframe) and `in_shadow`.

**Per element, in one pass:**
- the 12 legacy attributes, `innerText.trim()`, the label (same rule as `_get_associated_label`), visible and enabled (§2 R4), tag name, CSS path, XPath
- the constraints (§5)
- the container (§4.3)
- `aria-expanded`, `aria-haspopup`, `aria-controls`: these feed expander detection in §7

### 4.3 Container-scoped locators

After extraction, Python groups role candidates by `(role, name)` (the existing demotion logic), separately per frame.

1. For each duplicated pair, the record's nearest **named container** (computed in JS: `dialog`/`[role=dialog|alertdialog]`, `form`, landmarks, `fieldset`/`[role=group]`, `section`/`article` with an `aria-label`/`aria-labelledby`/first heading, `li`, `tr`) yields `container: {role, name, kind}`.
2. Playwright verifies `get_by_role(crole, name=cname, exact=True).get_by_role(role, name=name, exact=True).count() == 1`. The few duplicated elements are the only per-element round trips left.
3. A verified candidate is added with score 105, above the demoted role (110 − 50 = 60) and below a unique testid (150). The existing demotion is unchanged, so no guard is weakened.

### 4.4 Locator entries, runtime, validation

| Change | File |
|---|---|
| `_best_locator_entry`: **deep elements only** (marker: `capture_mode == "deep"`). If the role pair is duplicated → the `scoped_role` entry `{type: "role", locator, name, scope: {type: "role", locator: crole, name: cname}}` → else testid/id/CSS. A non-empty `frame` → entry `frame: [...]`. Classic elements keep the current chain byte-for-byte. | `build_dom_locator_map.py` |
| `_locator_value_key` = `(type, locator, name, json(scope), json(frame))` | same |
| `_mint_key` slugifies the tag fallback | same |
| `LocatorEntry` gains `frame?: string[]`, `scope?: {type, locator, name?}`. `resolve` builds `base = page → frameLocator(f)… → resolveOn(base, scope)` then `resolveOn(base, entry)`. The `switch` becomes a helper over `Page | FrameLocator | Locator`. Unknown types still throw. | `LocatorManager.ts` |
| One Python mirror `resolve_entry(page, entry)` and `entry_resolves(page, entry)` (count == 1). Used by script_generation and healing, replacing the two duplicated `_locator_entry_resolves` bodies. Behaviour for today's entries is identical, including the fail-open on unknown type and exceptions, which is a guard this phase does not change. | new `tools/test_creation/script_generator/locator_resolve.py` |
| `LocatorEntry` contract adds the optional `frame` and `scope` fields | `contracts/artifacts/models.py` |

### 4.5 Identity and merge

`_element_identity_parts` appends `frame_path` (joined) only when it is non-empty. Main-frame identities are unchanged. Classic tags are unchanged (R1). The merge copies enrichment fields (R18).

---

## 5. Task 2.2: constraint capture

Added to every form control (`input`, `select`, `textarea`, `[contenteditable]`, `[role=textbox|searchbox|spinbutton|slider|combobox|checkbox|radio|switch]`) as `constraints`:

```jsonc
"constraints": {
  "type": "text", "inputmode": "decimal", "autocomplete": "username",
  "required": true, "aria_required": true,            // both kept; "effective_required" = either
  "maxlength": null, "minlength": null, "pattern": null,
  "min": "1", "max": "99", "step": null,              // strings, as declared (dates are strings)
  "accept": ".csv,.png", "multiple": false,
  "readonly": false, "disabled": false, "aria_invalid": null,
  "default_value": "1", "default_checked": null,
  "options": [{"value": "", "text": "Choose a category", "disabled": false, "selected": true}, …],  // select / datalist
  "radio_group": {"name": "size", "members": [{"value": "s", "label": "Small", "checked": false}, …]},
  "error_container": {"describedby": [{"id": "pw-help", "text": "…"}], "errormessage": null},
  "form": {"id": "product-form", "novalidate": true, "method": "post", "action": "/products"}
}
```

Rules:
- The attribute is captured as declared: an absent attribute is `null`. ARIA-only widgets (`[role=spinbutton]`) map `aria-valuemin`, `aria-valuemax` and `aria-required` into the same keys, with `source: "aria"` noted.
- `options` is capped at 200, with `options_truncated: true` when cut.
- The constraint block is never used for identity or in the merge comparison of legacy fields.

**Proof:** "every constrained field has its constraints captured" means that every DOM-declared constraint in the ground truth appears with the same value. This is checked on the fixture pages and on all buggy_shop forms (`discovery_metrics.py --constraints`).

---

## 6. Task 2.3: observed validation oracle (`form_model.json`)

### 6.1 Which forms

Forms are found during the crawl: a `<form>` element, or a virtual form (a container with ≥ 1 fillable field and a submit-like button, as Agent-Eval's `kind: virtual`). Each form is identified by `state_id` + form id/name/action + field names. Each form is probed **once per project**, by the first role that reaches it. GET forms whose fields have no constraints (search forms) are listed without probes (`skip_reason: "get_form_no_constraints"`).

| Skip reason | When |
|---|---|
| `no_fillable_fields` | Checkout, delete, logout forms |
| `destructive_submit` | Classifier says destructive and not `destructive_allowed` |
| `validation_disabled` | The config switch is off |
| `budget` | `max_probes_per_form` or `max_minutes` reached; the remaining probes are listed |

### 6.2 Probes (deterministic order)

1. `empty`: clear every fillable field, submit.
2. For each field in DOM order, with all *other* fields filled with deterministic valid values:
   - **Valid-value rules:** the first non-empty option; `type=email` → `qa@example.com`; number → `min`, else `1`; `inputmode=decimal` → `10`; date → today's date from a fixed clock (`2026-01-15`); otherwise `Test`.
   - `required_missing`, when the field is required (by DOM or observed in the `empty` probe).
   - `too_long` (R8).
   - `wrong_type`, by type: email `not-an-email`; url `not a url`; number `max+1` / `min-1` (each its own probe); text with a `pattern` → a value that fails the pattern (generated deterministically by violating its first character class; if none can be derived, `!!!`); `inputmode=decimal|numeric` → `abc`.
   - `file` probes: `wrong_accept` (a 1-byte `.txt`) and `empty`. Files are created in a temp dir and deleted afterwards.
3. Before each probe, the page is restored: `goto(state.url)` (or replay the state's `revealed_by` expander), then the role context is reused.

### 6.3 What is recorded per probe

```jsonc
{ "probe": "too_long", "field": "name", "value_rule": "len=1000 (default; no maxlength)",
  "submitted_via": "click #save-product",
  "native": {"blocked": false, "messages": {"name": null}},          // validity + validationMessage per field
  "visible_errors": [{"text": "Name must be at most 50 characters", "container": "#form-errors",
                      "role": "alert", "field": "name", "attribution": "text_mentions_label"}],
  "aria_invalid": [], "focused": "#name",
  "network": [{"method": "POST", "path": "/products", "status": 400, "aborted": false}],
  "url_before": "/products/new", "url_after": "/products", "navigated": true,
  "accepted": false,          // true = the app took the invalid input (2xx and no error shown): a defect signal
  "duration_ms": 412 }
```

- **Visible errors** are new text, compared with the pre-submit DOM, inside `[role=alert]`, `[aria-live]`, elements referenced by `aria-describedby`/`aria-errormessage`, or elements whose class or id contains `error`/`invalid`/`help`.
- **Attribution order:** an `aria-*` reference, then the nearest field container, then message text that mentions the field label, else `field: null`.
- **Native messages** are browser- and locale-dependent. The record carries `browser` and `locale` at the form-model level.

Per field, `observed_messages` summarises the results:

```jsonc
{ "required_missing": {"text": "…", "source": "visible|native|server"},
  "too_long": {…}, "wrong_type": {…} }
```

This summary is what P3/P5 consume as `source: observed`.

### 6.4 Schema (`form_model`, v2 envelope)

```jsonc
{ "schema_version": 2, "artifact": "form_model", "project": "…", "generated_at": "…",
  "environment": "local", "probe_mode": "full|client_only", "browser": "chromium 1xx", "locale": "en-US",
  "forms": [{ "form_id": "F-3a9c…", "state_id": "S-…", "url": "/products/new", "url_template": "/products/new",
              "role": "user", "method": "post", "action": "/products", "novalidate": true,
              "submit": {"text": "Save product", "destructive": false},
              "fields": [{ "name": "name", "label": "Name", "locator": {…entry…}, "constraints": {…},
                           "observed_messages": {…} }],
              "probes": [ … ], "skipped_probes": [{"probe": "…", "reason": "budget"}] }],
  "skipped_forms": [{ "state_id": "…", "form": "#delete-form", "reason": "no_fillable_fields" }] }
```

---

## 7. Task 2.4: crawl and state model (`app_map.json`)

### 7.1 Algorithm (per role, BFS)

```
queue ← seeds (module URLs + project.url), depth 0; seen_templates ← {}
while queue and pages < max_pages and time < budget:
    url, depth, via ← queue.pop(0)
    skip if: not policy.url_allowed(url) │ SKIP_LINK │ classify_url(url).destructive │ template sample quota reached
    goto(url); wait ready (shared READY_JS + bounded networkidle, as the scanner does today)
    record redirect (e.g. /admin → /login?next=… = "blocked"), HTTP status
    state ← extract_page() → state_id = sha1(template + structural_hash)
    if new state: store elements, forms, baseline; run form probes (§6)
    add transition (via → state)
    if depth < max_depth:
        for <a href> in document order → enqueue (same-host-allowed only; fragments dropped)
        for expander in state (§7.2), up to max_expanders_per_state:
            click → wait settle → if URL changed: transition to the new URL state (enqueue it)
                                   else if structural hash changed: hidden state (revealed_by = expander)
            restore (Escape for dialogs/menus; otherwise reload)
```

**Shared primitives** (R9) come from `tools/discovery/web/`:
- `normalise_route` (`/products/42` → `/products/{id}`; extended to UUIDs, hex ≥ 8 and long mixed alphanumeric segments; query → sorted parameter names with templated values)
- `SKIP_LINK` (logout, delete, `mailto:`, assets, …)
- `READY_JS`
- the login helpers

### 7.2 Expanders (non-destructive only)

The candidates are:
- `summary`
- `[role=tab]`
- `[aria-expanded="false"]`
- `[aria-haspopup]` (`menu`, `listbox`, `dialog`, `true`)
- `[data-toggle]` / `[data-bs-toggle]`
- `button[type=button]` with `aria-controls`

Every candidate passes `action_classifier.classify("click", name, role)`. **A destructive verdict is never clicked during discovery, whatever `allow_destructive` says**: discovery explores, it does not act. A submit button is never an expander.

### 7.3 Schema (`app_map`, v2 envelope)

```jsonc
{ "schema_version": 2, "artifact": "app_map", "project": "…", "generated_at": "…", "config_hash": "…",
  "seeds": ["http://127.0.0.1:8765/login", …], "roles": ["user", "admin", "guest"],
  "bounds": {"max_pages": 25, "max_depth": 4, "max_minutes": 10},
  "stopped_by": {"user": "queue_empty", "admin": "queue_empty", "guest": "queue_empty"},
  "states": [{ "state_id": "S-1f2e…", "url": "http://…/products/3", "url_template": "/products/{id}",
               "title": "…", "kind": "page|revealed", "revealed_by": null,
               "status": 200, "structural_hash": "…", "roles": ["user", "admin"],
               "elements": [ …element dicts as in dom_elements.json, ids "S-1f2e…:E-007"… ],
               "forms": ["F-…"], "first_seen_depth": 1 }],
  "transitions": [{ "from_state": "S-…", "to_state": "S-…", "action": "click|navigate|submit|expand",
                    "element": {"ref": "S-…:E-012", "role": "link", "name": "Wireless Mouse", "href": "/products/3"},
                    "roles": ["user", "admin"], "via": "href|click" }],
  "skipped": [{ "url": "/logout", "reason": "skip_link" }, { "element": "Delete", "reason": "destructive" }],
  "limitations": ["closed shadow roots: 0", "cross-origin frames: 0"] }
```

Element dicts inside states use the deep extractor's shape, so P3 can turn any of them into a locator entry with the same `_best_locator_entry`.

---

## 8. Task 2.5: network inventory (`api_inventory.json`)

- **Capture.** Listen to `request`, `response` and `requestfailed` on each role's context during the crawl and probes. A `current_action` context variable (set by the crawler: `navigate <url>`, `expand <name>`, `probe <form>:<probe>`) gives each request its trigger.
- **Kept requests.** Resource types `document`, `xhr` and `fetch` within `allowed_hosts`; static assets are dropped. Requests made while probing in `client_only` mode are recorded as `aborted: true`.
- **Templating.** Uses the same `normalise_route` as the crawl, plus query-parameter names.
- **Schemas.** Request and response JSON schemas are inferred deterministically (`tools/discovery/deep/json_schema.py`): types, required = keys present in every sample, arrays from their items merged, depth cap 6, max 20 samples per endpoint. Form posts record field names and `content_type` only.
- **Privacy.** No bodies, header values or cookie values are stored. Only header **names** are stored, plus `auth: {authorization_header: bool, cookie: bool}`.

```jsonc
{ "schema_version": 2, "artifact": "api_inventory", "project": "…", "generated_at": "…",
  "endpoints": [{ "method": "POST", "path_template": "/products", "kind": "form_submit",
                  "statuses": {"303": 0, "400": 3}, "hosts": ["127.0.0.1:8765"],
                  "auth": {"authorization_header": false, "cookie": true},
                  "request": {"content_type": "application/x-www-form-urlencoded", "fields": ["name","price","category","description"]},
                  "response": {"content_type": "text/html", "json_schema": null},
                  "triggers": [{"state_id": "S-…", "action": "probe F-…:empty", "role": "user"}],
                  "samples": 4, "roles": ["user"] }] }
```

---

## 9. Task 2.6: roles and the permission matrix (`permission_matrix.json`)

1. Each role crawls the same seeds in its own browser context: anonymous, storageState, a live `credentials` login, or `setup` steps. The `max_minutes` budget is split evenly across roles.
2. **Union pass:** for every page state reached by any role, each role that did *not* reach it **deep-links** its URL. Only GET page states are deep-linked, never `SKIP_LINK` URLs or URLs the classifier calls destructive. Outcomes:
   - `blocked`: HTTP 401/403, a redirect to a login URL, or an error page (`role=alert` plus a 4xx)
   - `reachable_unlinked`: loaded fine, but no link led there for this role. This is a finding P3/P7 turn into authorization tests.
   - `not_found`: 404
3. **Matrix.** For each state (row key = `url_template`) and each action element (key = role+name, else testid/id), set `visible`, `hidden` or `blocked` per role. It is computed deterministically from the role crawls, with no LLM.

```jsonc
{ "schema_version": 2, "artifact": "permission_matrix", "roles": ["admin","user","guest"],
  "states": [{ "url_template": "/admin", "access": {"admin": "reachable", "user": "blocked", "guest": "blocked"},
               "evidence": {"user": {"status": 403}, "guest": {"redirect": "/login?next=/admin"}} }],
  "actions": [{ "url_template": "/products", "element": {"role": "link", "name": "Admin"},
                "visibility": {"admin": "visible", "user": "hidden", "guest": "blocked"} }] }
```

**Session safety.** Logout links are skipped (`SKIP_LINK`). A role whose session is lost during the crawl (it suddenly redirects to login) is re-authenticated once. A second loss stops that role with `stopped_by: "session_lost"`.

---

## 10. Task 2.7: baseline (`baseline.json`)

Captured per state on its first visit:
- `console` messages of type `error` and `warning` (text truncated to 300 chars, with the source URL and line)
- `pageerror`s
- failed requests (`requestfailed`, and responses ≥ 500 for document/xhr/fetch)
- navigation timing from `performance.getEntriesByType('navigation')[0]`: TTFB, DOMContentLoaded, load, transferSize, plus FCP from paint entries
- request count

```jsonc
{ "schema_version": 2, "artifact": "baseline", "generated_at": "…", "browser": "…",
  "states": { "S-…": { "url": "…", "role": "user",
                       "console_errors": [{"text": "…", "source": "…:12"}], "page_errors": [],
                       "failed_requests": [], "timing": {"ttfb_ms": 12, "dcl_ms": 40, "load_ms": 55, "fcp_ms": 61,
                       "transfer_bytes": 5120, "requests": 3} } } }
```

P4's `consoleGuard` will diff against this file, and P7 will use the timings. In P2 it is only written.

---

## 11. Integration, artifacts, migration

### 11.1 Flow

```
DiscoveryAgent._run_dom_scan (deep on, not interactive):
   scan_dom(deep=True) → save_dom_scan  (module page; dom_elements.json, dom_intents.json — as today, richer)
   tools.discovery.deep.ensure_app_discovery(project, request)          [NEW]
        reuse if config_hash same and age < reuse_minutes (unless --force-recrawl)
        else: roles → crawl (forms, network, baseline inside) → permission matrix → write 5 artifacts
   failure → logged + partial_reasons ("deep discovery: …"); never blocking
```

- In BOTH mode this runs inside the existing scan thread, so it overlaps with the LLM comprehension that dominates discovery time today.
- The cached-discovery skip in the orchestrator logs a hint when deep is on and `app_map.json` is missing, as Phase 1 does for requirements.
- **CLI:** `python -m tools.discovery.deep --project X [--role user] [--no-probes] [--force]`.

### 11.2 Artifacts and contracts

| Artifact | Path | Contract |
|---|---|---|
| `app_map` | `test_comprehension/app_map.json` | strict v2 dict model (like `requirements`) |
| `form_model` | `test_comprehension/form_model.json` | strict |
| `api_inventory` | `test_comprehension/api_inventory.json` | strict |
| `permission_matrix` | `test_comprehension/permission_matrix.json` | strict |
| `baseline` | `test_comprehension/baseline.json` | strict |
| `dom_elements` | unchanged path | lenient model gains optional `constraints`, `frame`, `container`, `capture_mode`, `capture_reason`, `scan` (schema regenerated) |
| `locator_map` | unchanged | `LocatorEntry` gains optional `frame`, `scope` |

Registered in `contracts/artifacts/{models,registry,paths,boundary}.py` (`_COMPREHENSION`; `STEP_ARTIFACTS["discovery"]`), with schemas exported to `schemas/*.v2.schema.json`.

### 11.3 Backward compatibility

| Item | Flag off | Flag on |
|---|---|---|
| Scanner | old per-element loop, byte-identical output | batched deep extractor; legacy fields equal for classic elements (parity test) |
| `dom_elements.json` | unchanged | additive keys; classic elements keep their `LOC-` ids; new elements appended |
| `locator_map.json` / `pages.ts` | byte-identical | new entries may carry `frame`/`scope`; classic entries unchanged except where a duplicate role pair now gets a scoped entry instead of an ambiguous one |
| `LocatorManager.ts` | entries without `frame`/`scope` resolve exactly as before (vitest) | resolves `frame`/`scope` |
| Validators (script_generation, healing) | same results (shared resolver, same fail-open rules) | resolve `frame`/`scope` |
| Agent-Eval | moved primitives re-exported (same objects); its tests unchanged | n/a |
| v1 artifacts | migrate as before; `migrate --all` must still report `failing=0` | new artifacts validated when present |

There is no on-disk migration. A project that turns the flag on gets new artifacts at its next discovery, or by running the CLI.

---

## 12. Files

**Changed**

| File | Change |
|---|---|
| `tools/playwright_scanner.py` | `deep_config` branch calls the deep extractor; shared helpers lifted to module level (legacy path unchanged) |
| `tools/discovery/dom_scan.py` | `scan_dom(deep=…)`; identity `frame_path`; enrichment merge (R18) |
| `agents/comprehension/discovery/agent.py` (+ `agent.md`, `agent.json`) | pass the deep config; call `ensure_app_discovery`; outputs/partial reasons |
| `agents/orchestrator/agent.py` (+ md/json) | cached-skip hint; `--force-recrawl` pass-through |
| `main.py` | `--force-recrawl` |
| `tools/project_manifest.py` | `discovery` block, `auth_roles` |
| `tools/test_creation/script_generator/build_dom_locator_map.py` | deep `_best_locator_entry`, `_locator_value_key`, `_mint_key` slug |
| `agents/test_creation/script_generation/agent.py` (+ md/json), `agents/test_execution/healing/tools.py` (+ md/json) | use the shared resolver (the identical behaviour is tested) |
| `application_assets/_shared/runtime/LocatorManager.ts` | `frame` / `scope` |
| `engines/runtime/discovery.py` | import the moved primitives (re-export) |
| `contracts/artifacts/*`, `schemas/` | five new artifacts; `dom_elements` and `locator_map` optional fields |
| `tools/benchmark/run.py`, `score.py`, `report_md.py` | deep discovery once before generation; `runtime_s.discovery`; `discovery` metrics block |
| `benchmarks/apps/buggy_shop/mta_project/project.yaml.tmpl`, `aAprojectTemplate/project.yaml` | `discovery.deep: true`, roles (buggy_shop) |
| `README.md` | Discovery / scanner / data-model / manifest / artifact-chain sections |

**New**

| Path | Purpose |
|---|---|
| `tools/discovery/web/{urls,links,ready,login}.py` | shared primitives (moved from Agent-Eval) |
| `tools/discovery/deep/{__init__,config,extract,extract.js,containers,constraints,state_hash,crawl,expanders,forms,network,json_schema,roles,permission,baseline,store,cli}.py` | the deep discovery package |
| `tools/test_creation/script_generator/locator_resolve.py` | shared Python resolver |
| `benchmarks/apps/buggy_shop/elements.yaml` | element ground truth (§2 R16) |
| `benchmarks/apps/buggy_shop/validation_messages.yaml` | expected messages per form/field/probe kind, transcribed from `app.py:30-36` and the templates |
| `tools/benchmark/discovery_metrics.py` | element recall, constraint coverage, page coverage, oracle match, scan time |
| `tests/fixtures/discovery/*.html` | fixture site (§13) |
| tests | §13 |

---

## 13. Tests

**Baseline before P2** (HEAD `3c39c3a`, run while writing this design): `python -m pytest tests/unit` → **1,703 passed** (3 m 28 s); `npx vitest run` → **36 passed** (3 files).

Browser tests follow the existing pattern in `tests/unit/test_playwright_executor.py`: a `ThreadingHTTPServer` on 127.0.0.1 serving `tests/fixtures/discovery/`, and `pytest.importorskip("playwright.sync_api")`.

| Area | Tests |
|---|---|
| **Fixture pages (required)** | `widgets.html` (div[role=button], tabs, menu, switch, slider, spinbutton, treeitem, contenteditable, onclick div, cursor:pointer card, tabindex=0 span, details/summary, date/time/range/color/file inputs); `shadow.html` (open shadow root with form controls + a closed root); `frames.html` (same-origin iframe, nested iframe, srcdoc iframe); `dialogs.html` (two dialogs, each with a "Save" button; two forms each with "Submit"; a nav and a footer each with a "Home" link). Each asserts that elements are found, `capture_reason`, frame path, shadow flag, and **scoped locators verified with `count()==1`** |
| Parity | Old vs new extractor on the classic fixture and on rendered buggy_shop pages: legacy fields equal for every classic element; same `LOC-` ids |
| Constraint extraction (required) | `constraints.html`: every attribute in §5, ARIA spinbutton, select options (+ disabled, selected), radio groups, describedby/errormessage text, `form.novalidate` |
| State hash (required) | Same structure with different text/values/ids-with-digits → same hash; an added field → different hash; order-insensitive |
| URL templating (required) | numeric, UUID, hex, slug, query parameters; idempotent; never templates a plain word |
| Crawl | Fixture mini-site: BFS order; `max_pages`/`max_depth`/`max_minutes` stop reasons; `allowed_hosts` respected (an off-host link is skipped and listed); logout skipped; destructive expander not clicked; tab/accordion/dialog revealed states with `revealed_by`; transitions; one sample per template |
| Forms | Native-validation form (`required`, `maxlength`, `type=email`, `min`/`max`); JS-validated `novalidate` form with `role=alert` errors; server-validated form; attribution rules; `accepted: true` detection; destructive and no-field forms skipped; **prod/unspecified → client-only, every POST aborted** (asserted at the fixture server: zero POSTs received) |
| Network | Templating, kinds, inferred JSON schema (pure-function tests with samples), the auth flags, no bodies or header values persisted |
| Roles / matrix | Pure diff tests (visible/hidden/blocked/reachable_unlinked); fixture with an anonymous and a `setup`-login role; a session-loss re-login |
| Baseline | Fixture page with `console.error`, a thrown error and a 500 sub-request → captured; timing keys present |
| Locator runtime | vitest: `LocatorManager.resolve` with `frame`, `scope`, both, neither (unchanged), unknown type still throws. pytest: shared resolver on fixture pages (frame and scoped count == 1); existing validator tests unchanged |
| Locator map | Deep element → scoped/frame entry; classic element → byte-identical entry; `_locator_value_key` keeps two scoped "Save" entries; slugified fallback key |
| Merge | Enrichment copied without "updated" drift; a real constraint change → updated |
| Contracts / manifest | Five artifacts registered, round-trip, schemas fresh; `migrate --all` failing=0; `discovery` block defaults; roles validation |
| Integration | DiscoveryAgent with deep on (stubbed LLM, fixture site): artifacts written; a crawl failure → partial, not blocking; flag off → byte-identical `dom_elements.json` |
| Regression | Full `tests/unit` and `npx vitest run` stay green |

---

## 14. Acceptance criteria — how each will be proven

| Criterion | Proof planned |
|---|---|
| buggy_shop element recall ≥ 95% against a hand-labelled list | `python -m tools.benchmark.discovery_metrics --app buggy_shop --recall`: starts the app, runs deep discovery (no LLM), matches `app_map` states against `elements.yaml` by id/testid, else role+name. Gated on `reachability: link`; the full-list recall is also printed |
| Every constrained field has its constraints captured | `… --constraints`: 100% of DOM-declared constraints in the ground truth, plus the fixture test |
| `app_map` contains every page | `… --pages`: every page template in `elements.yaml` that a link reaches is a state in `app_map` (per role); deep-link-only pages are listed separately |
| Observed validation messages match the app's real messages | `… --oracle`: every expected `(form, field, probe kind) → message` in `validation_messages.yaml` appears in `form_model.json` (exact text) |
| Scan time same or better than baseline | `… --scan-time`: per module URL, median of 3 classic vs deep single-page scans on the same machine; deep ≤ classic for every module. Crawl time is reported separately |
| Required tests | named test files + pytest/vitest output |
| Benchmark before/after | `python -m tools.benchmark.run --app buggy_shop --label phase2` (full run, D6) vs Phase 1: no regression in detection or false failures, plus the new discovery metrics and discovery runtime |

---

## 15. Risks

| Risk | Mitigation |
|---|---|
| Deep extraction changes legacy field values, so ids churn and drift floods the review queue | Parity test on fixtures and buggy_shop; classic `tag` kept; enrichment merge; flag off by default |
| Crawl or expander clicks change application state | Destructive classifier on every click (discovery never clicks destructive things); `SKIP_LINK`; only expander-type elements are clicked; probes only invalid data; prod/unspecified → client-only with writes aborted |
| Probes create data in non-prod (e.g. the app accepts invalid input because of a bug) | Recorded as `accepted: true` (a useful finding); local/dev only for full probes |
| State explosion from dynamic content | Structural hash ignores text, values and digit runs; `samples_per_template`; hard bounds |
| Crawl time adds to discovery | Runs in the scan thread, in parallel with LLM comprehension; one crawl per project, reused; `max_minutes` |
| Native validation text depends on browser and locale | Recorded with browser and locale; ground-truth comparison uses buggy_shop's own (server/JS) messages, and fixture tests assert presence and attribution, not Chromium wording |
| Scoped locators break old runtimes | The runtime ships in-repo and changes in the same commit; entries without `scope`/`frame` resolve exactly as before (vitest) |
| Shared-resolver refactor changes validation results | The existing validator tests run unchanged, plus a table test over every entry type, including the fail-open cases |
| Moving Agent-Eval primitives breaks it | Pure move + re-export; Agent-Eval tests (`test_runtime_discovery.py`, `test_playwright_executor.py`, …) must stay green unchanged |
| Secrets in artifacts | No bodies, header values or cookie values; credentials only through env vars or existing setup steps; console text truncated |
| Benchmark run time (~2 h + Gemini spend) | Run once at the end (D6) |

---

## 16. Decisions needed from you

| # | Question | My recommendation |
|---|---|---|
| **D0** | Your message says "tasks 0.1 to 0.7", but those are Phase 0's tasks (done). Phase 2's tasks are **2.1–2.7**. Implement 2.1–2.7? | **Yes, 2.1–2.7** (this design). |
| **D1** | `discovery.deep` default | **Off** for existing projects (plan principle 4); **on** in the project template and buggy_shop. |
| **D2** | Feed elements from crawled pages and revealed states into `dom_elements.json` / `locator_map.json` now, or keep them in `app_map.json` for P3? | **Keep them in `app_map` (R10).** Specs start at the module URL; such elements would be validated against the wrong page and excluded. P3 adds navigation-aware generation from `app_map`. Expected consequence: P2 by itself does not raise AC coverage much on buggy_shop. |
| **D3** | Validation probes on prod/unspecified: the plan's wording (full submit of non-destructive forms), or client-only with writes aborted? | **Client-only, writes aborted** (R7). Stricter and safer; full probes in local/dev/staging. |
| **D4** | Add custom widgets (tabs, dialog, details) to buggy_shop so recall covers them on the benchmark, or leave the app unchanged and prove widgets on fixture pages? | **Leave buggy_shop unchanged** (keeps the Phase 0/1 numbers comparable); fixtures cover the widget, frame and shadow cases. |
| **D5** | Switch Agent-Eval's `runtime_discovery` to the new crawler now? | **No.** Share the primitives (moved and re-exported) in P2. Switching changes Agent-Eval's classifier inputs and scoring; it is a separate, measured change. |
| **D6** | Run the full benchmark (~2 h + Gemini spend) for the before/after numbers, which also closes Phase 1's open item (67/67 linked after regeneration)? | **Yes.** |
| **D7** | Crawl bounds defaults: `max_pages 25` (per role), `max_depth 4`, `max_minutes 10` (total), `samples_per_template 1` | **Yes** (buggy_shop has 12 page templates; Agent-Eval uses 12 pages / 10 min). |
| **D8** | Change the TS runtime (`LocatorManager.ts`: `frame` + `scope`) in P2? | **Yes.** Without it, frame and scoped locators cannot run. Additive; vitest-covered. |
