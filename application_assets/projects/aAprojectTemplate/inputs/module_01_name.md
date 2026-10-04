# Business Requirements Document — Module 1: [Module Name]

> Duplicate this file per module (e.g. `module_02_cart.md`), fill in the brackets,
> then reference it in `project.yaml` under `modules[].brd_file`.
>
> **ComprehensionAgent's parser is free-form** — it reads the raw file text and lets an LLM extract
> requirements, business rules, actors, and workflows from it, so nothing below is a strict schema.
> But structure matters for quality: a BRD with clear sections, numbered rules (`BR-01`, `BR-02`, ...),
> and an explicit actors/workflows breakdown produces measurably richer, more traceable scenarios than
> a loose paragraph of instructions. If you only have time for a quick bullet list, use the minimal
> format at the bottom of this file — it still works, just expect thinner coverage.

---

## 1. Purpose

_One or two sentences: what does this module let the user do, and why does it matter?_

[e.g. "This module validates that a logged-in customer can add, update, and remove items from
their shopping cart, and that the cart total always reflects the current contents."]

---

## 2. Page / Feature Overview

_Describe the structure of the page or feature: what regions/sections exist, what's in each._

| Region | Description |
|---|---|
| [e.g. Cart item list] | [e.g. One row per item: thumbnail, name, quantity stepper, remove button, line total] |
| [e.g. Cart summary] | [e.g. Subtotal, shipping estimate, checkout button] |

---

## 3. Actors

| Actor | Description |
|---|---|
| [e.g. Logged-in customer] | [e.g. Has items already in their cart from browsing] |
| [e.g. Guest user] | [e.g. Not logged in — cart persists to session only] |

---

## 4. Business Rules

_Number every rule — ComprehensionAgent extracts these as `business_rules[]` and generated scenarios
reference them by ID, so they're traceable from a failing test back to the exact rule it covers._

### BR-01 — [Rule name, e.g. "Cart cannot exceed 10 line items"]
[One or two sentences describing the constraint precisely — what triggers it, what the system must do.]

### BR-02 — [Rule name, e.g. "Quantity cannot go below 1"]
[Description.]

---

## 5. User Workflows

_Named, numbered sequences of actions from a starting state to a defined end state._

### Workflow 1 — [e.g. "Add an item to the cart"]
[e.g. "User is viewing a product page. User clicks 'Add to Cart'. Cart icon badge increments.
Item appears in the cart drawer with quantity 1."]

**Expected path:** [e.g. Product page → Add to Cart click → cart badge updates → drawer shows item]

### Workflow 2 — [e.g. "Remove an item from the cart"]
[Description.]

---

## 6. Test Scenarios — Module 1

_Optional, but strongly recommended — gives ScriptGenerationAgent explicit, prioritized coverage
targets instead of relying entirely on what the LLM infers from workflows/rules alone._

| ID | Scenario | Priority |
|---|---|---|
| TC-001 | [e.g. Add a single item to an empty cart] | Critical |
| TC-002 | [e.g. Increase quantity of an existing cart item] | High |
| TC-003 | [e.g. Remove an item — cart total updates immediately] | Critical |
| TC-004 | [e.g. Attempt to exceed the 10-item limit — system blocks it (BR-01)] | High |

---

## 7. Test Data Requirements (optional)

| Data item | Value |
|---|---|
| Target base URL | `https://yourapp.com/cart` |
| Test account | [e.g. an account pre-seeded with 2 cart items] |
| Known limits | [e.g. max 10 line items, min quantity 1] |

---

## 8. Acceptance Criteria

- [e.g. All Critical priority test cases pass]
- [e.g. Cart total is always the sum of (unit price × quantity) across all line items]
- [e.g. No console errors during any cart interaction]

---

## Minimal format (if you're short on time)

Skip sections 2-8 above and just list features as bullets — ComprehensionAgent will still extract
what it can, with less structure to work from:

- [Feature name, e.g. "Shopping cart"]
  - [Behavior, e.g. "Add an item to the cart"]
  - [Behavior, e.g. "Remove an item from the cart"]
  - [Behavior, e.g. "Cart shows a maximum of 10 items"]
- [Feature name]
  - [Behavior]
