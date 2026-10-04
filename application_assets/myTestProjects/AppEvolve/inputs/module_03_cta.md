# Business Requirements Document — Module 3: Project Card CTAs

## 1. Purpose

This module validates the call-to-action (CTA) buttons and "Read more" links on the three Selenium project cards — WebDriver, IDE, and Grid. Every download link and extension store link must resolve to a valid, non-404 URL.

---

## 2. Page Structure Overview

| Region | Description |
|---|---|
| Project card — WebDriver | Logo, description, Download button, Read more link |
| Project card — IDE | Logo, description, Download / Add to Chrome / Add to Firefox buttons, Read more link |
| Project card — Grid | Logo, description, Download button, Read more link |

---

## 3. Actors

| Actor | Description |
|---|---|
| Developer | Technical user looking for download or API documentation |
| QA Engineer | Professional evaluating Selenium tools for their project |
| Automated test agent | The test runner executing this suite |

---

## 4. Business Rules

### BR-01 — All project cards must be visible on page load
Each card must display a heading, a description paragraph, at least one CTA button, and a "Read more" link.

### BR-02 — All CTA buttons must be functional
Every download, "Add to Chrome", and "Add to Firefox" button must resolve to a valid, non-404 URL. Buttons must not be disabled, hidden, or visually broken.

### BR-03 — Internal navigation links must stay within selenium.dev
"Read more" links must navigate to `/documentation/` sub-pages, not to external domains.

---

## 5. User Workflows

### Workflow 1 — Project discovery
User lands on `/projects/`, scans the three project cards, reads descriptions, and clicks "Read more" → lands on the relevant documentation page.

**Expected path:** `/projects/` → card section → `Read more` link → `/documentation/webdriver/` (or equivalent)

### Workflow 2 — Direct download
User knows they want Selenium IDE. They scroll to the IDE card, click "Add to Chrome" or "Add to Firefox", and are redirected to the respective browser extension store page.

**Expected path:** `/projects/` → IDE card → browser store link → external URL in new tab

---

## 6. Test Scenarios — Module 3

| ID | Scenario | Priority |
|---|---|---|
| TC-019 | WebDriver "Download" or "Read more" link navigates to a valid, non-404 URL | Critical |
| TC-020 | WebDriver "Read more" link targets a /documentation/ sub-page | High |
| TC-021 | Selenium IDE "Add to Chrome" button navigates to the Chrome Web Store | Critical |
| TC-022 | Selenium IDE "Add to Firefox" button navigates to addons.mozilla.org | Critical |
| TC-023 | IDE extension store links open in a new tab (target=_blank) | High |
| TC-024 | Selenium Grid "Download" or "Read more" link navigates to a valid URL | Critical |
| TC-025 | Grid "Read more" link targets a /documentation/ sub-page | High |
| TC-026 | No CTA button is in a disabled state | High |
| TC-027 | Clicking a CTA and pressing back returns the user to /projects/ without error | Medium |

---

## 7. Test Data Requirements

| Data item | Value |
|---|---|
| Target base URL | `https://www.selenium.dev` |
| Page path | `/projects/` |
| Expected external domains | `chrome.google.com`, `addons.mozilla.org` |
| Expected internal paths | `/documentation/webdriver/`, `/documentation/ide/`, `/documentation/grid/` |

---

## 8. Acceptance Criteria

- All Critical CTA tests pass (no broken download or extension links)
- "Read more" links stay within selenium.dev/documentation/
- IDE extension links open in a new tab with `target="_blank"`
- No CTA button is disabled at page load
