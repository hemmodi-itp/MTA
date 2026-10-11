# MTA design system and app shell

This document explains the 2026 redesign of the web app: what it aims for, the tokens, the motion system, the information
architecture and where each piece lives. All numbers on screen come from real evaluations. Nothing in the UI is mock data.

## Principles
- **Facts first.** Each surface answers one question in under 5 seconds. The dashboard answers "what needs me, and why?"
  through a hero brief, then KPIs, then detail.
- **Dense, not crowded.** 8-px rhythm, 16–24 px card padding, `tabular-nums` for every metric, 11-px uppercase
  eyebrow labels for hierarchy.
- **AI-native, never vague.**
  - ⌘K understands plain language, and ⌘J opens a Copilot that answers only from your data.
  - Insights are deterministic rules over real numbers.
- **Motion explains, it doesn't decorate.** Entrances, state changes and live updates animate. Nothing loops except
  "live" and "busy" indicators. Animation respects `prefers-reduced-motion`.

## Tokens (`src/app/globals.css`)
| Token | Light | Dark | Use |
|---|---|---|---|
| `--primary` | #2563EB | #3B82F6 | Links, focus rings, active nav, chart 1 (text-safe on cards) |
| `--primary-solid` | #2563EB | #2563EB | Filled buttons: white text stays ≥ 4.5:1 in both themes |
| `--violet` | #7C3AED | #8B5CF6 | AI accents, gradients, chart 2, "healed" |
| `--background` / `--surface` / `--card` | #F6F7FB / #FFF / #FFF | #0B0F1A / #111827 / #111827 (86 %, blurred) | Page, glass, cards |
| `--muted-foreground` | #5B6B81 | #94A3B8 | Secondary text (≥ 4.5:1 on page, card and muted) |
| `--glow` | primary at 16 % | primary at 22 % | Hover glow, spotlight |

**Status tones.** Seven tones — `success · warning · critical · info · neutral · violet · orange` — each with
`--{tone}` (fill, dot, bar, chart) and `--{tone}-fg` (text: ≥ 4.5:1 on the card *and* on its own tint, both themes).
Use them through the utilities: set one `tone-{name}`, then `tone-text`, `tone-tint`, `tone-border`, `tone-fill`
(`pill` is the status-pill shell). Plain Tailwind classes exist too (`text-success-fg`, `bg-critical-solid`…).
`src/app/design-tokens.test.ts` fails if any text token drops below AA.

**Status registry** (`src/lib/status.ts`): every run, test and step status and risk level maps to one of eight
semantic statuses, each with one tone and icon — passed ✓ success · failed ✕ critical · running (live dot) info ·
queued (clock) neutral · inconclusive (?) warning · skipped (−) neutral · flaky (shuffle) orange · healed (wand) violet.
`StatusPill` and every list read it; never hand-write status colours.

**Other scales:** radius `--radius` 12 px (cards `rounded-2xl`, inner tiles `rounded-xl`, controls `rounded-lg`, pills
full) · elevation `shadow-control / card / card-hover / popover / overlay` · type roles `type-page-title`,
`type-section-title`, `type-eyebrow`, `type-kpi(-sm)` plus `text-2xs` (11 px) · stacking `--z-sticky 30 · sidebar 40 ·
drawer 50 · panel 55 · modal 60 · popover 70 · toast 80 · tooltip 90` (use as `z-(--z-modal)`).

Themes: light, dark and **system** (the default) via `next-themes`. Switch in the sidebar or with ⌘K → "theme".

Surface utilities:
| Class | What it does |
|---|---|
| `.glass` | Frosted 72 % surface with an 18-px blur |
| `.surface-card` | The default `<Card>` |
| `.gradient-border` | Primary → violet 1-px border, for hero cards |
| `.app-backdrop` | Fixed mesh gradient plus SVG noise |
| `.spotlight` | Cursor-following glow, driven by `--mx` / `--my` |
| `.skeleton` | Loading block; the highlight sweeps with a transform |
| `card-elevate` | Hover shadow on a pseudo-element (only its opacity animates) |
| `.text-gradient` | Hero headline |
| `.kbd` | Keyboard hint |

Score bands are the same everywhere (`lib/insights.ts → band()`, as tones via `BAND_TONE`): **≥ 75 good · 50–75 warn ·
< 50 bad**.

## Motion system (`src/lib/motion.ts`, `src/components/motion/`)
Rules: motion explains a state change; animate **transform and opacity only**; micro-interactions **120–200 ms**,
panels and pages **200–350 ms**; **ease-out in, ease-in out** (exits shorter); lists stagger 30 ms and only the
**first 20 items** animate. Charts, rings and count-ups may run up to 600–900 ms (data, not chrome).

**Tokens:** `duration` fast 0.12 · micro 0.16 · exit 0.14 · panel 0.24 · page 0.28 s (CSS: `--dur-*`).
**Easing:** `enter` [0.16, 1, 0.3, 1] · `exit` [0.4, 0, 1, 1] · `move` [0.65, 0, 0.35, 1] (CSS: `ease-enter`…).
**Bundle:** `<MotionProvider>` = `LazyMotion` with `domAnimation` (`strict`: use `m.*`, never `motion.*`) +
`MotionConfig reducedMotion="user"`. `domAnimation` has no layout/drag, so shared-element indicators use
`<IndicatorGroup>`/`<Indicator>` (a FLIP with transforms, the only spring in the app — critically damped).
**Reduced motion:** framer drops transforms; `usePrefersReducedMotion()` turns off Recharts draws, count-ups and smooth
scrolling; a global CSS rule ends every CSS animation/transition at once (live dots go still).

