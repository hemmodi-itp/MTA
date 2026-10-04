# Interactive `--record` Flow — Current Behavior & Gaps

Captured for later reference when we redesign this flow. Reflects the codebase as of the
`AppEvolve2` branch, after the thread-safety fix to `InteractiveScanner` (launch → setup →
session loop → close now all run on one worker thread instead of three).

---

## Current step-by-step flow

**1. `python main.py --project <name> --module <id> --record`**
`main.py` sees `--record`, calls `run_interactive_recording(project, module)` from
`tools/discovery/record_cli.py`, and **exits immediately after** (`return 0`). The
`OrchestratorAgent` / normal workflow is never invoked — `--record` is a fully separate code
path from `full_workflow`.

**2. `record_cli.run_interactive_recording()`**
- Loads `project.yaml`, confirms `interactive_scan: true` (raises if not).
- Resolves the module's manifest via `load_project_manifest()` + `narrow_to_module()`:
  `url`, `setup_steps`, `auth`, `browser` — the exact same resolution `OrchestratorAgent`
  uses for a normal run.
- Resolves the output dir (`comprehension/modules/<id>/` or the flat `comprehension/` root
  for non-modular projects).
- Checks for a leftover `.scan_checkpoint.json` (only present if a *previous* session crashed
  mid-way) to decide whether to `resume`.
- Prints the recording banner (URL, output dir), then calls `scan_dom_interactive(...)`.

**3. `interactive_dom_scan.scan_dom_interactive()`**
Thin wrapper — builds an `InteractiveScanner`, calls `scanner.scan_interactive(...)`.

**4. `InteractiveScanner.scan_interactive()` → `_run_worker_bounded()`**
Everything below now runs on one dedicated worker thread (fixed from the original 3-thread
split, which violated Playwright sync API's single-thread requirement):

- **a. `self.launch(...)`** — starts Playwright, launches Chromium **headed**
  (`headless=False` is hardcoded for this class), opens a fresh context + page.
- **b. Setup steps run** (module's `setup_steps`, e.g. M02's SSO login sequence) — by the end
  the page is authenticated and sitting on the target URL.
- **c. `_setup_tracking(page)`** — exposes `__qaReportClick` / `__qaFinishRecording` to the
  page, registers `add_init_script` for the click-tracker JS and the recording-overlay banner
  JS (these apply on the **next** navigation only — they do not retroactively run against an
  already-loaded page), wires `page.on("request"/"close"/"crash")` and
  `browser.on("disconnected")`.
- **d. `_run_sessions(page, url)`**:
  - Immediately does `page.goto(url, wait_until="commit")` **again** — a second navigation to
    the same target URL. This re-navigation is what actually triggers the
    `add_init_script`-registered tracker/banner scripts to run for the first time. This is
    incidental, not documented as deliberate anywhere in the code — if this redundant `goto`
    were ever removed, the banner/tracker would silently stop being injected.
  - Polls `document.readyState` up to 15s (`_poll_page_ready`), then runs the **first
    full-page element scan** (`_scan_current_page`). `document.readyState === "complete"`
    fires early for an SPA shell, well before client-rendered UI actually mounts — observed in
    practice: a scan of the AppEvolve dashboard found only the injected "Finish Recording"
    banner button, because the real dashboard content hadn't rendered yet.
  - Enters a 0.3s poll loop: drains queued clicks (fed by `__qaReportClick`), does
    blast-radius scans around each click's container, checks `page.is_closed()`, loops
    **until `_stop_event` is set** — no timeout by design, so a human can take as long as they
    want.
  - Observed in practice: closing the browser window did **not** reliably fire
    `page.on("close")` → `_handle_page_close()` → `_stop_event.set()`. The loop kept waiting
    indefinitely; only `Ctrl+C` (SIGINT → `_on_signal()`) actually unblocked it.
- **e.** `_run_sessions` finalizes the current page, returns. The worker thread's `finally`
  calls `self.close()` — verified to complete cleanly once `_stop_event` is set (confirms the
  threading fix holds under real conditions).

**5. `save_dom_scan_interactive()`**
Writes `dom_elements.json` and `dom_intents.json` via plain `open(path, "w")` —
**unconditional overwrite**, no read-merge of whatever was already on disk for that module.
Same for `interactive/session.json` and `interactive/user_flows.json`.

**6. CLI prints "Recording complete" + file paths + the follow-up command, then exits.**
Nothing downstream runs automatically.

**7. (Separately, manually) `python main.py --project <name> --module <id>`**
Only this second, distinct command invokes `OrchestratorAgent` → `DiscoveryAgent._run_both()`
→ since `interactive_scan: true`, `_read_recorded_scan()` just reads the files step 5 wrote
(no browser) → runs `ComprehensionAgent` on the BRD in parallel → continues into
`testdata` → `semantic_map` → `script_generation` → `ui_execution` → `healing` → `reporting`
per the workflow definition.

---

## Confirmed gaps / open items for redesign

1. **`--record` is fully disconnected from the orchestrator.** It's a standalone branch in
   `main.py` that exits before the workflow loader is touched. The desired end state
   (per user): recording should feed into the *same* orchestrated flow — comprehension from
   BRD, test data generation, script generation, execution — rather than requiring a manual
   second command afterward.

2. **Overwrite instead of append/merge** on every artifact `--record` writes
   (`dom_elements.json`, `dom_intents.json`, `session.json`, `user_flows.json`). Re-recording
   a module discards everything a prior completed recording captured. Violates the project's
   "never overwrite, always append artifacts" rule.

3. **Close/disconnect detection is unreliable.** Closing the browser window did not reliably
   set `_stop_event`; only `Ctrl+C` did. No verified working path to a normal, non-forced
   finish (the "Finish Recording" banner's reliability is unverified — the banner *was*
   present in the DOM per the incidental re-navigation in 4d, but whether clicking it actually
   ends the session cleanly hasn't been confirmed in a real run).

4. **Scan-timing gap for SPA dashboards.** `_poll_page_ready`'s `document.readyState` check
   isn't a reliable readiness signal for client-rendered apps — the initial element scan can
   run before real content exists, capturing only scaffolding (e.g. just the recording
   banner).

None of items 1–4 have been fixed yet — this document is the reference point for that follow-up work.
