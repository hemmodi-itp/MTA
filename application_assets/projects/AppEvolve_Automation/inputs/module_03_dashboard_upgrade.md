# Business Requirements Document — Module 1: Page Load & Structure

## 1. Purpose

The dashboard has the functioanlities of the project. 

---

## 2. Page Structure Overview

Left side bar has the navigation menu. All the items in the navbar are clickable. We also have a search option which user can search the items in the left navigation bar. 
Right side of the page has the project display in charts as the status of the projects. 
On scrolling user can see the project listing. User may also check through the project list and navigate to any new project by clicking on the link. 



---

## 3. Actors

| Actor | Description |
|---|---|
| Visitor (anonymous) | First-time or returning user browsing the Selenium ecosystem |
| Automated test agent | The test runner executing this suite |

---

## 4. Business Rules

### BR-01 — Left hand navigation bar should be visible with these componenets
AppEvolve
Settings
help
Search
Main
Dashboard
projects

### BR-06 — Section visibility
The section "AI-Driven Legacy Code Conversion" should be visible 
The section "Statistics and Reports" should be visible.
The section "Recent Projects (194)" should be visible.
The table with project details should be present.
The search should work

### BR-08 — Section title and meta must be correct
validate the section titles
---

## 5. User Workflows

### Workflows — Page load verification
User lands on Dashboard.
user clicks on settings on the left bar. 
user clicks on help from the left bar. 
user searches the navigation bar from the left search. 
user Clicks on dashboard and sees all dashboard stuff
USer clicks on project on the left bar - user should be redirected to page showing "Projects"
User clicks on Role and Permission - user should be able to click the tab. Corresonsing tab should open.






---

## 6. Test Data Requirements

| Data item | Value |
|---|---|
| Target base URL | https://pt-dev.appevolve.intuitive.ai/appevolve/dashboard
| Page path | https://pt-dev.appevolve.intuitive.ai/appevolve/projects
| Expected project names | "Vishal Demo", "test0"
| Viewports to test | `375x812`, `768x1024`, `1280x800` |

---

## 8. Acceptance Criteria

- All Critical sections are present
-User is able to navigate throught the dashboard and the Navigation bar
- Page renders without horizontal overflow at all three viewport sizes
- Page `<title>` contains both "AppEvolve" and "Projects"
- Zero console errors on initial page load
