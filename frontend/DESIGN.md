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
- **Motion explains, it doesn't decorate.** Entrances, layout changes and live updates animate. Nothing loops except
  "live" indicators. Animation respects `prefers-reduced-motion`.

## Tokens (`src/app/globals.css`)
| Token | Light | Dark | Use |
|---|---|---|---|
| `--primary` | #2563EB | #3B82F6 | Actions, focus, active nav, chart 1 |
| `--violet` | #7C3AED | #8B5CF6 | AI accents, gradients, chart 2 |
| `--success` | #16A34A | #22C55E | Pass, healthy, ≥ 75 |
| `--warning` | #F59E0B | #F59E0B | Partial, 50–75 |
| `--critical` | #DC2626 | #EF4444 | Fail, blocking, < 50 |
| `--background` | #F6F7FB | #0B0F1A | Page |
| `--surface` | #FFFFFF | #111827 | Sidebar, topbar, glass |
| `--card` | #FFFFFF | #111827 (at 86 %, blurred) | Cards |
| `--muted-foreground` | #64748B | #94A3B8 | Secondary text |
| `--glow` | primary at 16 % | primary at 22 % | Hover glow, focus halo, spotlight |

Themes: light, dark and **system** (the default) via `next-themes`. Switch in the top bar or with ⌘K → "theme".

Surface utilities:
| Class | What it does |
|---|---|
| `.glass` | Frosted 72 % surface with an 18-px blur |
| `.surface-card` | The default `<Card>` |
| `.gradient-border` | Primary → violet 1-px border, for hero cards |
| `.app-backdrop` | Fixed mesh gradient plus SVG noise |
| `.spotlight` | Cursor-following glow, driven by `--mx` / `--my` |
| `.shimmer` | Skeleton loading |
| `.text-gradient` | Hero headline |
| `.kbd` | Keyboard hint |

Score bands are the same everywhere (`lib/insights.ts → band()`): **≥ 75 good · 50–75 warn · < 50 bad**.

## Motion system (`src/lib/motion.ts`)
**Durations:** instant 100 ms · fast 160 · base 240 · slow 400 · slower 600.

**Easing:**
- `out` [0.16, 1, 0.3, 1]: entrances;
- `inOut` [0.65, 0, 0.35, 1]: moves;
- `emphasized` [0.2, 0, 0, 1]: page.

**Springs:**
- `snappy` 420/34: hover and press;
- `gentle` 220/26: panels and sidebar;
- `bouncy` 500/18: buttons;
- `layout` 380/32: active-nav pill.

**Variants:** `fadeIn`, `fadeUp`, `scaleIn`, `slideInRight`, `page`, `stagger(step, delay)`, `listItem`, `overlay`, plus `hoverLift`
and `pressable` presets. Entrances use opacity and translate only, with no `filter: blur`: it is costly on top of glass.

| Where | Motion |
|---|---|
| Route change | `(app)/template.tsx`: fade + 8 px rise + 0.995 scale |
| Sidebar | Width spring 252 ↔ 76 px; labels fade and slide; the active pill moves with a shared `layoutId` |
| Cards | `MotionCard`: fade-up on enter, 2-px hover lift, glow shadow, cursor spotlight |
| Metrics | `CountUp` from the previous value (starting at 0) when it enters the viewport |
| Tables and feeds | `stagger(0.03–0.06)` on rows; live activity items slide in with `layout` |
| Charts | Recharts progressive draw (900–1400 ms); SVG health rings animate `strokeDashoffset` |
| Panels | Copilot slides in from the right (spring); palette and dialogs scale in over a blur; notifications stagger |
| Loading | Shimmer skeletons shaped like the final layout |
| Empty states | A gently floating illustration and one clear action |

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
│   ├── providers.tsx               ThemeProvider · React Query · MotionConfig(reducedMotion) · Tooltip · Toaster
│   ├── (app)/layout.tsx            auth gate → <AppShell>
│   ├── (app)/template.tsx          route transition
│   ├── (app)/dashboard/page.tsx    portfolio dashboard
│   ├── (app)/runs/page.tsx         filterable run history
│   └── api/
│       ├── copilot/route.ts        grounded Copilot (context from visible runs only)
│       ├── activity/route.ts       cross-run event stream
│       └── runs/[runId]/{logs,progress}/…
├── components/
│   ├── shell/       app-shell · sidebar · topbar · command-palette · copilot · notifications · nav
│   ├── motion/      motion-card · count-up · stagger
│   ├── dashboard/   brief-hero · kpi-tile · section · compliance-trend · health-scores · risk-heatmap ·
│   │                insights-feed · activity-timeline · status-overview · performance-matrix
│   └── ui/          shadcn primitives (+ popover); <Card> uses .surface-card
└── lib/
    ├── motion.ts      motion system
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
