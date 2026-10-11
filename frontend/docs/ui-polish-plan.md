# UI polish plan: MTA web app

**Status:** approved with all recommendations (D1–D8) and implemented on 2026-10-11. See "Outcome" below; the
original proposal follows unchanged.
**Date:** 2026-10-10

## Outcome (2026-10-11)

Measured with the same harness, real data and 15 routes × 5 variants as the audit:

| Check | Before | After |
|---|---|---|
| CLS, app pages | 0.11–0.63 | **0** after the final fixes (re-measured on dashboard, runs, run detail and settings at 1440 and 1920; earlier full matrix ≤ 0.0003 except one 0.011 scroll artifact) |
| Sideways page scroll at 360 px | 4 pages (up to +862 px) | **none** on any page |
| Text-token contrast | 17 pairs < 4.5:1 | all ≥ 4.5:1, enforced by `src/app/design-tokens.test.ts` |
| Decorative infinite loops | 6 | 0 (only live dots, the log cursor and Copilot's typing dots loop) |
| Keyboard | gaps | every focus stop shows a ring (only Next's dev-only portal doesn't); drawer = Radix Sheet; Copilot closes on Esc and returns focus |
| Compressed JS per route (prod build) | login 238 · dashboard 419 · runs 287 · run 431 · projects 285 KB | 227 · 413 · 282 · 441 · 279 KB |
| `npm run lint` / `build` / `test:unit` | 0 errors (2 warnings) / pass / none | 0 errors (1 warning) / pass / 45 tests pass |

The framer saving is real but smaller than framer's own size rollups suggested (≈ 11 KB on the leanest route), and the
run page grew by 10 KB for the new pipeline components. Out of scope and untouched: login/signup (only a mechanical
`motion.*` → `m.*` rename, required by `LazyMotion strict`), marketing, and the hard-coded `healingPenalty={4}` on
the report page.
**Goal:** bring the signed-in app to Linear / Vercel / Datadog quality, with motion that explains state changes.
Business logic stays untouched.

---

## 0. Scope (please confirm)

The brief ends with "Work only on the scope below.", but no list follows it. **Proposed scope:**

| In scope | Out of scope |
|---|---|
| App shell: sidebar, top bar, ⌘K palette, Copilot panel, notifications, mobile drawer | `/login`, `/signup`: redesigned last week, already CLS 0 and AA-clean |
| Dashboard `/dashboard` | Marketing `/`: separate surface; its copy and fake run card describe the old Playwright pipeline (a content decision, not polish) |
| Projects `/projects`, project detail `/projects/[id]`, New evaluation `/projects/new` | API routes, server actions, Prisma, `lib/api/*`, `lib/query/*` (fetching, query keys, polling), auth, Python backend |
| Runs `/runs`, run detail `/runs/[runId]`: live, completed, failed, legacy | |
| Reports `/reports`, report detail `/reports/[id]` | |
| Settings `/settings` | |
| Shared layer: `globals.css`, `components/ui`, `components/motion`, `components/shared`, `lib/motion.ts` | |

## 1. How the audit was done

- **App setup:** dev server on :3100. A throwaway local account `ui-audit@example.com` signed in; this is the only database write.
- **Data:** real data, dumped read-only from the local DB with the app's own mappers and served to that account through Playwright route mocks. A synthetic in-flight copy of the latest run (step 9 of 18 running) stands in for a live run, because none exists in the DB.
- **Captures:** 15 routes × 5 variants (1440 light, 1440 dark, 360 light, 360 dark, 1920 dark), 75 page loads in all.
- **Measurements:** CLS through `PerformanceObserver`, horizontal page overflow at 360 px, and WCAG contrast computed from the token values.
- **Baseline gates:** `npm run lint` gives 0 errors and 2 pre-existing warnings. `npm run build` passes.

## 2. Cross-cutting findings

| # | Problem | Evidence | Root cause |
|---|---|---|---|
| X1 | **Layout shift on every app page** | CLS ≈ 0.17 on all desktop app pages (0.11 at 1920). Run detail reaches **0.47** (live) and **0.63** (failed). Target is 0. | `AppShell` learns "is desktop" after mount, then animates `paddingLeft` from 8 to 276 px. Run pages also swap a single `h-96` skeleton for much taller content. |
| X2 | **Sideways page scroll at 360 px** | Dashboard +862 px, Projects +62, Runs +34, Report +26 | Grid items lack `min-w-0`, so the heatmap's `w-max` and long titles stretch the page. The Runs status tabs neither wrap nor scroll. |
| X3 | **WCAG AA failures** (normal text needs 4.5:1) | Light: green "Passed / Completed" pill **2.78**, `text-success` 3.30, `text-warning` (#F59E0B) **2.15**, critical on its tint 3.81, primary on its tint 4.20, `/70` timestamps **2.71**, muted text on the page background 4.45. Dark: white on primary button **3.68**, white on the red badge 3.76, `/70` timestamps 4.06. | There is one base color per status, used for fills, tints and text alike. Text needs its own `-fg` shade per theme. |
| X4 | **Status colors are not one system** | 15+ hand-written tone and color maps (StatusPill, findings severity, verdicts, requirement status, gates, discrepancies, notifications, insights, two KPI tone maps, score colors, heatmap, activity dots, recommendation borders). `text-warning-foreground dark:text-warning` is copy-pasted 20 times. `cloning`, `installing` and `launching` are active states but render grey like `queued`. No `flaky` style. | No semantic status registry. |
| X5 | **Score bands disagree** | 78 is **green** on the dashboard but **amber** on the run and report pages. | `band()` uses ≥75 / ≥50 (the DESIGN.md rule). `ComplianceCard`, `QualityScoreCard` and `AgentScoresCard` use ≥80 / ≥60. |
| X6 | **No shared page or card grammar** | Pattern counts: 2 card systems (`Card`, `MotionCard`) with different shadows; 3 eyebrow styles; 3 KPI styles (sans 34 px, mono 2xl, mono xl); 4 page widths (full, `max-w-2xl` centered, `max-w-3xl` centered). Headers: Dashboard and Runs have none, and only Projects has a primary action. | No `PageHeader`, `SectionCard` or `KpiCard` primitives. |
| X7 | **Motion breaks the brief** | Full `motion` bundle everywhere (39.3 kB gzipped). 6 infinite decorative loops: 2 hero blobs, floating empty-state icon, Copilot sparkle, insight sparkle, bell shake every 6 s. Only the Copilot typing dots and the log cursor loop for a reason. Width, height or padding animations: shell padding, sidebar width, runs score bars, performance bars, progress bars (`transition-all`). `fadeUp` and page transition run 400 ms. A "bouncy" spring is used on hover. Lists animate every row, with no 20-row cap; the heatmap's last cell starts after 1.3 s. | `lib/motion.ts` values predate the brief. |
| X8 | **Page transition skips list → detail** | `/runs` → `/runs/[id]` and `/projects` → `/projects/[id]` play no enter animation. | Per Next 16 `template.md`, the `(app)` template remounts only when its own segment changes (`runs` stays `runs`). |
| X9 | **Reduced motion is partial** | Respected only by framer transforms (`MotionConfig reducedMotion="user"`), `.shimmer` and `CountUp`. Ignored by CSS pulse and spin, tw-animate dialog keyframes, and Recharts draws (900–1400 ms). | No shared hook or global CSS guard. |
| X10 | **Loading, empty and error states** | Page loading is one grey `animate-pulse` block (project, run and report detail). "Loading…" text appears in Runs and the log tab. The "Business scenarios" card renders blank when empty. The Projects empty state never shows its CTA (no `onAction`). The failed-run card dumps a raw Python exception as body text. | `EmptyState`, `ErrorState` and `Skeleton` are too thin. |
| X11 | **Keyboard and screen readers** | Mobile drawer and Copilot have no focus trap, no Esc and no focus return. Runs status tabs have no tab semantics. Mode cards are `role=radio` without arrow-key navigation. Focus rings are missing or inconsistent on sidebar quick actions, chips, filter pills, project cards and runs tabs. | Custom controls skip Radix where it would provide this. |
| X12 | **Stacking order** | The top bar is z-30, the sidebar z-40, and Copilot, drawer, dialogs, popovers and tooltips all z-50. | No z-index scale. |

## 3. Audit per page (top problems)

**Dashboard**
1. Opens straight into the KPI tiles: no title, no description, no primary action.
2. At 360 px the page scrolls 862 px sideways (X2). The four KPI tiles take about 700 px, a whole screen.
3. At 1440 the Performance matrix clips "Verified" and "Duration" and cuts "121/9/12" down to "12". The risk heatmap shows 4 of 8 columns with no scroll affordance. Project-health names truncate to "docs-com…".
4. Decorative loops (hero blobs, floating empty icon). Amber and green small text fails AA (X3).

**Projects**
1. The header has no description. The button says "New Project" while the sidebar says "New evaluation".
2. Cards hide what matters: no score band color, no last-run time, and the full GitHub URL adds noise. Hover is only a background tint, and there is no visible focus ring.
3. The empty state's CTA never renders. The page overflows 62 px at 360.

**Project detail**
1. No primary action (Re-run or New evaluation).
2. Doubled heading: "Run history" h2, then a "Recent runs" card title. Every row repeats the project name. Scores carry no band color.
3. Loading state is one grey block.

**New evaluation**
1. The column is centered, so its header starts at a different x than every other page.
2. Mode cards have no arrow-key radio navigation.
3. Conditional fields (live URL, login, BRD path) pop in and out with no transition.

**Runs**
1. No description and no primary action. Status tabs overflow at 360 and lack tab semantics.
2. The 760 px-min table shows two columns on a phone; it needs stacked rows on mobile.
3. Running rows show no sign of progress. Score bars animate `width`. Every row staggers in.
4. "11 / 5 / 4" is unlabeled. Green and primary small text fails AA.

**Run detail, live**
1. The running step is a 12 px spinner inside a circle. The row is not highlighted, pending steps look disabled, and nothing animates when a step completes.
2. The progress bar animates `width`. The status pill is static, with no live pulse.
3. The timing line ("elapsed 7m 23s · about 6m 39s left · ends ~22:04 44%") is monospace log text instead of stat chips.
4. The log is fixed at 288 px next to an 18-step list, leaving a tall empty column. CLS is 0.47.

**Run detail, completed**
1. In the 6-up KPI row, the wrapped label "Insufficient evidence" misaligns its value. KPI numbers are monospace here but sans on the dashboard.
2. Score 61 renders brown (#92400e) on the 80/60 band (X5). The header shows the full run id.
3. Nine tabs wrap into three rows on mobile, and the active tab has no moving indicator.

**Run detail, failed**
1. The raw exception (`ClientError: 400 INVALID_ARGUMENT {'error': …}`) is the card body.
2. CLS is 0.63.

**Run detail, legacy (sample projects)**
1. The empty "Business scenarios discovered" card is blank.
2. The quality ring shows 78 in amber, while the dashboard shows 78 in green.

**Reports**
1. Rows are about 80 px tall because `Card`'s flex `gap` lands between the links.
2. Scores carry no band color, and there is no status or description.

**Report detail**
1. Breakdown bars misalign: the label widths differ (`w-48` vs `w-40`).
2. +26 px overflow at 360. Centered column.
3. *Not touching:* the "Healing penalty −4" bar comes from a hard-coded `healingPenalty={4}` in the page, and it shows on agent runs too. I'm flagging this for the backend/product owner.

**Settings**
1. Shows a hard-coded name and email ("Hem Modi"), a fake API key and fake plan usage. Save, Copy and Generate do nothing. (See D4.)
2. Default shadcn tabs, while Runs uses a custom segmented control.

**Shell**
1. It is the CLS source (X1).
2. On mobile the top bar shows only ☰ and 🔔, so there is no page or brand context.
3. The drawer and Copilot have the focus issues in X11. The bell shakes every 6 s, and the gradient CTA is loud.

## 4. Decisions I need from you

| # | Decision | Recommendation |
|---|---|---|
| D1 | **Scope:** confirm §0 | As proposed |
| D2 | **`layoutId` vs `domAnimation`.** The brief asks for both, but in framer-motion 12 `layout`/`layoutId` only ship in `domMax` (measured from the package: `m`+`domAnimation` **14.0 kB** gz, `m`+`domMax` **27.4 kB**, today's full `motion` **39.3 kB**). | **`domAnimation`** plus a small `<SlidingIndicator>` primitive: one absolutely-positioned element moved with `x`/`y`/`scaleX`. It looks the same as `layoutId` and is transform-only. Sidebar collapse then snaps width while labels fade (no width tween), and lists enter and exit without FLIP reflow. *Alternative:* `domMax` for native `layoutId` and a FLIP sidebar (+13.4 kB). |
| D3 | **One score band everywhere?** DESIGN.md says ≥75 / ≥50 (`band()`). Three components use ≥80 / ≥60. | Yes, use `band()`. Example: 78 becomes green on the run and report pages, matching the dashboard. Judge scores in the test-case list (0–100 per test, ≥70 / ≥40) stay as they are. |
| D4 | **Settings shows mock data** (name, email, API key, plan) | Polish the visuals. Show the signed-in user's real name and email (`AppShell` already has `user`; pass it through a context, no new fetch). Disable the controls that do nothing (Save, Copy, Generate key) and label them "Not available yet". *Alternative:* visuals only, keep the content as is. |
| D5 | **Test runner.** The README requires unit tests. `frontend/` has no runner, but vitest 4.1.10 is a repo-root devDependency, and there is no jsdom. | Add `frontend/vitest.config.ts` (`@/` alias, node environment) and `"test:unit": "vitest run"`. npm resolves `vitest` from the root `node_modules/.bin`, so **no new dependency**. I verified this works. Tests cover pure logic (list in §5, A6). *Alternative:* add `vitest`, `jsdom` and `@testing-library/react` to `frontend` for render tests (new devDependencies, needs your OK). |
| D6 | **`flaky` status.** `TestStatus` has no `flaky` today (retry/flaky is Phase 4.7 of the v3 plan). | Add the token and pill style now, unused until the backend emits it. |
| D7 | **Chart entrance.** Recharts animates SVG geometry. That causes no layout or CLS, but it isn't strictly transform/opacity. | Keep Recharts' series draw but shorten it to ≤ 600 ms ease-out, turn it off under reduced motion, and wrap each chart in a fade + 8 px rise. *Strict alternative:* fade/rise only, no series draw. |
| D8 | **Expand/collapse.** Tweening height animates a layout property. | Height snaps (user-initiated, so CLS-exempt). Content fades in and moves 4 px, and the chevron rotates. Same for accordions, test-case rows and conditional form fields. |

## 5. Plan

Order: **foundations first, then pages.** After each page: check it in the browser through the harness (1440 light and dark, 360 light and dark, 1920 dark), confirm CLS = 0 and no sideways scroll, then `npm run lint` and `npm run build`. Both must pass before the next page.

### Phase A: Foundations

**A1. Tokens (`globals.css`).** These extend the existing tokens; nothing is renamed.

- **Status tones:** `success`, `warning`, `critical`, `info`, `neutral`, `violet` (healed / AI), and a new `orange` (flaky). Each tone has four tokens:
  - `--{tone}`: fill, dot, bar and chart color;
  - `--{tone}-fg`: text, at least 4.5:1 on the card *and* on its own tint, in both themes;
  - `--{tone}-tint`: about 12 % background mix;
  - `--{tone}-border`: about 30 % mix.

  Exposed as Tailwind colors (`text-success-fg`, `bg-success-tint`, …) and as a `.tone-*` utility that sets all four.
- **Dark-mode fill:** `--primary-solid` for filled buttons, about 5.2:1 with white text. `--primary` keeps its role for text, rings and charts.
- **Shadows:** `--shadow-xs`, `--shadow-card`, `--shadow-card-hover`, `--shadow-popover`, `--shadow-overlay`, light and dark. These replace the hard-coded `shadow-[…]` values.
- **Typography:** `@utility` classes `text-page-title`, `text-section-title`, `text-eyebrow` (11 px, 600 weight, 0.08 em tracking), `text-kpi` (tabular), and `--text-2xs` (11 px). These replace `text-[11px]`, `text-[34px]` and `tracking-[0.12em]`.
- **Spacing rhythm:** page stack 24 px, card padding 20 px, grid gap 16 px. Encoded in the primitives, not repeated per page.
- **z-index:** `--z-sticky` 30, `--z-sidebar` 40, `--z-drawer` 50, `--z-panel` 55 (Copilot), `--z-modal` 60, `--z-popover` 70, `--z-toast` 80, `--z-tooltip` 90.
- **Motion:**
  - Durations: `--dur-fast` 120 ms (press), `--dur-micro` 160 ms (hover, toggles), `--dur-panel` 240 ms (dialogs, sheets, panels), `--dur-page` 280 ms.
  - Easings: `--ease-enter` (out) `cubic-bezier(.16,1,.3,1)`, `--ease-exit` (in) `cubic-bezier(.4,0,1,1)`, `--ease-move` `cubic-bezier(.65,0,.35,1)`.
- **Global reduced-motion guard:** under `prefers-reduced-motion: reduce`, CSS animations and transitions drop to ~0 ms and run once; only the live indicators fall back to a static state.

**A2. Motion system (`lib/motion.ts`, `providers.tsx`)**

- Retune the values to the brief:
  - micro-interactions 120–200 ms; panels and pages 200–350 ms;
  - enters ease-out, exits ease-in and shorter (120–160 ms);
  - springs only for drag/layout (with D2 = `domAnimation` that means none). `bouncy` goes away; hover and press become short tweens.
- `<MotionProvider>`: `LazyMotion features={domAnimation} strict` plus `MotionConfig reducedMotion="user"`. Every `motion.*` becomes `m.*`, and `strict` makes any leftover throw in dev.
- `useReducedMotion()` shared hook (`src/hooks/`) for things framer doesn't drive: Recharts `isAnimationActive`, `CountUp`, CSS live effects, auto-scroll behaviour.

**A3. Motion primitives (`components/motion/`)**

- `PageTransition`: used by `template.tsx`; keyed by pathname so list → detail animates (X8). Opacity plus an 8 px rise, 280 ms, no scale.
- `Stagger` / `StaggerItem`: 30 ms step, **capped at 20 items**; items past 20 render with `initial={false}`. A `rowMotion(index)` helper does the same for `<tr>`s.
- `Presence`: `AnimatePresence` wrappers for list add/remove (activity feed, notifications, filtered rows, filter chips) and for owned panels (Copilot).
- `SlidingIndicator` (per D2): sidebar active item, segmented tabs and line tabs.
- `CountUp` (existing): moved onto the shared hook and used for every KPI (run detail, project detail).
- `ProgressBar`: `scaleX` transform with an eased value change, plus an optional "live" sheen (a translating highlight) while active.
- `ChartReveal`: fade plus rise around charts (D7).
- `Collapse`: per D8.
- `Pressable`: hover and press feedback. CSS `active:scale-[.98]` on buttons. Interactive cards get a 2 px lift, and their hover shadow is a pseudo-element faded in and out (opacity only).
- `LiveDot`: pulse ring (transform + opacity) for running states.
- Skeleton shimmer becomes a translating `::after` highlight (transform). Today it animates `background-position`.

**A4. UI patterns (`components/shared/`, `components/ui/`)**

- `PageHeader`:
  - eyebrow or breadcrumb (optional), title, description, a primary-action slot, and a meta row;
  - one left-aligned position on every page; narrow pages (forms, settings, report) keep a max width but left-align.
- `SectionCard`: merges the `Card` and `MotionCard` headers into one header pattern (title, hint tooltip, action slot).
- `KpiCard`: one KPI style that replaces both `KpiTile` and `KpiCard`. It has a count-up value, delta chip, optional sparkline and fixed internal rows so wrapped labels can't misalign values. A compact 2-up variant serves mobile.
- **Status registry** (`lib/status.ts`, presentation only) maps each status to tone, label and icon.
  - The 8 semantic statuses: passed ✓, failed ✕, running (live dot), queued (clock), inconclusive (?), skipped (−), flaky (shuffle), healed (wand).
  - Every domain value maps onto one of them: run / test / step statuses, verdicts, severities, risk, gates.
  - `StatusPill` and every hand-written map read the registry. Icons mean color is never the only cue.
- `ScoreBadge` / `ScoreBar` from `band()` (per D3).
- Skeletons shaped like the final layout, so swapping in content causes no shift: `PageHeaderSkeleton`, `KpiRowSkeleton`, `TableSkeleton`, `CardGridSkeleton`, `RunDetailSkeleton`.
- `EmptyState`: icon, title, description, and an action as a link *or* a button. Static, no loops.
- `ErrorState`: card style with a retry button, plus an optional collapsible "Technical details" mono block, used for the raw exception.
- `SegmentedTabs`: Radix Tabs semantics, a sliding indicator, and a horizontally scrollable strip with edge fades on small screens. Runs status tabs and Settings tabs use it, and the run-detail tabs use its line variant.
- `DataTable` styling: sticky header, row hover and focus ring, numeric alignment. Below `sm` it switches to a stacked-row layout.
- `components/ui` tweaks:
  - Button gets `--primary-solid`, press scale, and tokenized focus ring and radius.
  - Dialog, Sheet, Popover and Dropdown get tokenized durations and easings (enter ease-out 240 ms, exit ease-in 150 ms) and z-index tokens.
  - Skeleton gets the transform shimmer.
  - Progress is transform-based (it already is) and tokenized.

**A5. Shell**

- Sidebar offset comes from CSS (`md:` padding through a CSS variable and a `data-collapsed` attribute set from the persisted store), so the first render already matches. This fixes the 0.17 CLS.
- Sidebar:
  - collapse per D2;
  - `SlidingIndicator` for the active item;
  - focus rings on every item;
  - the "New evaluation" CTA toned down to the primary solid, with no sheen sweep.
- The mobile drawer becomes the shadcn `Sheet` (Radix Dialog): focus trap, Esc, focus return, `aria-modal`.
- Copilot:
  - Esc closes it, and focus goes to the input on open and back to the opener on close;
  - typing dots stay (they explain "busy"); the sparkle wobble goes;
  - message enter uses opacity plus y.
- Top bar on mobile shows the current page title, with the brand on the dashboard.
- The bell shakes once when the unread count increases, not on a loop.
- Every overlay uses the z-index tokens.

**A6. Unit tests (D5)**

- `useReducedMotion` store: subscribe and snapshot against a fake `matchMedia`, including change events and unsubscribe.
- Motion presets: reduced variants contain no transform keys; durations stay inside the brief's ranges; exit is shorter than enter.
- Stagger cap: index 20 and above gets no animation.
- Status registry: every `RunStatus`, `TestStatus` and `StepStatus` maps to a tone, label and icon; all 8 semantic statuses exist.
- **Contrast guard:** parse `globals.css` and assert ≥ 4.5:1 for every `-fg` token on the card and on its tint, in light *and* dark. This keeps AA from regressing.

### Phase B: Pages (in this order)

1. **Runs list**
   - `PageHeader` (description, "New evaluation" action).
   - `SegmentedTabs`: scrollable on mobile, real tab semantics, sliding indicator.
   - Filter chips with presence, plus a search input wired to the *existing* `q` URL param (no new filtering logic).
   - `TableSkeleton`.
   - Score bars as `scaleX`.
   - Running rows show `LiveDot` plus `currentStage` (already on the run object, no new fetch) and an indeterminate live bar.
   - Column header tooltip "passed / failed / other".
   - Row stagger capped at 20; stacked rows below `sm`.
2. **Run detail.** "Alive" for live runs, readable when finished.
   - Header: `PageHeader` with breadcrumb "Runs / project". The run id is shortened, with a copy button. Status pill with live pulse.
   - Pipeline:
     - progress `scaleX` with a live sheen;
     - the active step is highlighted (tint plus ring) with a pulsing icon;
     - a step that changes state cross-fades its icon (pending → running → success / failed / skipped) and the check scales in;
     - pending steps are neutral, not disabled-grey;
     - stat chips replace the mono timing line;
     - the activity log height follows the steps column (sticky on desktop); new log lines fade in.
   - `KpiCard` row with count-up and aligned values.
   - Score on `band()` (D3).
   - Line tabs with a sliding indicator, scrollable on mobile.
   - Tab panels fade in.
   - Accordions per D8.
   - Failed run: `ErrorState` with a one-line summary and collapsible technical details.
   - Legacy view: empty-state for empty sections.
   - `RunDetailSkeleton` brings CLS to 0.
3. **Dashboard**
   - `PageHeader` ("Dashboard", portfolio summary, "New evaluation").
   - `KpiCard` ×4, 2-up on mobile.
   - Grid `min-w-0` fixes (X2).
   - Performance matrix: columns adapt; Verified and Duration collapse into the row below `2xl`, nothing is clipped.
   - Heatmap: sticky first column plus a scroll-edge fade; cells capped in the stagger.
   - Health names wrap to two lines instead of truncating.
   - `ChartReveal`.
   - Remove the decorative loops (hero blobs, floating empty icon, insight sparkle).
   - Skeleton matched to the layout.
4. **Projects and Project detail**
   - `PageHeader` with the consistent "New evaluation" label.
   - Project cards:
     - score badge with band color;
     - last-run status and time;
     - `owner/repo` instead of the full URL;
     - hover lift and focus ring;
     - staggered entrance.
   - Empty state with a working CTA.
   - Detail page: header with Re-run (existing mutation) and New evaluation; `KpiCard`s; run history as a table with the score bar, no repeated name, live row; matching skeleton.
5. **New evaluation**
   - Left-aligned `PageHeader`.
   - Mode cards become a Radix RadioGroup: arrow keys, focus ring, a selected state that animates its check.
   - Conditional fields use `Collapse`.
   - The repo-check status line cross-fades.
   - The submit button keeps its pending state.
6. **Reports and Report detail**
   - Fix the row spacing bug.
   - Score badge with band, run status and date (`date-fns`, already a dependency), `PageHeader`, staggered rows.
   - Detail: aligned breakdown grid, band-colored ring, `ChartReveal`; recommendation cards on the tone system; no overflow at 360.
7. **Settings**
   - `PageHeader`, `SegmentedTabs`, D4 content treatment, form layout on the token system.

### Phase C: Wrap-up

- Final pass across the whole matrix, plus a reduced-motion pass (`REDUCED=1`) and a keyboard-only pass (Tab through every page; focus visible on every stop).
- Report: changes per page, before/after numbers (CLS, overflow, contrast, framer bundle), and whatever is left for the next session.
- Update `DESIGN.md` (tokens, motion table, status registry) so it matches reality.

## 6. Guardrails

- **Changes allowed in:** `globals.css`, `components/**`, `hooks/**`, `lib/motion.ts`, new `lib/status.ts`, and the JSX in `app/(app)/**`. The JSX only changes rendering, never which data is fetched or how.
- **Never touched:** `app/api/**`, `app/actions/**`, `prisma/**`, `lib/api/**`, `lib/query/**` (keys, polling), `lib/auth/**`, `lib/insights.ts` logic, `lib/run-status.ts`, `proxy.ts`, Python.
- **Per-page check:** after each page I check `git diff --stat` against that list.
- **Dependencies:** no new runtime dependency. Everything comes from what is already installed: framer-motion, Radix, tw-animate-css, lucide, date-fns, cmdk, sonner, recharts.

## 7. Done means

| Check | Target | Today |
|---|---|---|
| CLS, every app page, 360 / 1440 / 1920 | **0.00** | 0.11–0.63 |
| Horizontal page scroll at 360 px | **none** | 4 pages |
| Text contrast, both themes (unit-tested) | **≥ 4.5:1** (≥ 3:1 for large text and UI glyphs) | 17 pairs below 4.5:1 (11 light, 6 dark) |
| Framer-motion shipped | **≈14 kB gz** (`m` + `domAnimation`) | 39.3 kB gz |
| Infinite decorative loops | **0**; only live and busy indicators loop | 6 |
| Reduced motion | No transforms, loops or chart draws; numbers show their final value | partial |
| Keyboard | Every control reachable with a visible focus ring; drawer and Copilot trap focus and close on Esc | gaps |
| `npm run lint` / `npm run build` / unit tests | 0 errors / pass / pass | 0 errors (2 warnings) / pass / none |

**Size and cadence.** Phase A is the bulk, roughly 15 new or changed shared files. If this session runs short, I'll finish A plus Runs and Run detail (the live-status work) first and hand over the rest with the harness, so it can be checked the same way.