| Where | Motion |
|---|---|
| Route change | `PageTransition` (in `(app)/template.tsx`): fade + 8 px rise, keyed by path so list → detail animates |
| Sidebar | Active item: sliding `Indicator`. Collapse: width snaps (CSS, from `html[data-sidebar]`), labels fade back in |
| Tabs / segmented filters | Sliding `Indicator`; panels fade in |
| Cards | `MotionCard`: fade-up inside a `Stagger`; interactive ones lift 2 px with a pseudo-element shadow |
| Metrics | `CountUp` (rAF, fixed width, final value for screen readers) |
| Lists and tables | `Stagger` / `itemMotion(i)`: 30 ms steps, first 20 rows only |
| Progress and scores | `ProgressBar` / `ScoreBar`: translateX fill, eased value changes, live sheen while running |
| Live run | Active step tinted + pulse ring; step icons swap with a scale/fade; `LiveDot` on running pills; new log lines fade |
| Charts | `ChartReveal` (fade + rise) and a ≤ 600 ms series draw |
| Panels | Copilot slides in (Esc closes, focus returns); dialogs/sheets/popovers use Radix presence with token timings |
| Expand / collapse | `Collapse` and accordions: no height tween — content fades in with a 4 px drop |
| Loading | Skeletons shaped like the final layout (no spinners for page content) |
| Empty states | Static icon, one clear action |

## Information architecture
```
Shell
├── Sidebar (floating, collapsible, mobile drawer)
│   ├── Brand
│   ├── Workspace scope: All / My projects / Samples (filters the dashboard)
│   ├── Workspace: Dashboard · Projects · Runs (live count) · Test cases · Reports
│   ├── AI actions: New evaluation · Ask Copilot (⌘J) · Command palette (⌘K)
│   └── Settings · Profile (log out)
├── Topbar (sticky glass)
│   ├── Page title
│   ├── Search or ask (opens ⌘K)
│   ├── Live "N running" indicator
│   ├── Notifications
│   ├── Theme
│   └── Copilot
├── ⌘K Command palette
│   ├── Ask MTA: natural-language intents (lib/nl-query.ts), plus "Ask Copilot"
│   ├── Navigate · Projects · Recent runs
│   └── Actions: new evaluation, Copilot, sidebar, theme
└── ⌘J Copilot drawer
    └── Context-aware (run / project / portfolio); grounded answers via /api/copilot → evaluation service → Gemini;
        action intents shown as confirm buttons

Dashboard (/dashboard)
├── 1. AI brief hero: headline and supporting facts (lib/insights.ts → brief); quick actions
├── 2. KPIs: BRD compliance (Δ + sparkline) · Runtime verified · Runtime pass rate · Blocking gates
├── 3. Compliance trend (14 days, line + volume) │ Project health (score rings, riskiest first)
├── 4. Risk heatmap (projects × 8 dimensions) │ AI insights (risks, regressions, recommendations)
└── 5. Status overview (donut) │ Performance matrix (tests, depth) │ Live activity (cross-run events)

Runs (/runs): status tabs + URL filters (status, since, q, minScore, maxScore, gate), removable chips, staggered table.
```

Natural-language examples, all deterministic and all landing on real filtered pages:
- "failed runs from yesterday", "runs below 50", "blocked runs last week", "BRD_Agent runs", "failed tests";
- "re-run BRD_Agent", "generate report", "new evaluation".

## Folder structure
```
src/
├── app/
│   ├── globals.css                 tokens, themes, surface utilities
│   ├── providers.tsx               ThemeProvider · React Query · MotionProvider (LazyMotion + MotionConfig) · Tooltip · Toaster
│   ├── design-tokens.test.ts       WCAG AA guard for the colour tokens
│   ├── (app)/layout.tsx            auth gate → <AppShell>
│   ├── (app)/template.tsx          route transition (PageTransition)
│   ├── (app)/dashboard/page.tsx    portfolio dashboard
│   ├── (app)/runs/page.tsx         filterable run history
│   └── api/
│       ├── copilot/route.ts        grounded Copilot (context from visible runs only)
│       ├── activity/route.ts       cross-run event stream
│       └── runs/[runId]/{logs,progress}/…
├── components/
│   ├── shell/       app-shell · sidebar · topbar · command-palette · copilot · notifications · nav
│   ├── motion/      motion-provider · page-transition · stagger · sliding-indicator · count-up · progress-bar ·
│   │                chart-reveal · collapse · live-dot · motion-card
│   ├── shared/      page-header · section-card · kpi-card · status-pill · score · skeletons · empty-state ·
│   │                error-state · notice · segmented-control
│   ├── dashboard/   brief-hero · compliance-trend · health-scores · risk-heatmap · insights-feed ·
│   │                activity-timeline · status-overview · performance-matrix · recent-runs-list
│   └── ui/          shadcn primitives (+ popover, radio-group); <Card> uses .surface-card, Tabs host the sliding indicator
└── lib/
    ├── motion.ts      motion system (tokens, presets, FLIP + count-up math)
    ├── status.ts      status registry: status → semantic status → tone
    ├── insights.ts    portfolio analytics, brief, insights, heatmap rows (pure functions over runs)
    ├── nl-query.ts    natural language → intents
    └── stores/ui-store.ts   zustand: sidebar, workspace scope, palette/Copilot, notifications (persisted prefs)
```

## Responsive
| Width | Layout |
|---|---|
| ≥ 1440 | Full grid: the bottom row is 3 / 5 / 4 columns, and the duration column shows from 2xl |
| ≥ 1024 | Two-column rows (`xl:` splits); the sidebar floats |
| ≥ 768 | The sidebar collapses to 76 px on demand; panels stack |
| 390 | The sidebar becomes a slide-in drawer (topbar ☰); the Copilot goes full width; tables scroll horizontally inside their card |
