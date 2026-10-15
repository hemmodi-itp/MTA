# Phase 10 CI benchmark — buggy_shop (2026-10-15)

**15/15 checks passed**

| Check | Result |
|---|---|
| A: exit 3 when the app is down | pass |
| A: no test ran | pass |
| B: exit 0 | pass |
| B: burn-in admitted every new test | pass |
| B: order check found no order-dependent test | pass |
| B: fingerprint saved | pass |
| C1: nothing changed -> no impacted test | pass |
| C1: only the smoke test ran | pass |
| C1: exit 0 | pass |
| C2: the edited spec's tests are selected and run | pass |
| C2: only smoke + impacted tests ran, fewer than nightly | pass |
| C2: exit 0 | pass |
| D1: a failing gating test -> exit 1 | pass |
| D2: the same test quarantined -> exit 0 | pass |
| D2: the report lists it as quarantined | pass |

| Stage run | Exit | Status | Passed | Failed | Seconds |
|---|---|---|---|---|---|
| A_app_down (pr) | 3 | environment_blocked | 0 | 0 | 2.3 |
| B_nightly (nightly) | 0 | success | 5 | 0 | 104.1 |
| unchanged (pr) | 0 | success | 1 | 0 | 8.2 |
| spec_edited (pr) | 0 | success | 2 | 0 | 9.9 |
| failing (release) | 1 | success | 5 | 1 | 18.4 |
| quarantined (release) | 0 | success | 5 | 1 | 27.8 |
