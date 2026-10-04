# Business Requirements Document — Module 4: Footer

## 1. Purpose

This module validates the footer region of the Selenium Projects page. All social media links must open in new tabs, copyright information must be present, and the Apache License link must resolve correctly.

---

## 2. Page Structure Overview

| Region | Description |
|---|---|
| Footer | Copyright text with year, social links (GitHub, Twitter/X, LinkedIn, Slack), Apache License notice |

---

## 3. Actors

| Actor | Description |
|---|---|
| Visitor (anonymous) | User seeking to join the Selenium community or find social links |
| Automated test agent | The test runner executing this suite |

---

## 4. Business Rules

### BR-05 — Footer social links must open in a new tab
All footer social icons (GitHub, Twitter/X, LinkedIn, Slack) must open externally with `target="_blank"` and valid URLs.

---

## 5. User Workflows

### Workflow 4 — Footer / community access
User wants to join the Selenium Slack community. They scroll to the footer, click the Slack icon, and are taken to the Selenium Slack invite page in a new tab.

**Expected path:** `/projects/` → footer → Slack icon → external Slack URL, new tab

---

## 6. Test Scenarios — Module 4

| ID | Scenario | Priority |
|---|---|---|
| TC-028 | Footer is visible after scrolling to bottom of page | High |
| TC-029 | Footer contains copyright text with current or recent year | Medium |
| TC-030 | GitHub icon link opens a valid github.com/SeleniumHQ URL in a new tab | High |
| TC-031 | Twitter/X icon link opens a valid twitter.com or x.com URL in a new tab | Medium |
| TC-032 | LinkedIn icon link opens a valid linkedin.com URL in a new tab | Medium |
| TC-033 | Slack/community icon link opens a valid external URL in a new tab | High |
| TC-034 | Apache License link resolves to apache.org license page | Low |

---

## 7. Test Data Requirements

| Data item | Value |
|---|---|
| Target base URL | `https://www.selenium.dev` |
| Page path | `/projects/` |
| Expected footer social domains | `github.com`, `twitter.com` or `x.com`, `linkedin.com` |
| Expected license URL | `apache.org` |

---

## 8. Acceptance Criteria

- Footer is visible after a full-page scroll
- All social links have `target="_blank"` and resolve to valid external URLs
- Copyright text contains the current or a recent year
