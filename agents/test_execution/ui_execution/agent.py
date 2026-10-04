"""
UIExecutionAgent — runs Playwright TypeScript .spec.ts files (or pytest .py files).

Mode selection:
    TypeScript mode — any .spec.ts found in test_scripts/ → `npx playwright test`
    Python mode     — only .py files present → `pytest` (backward compat)

TypeScript mode behaviours:
    - Positional scripts_dir arg limits execution to this project's tests only
      (fixes "all projects' tests run" when PW_TEST_DIR spans multiple projects)
    - Streams stdout so test progress is visible in real time
    - Handles KeyboardInterrupt gracefully: summarises all completed tests and
      marks unstarted tests as "skipped" with a reason comment
    - Browser-close errors are marked as "skipped" (not failed) with comment
    - 3+ consecutive no-interaction browser closes switch remaining specs to
      headless (mirrors original PlaywrightScanner loop behaviour):
        · A browser close counts as "no interaction" when the FIRST attempt
          duration is < NO_INTERACTION_MAX_MS (browser closed before any
          action in the spec could complete)
        · Counter resets on any non-browser-close result or on a browser-close
          where interaction DID occur (longer first-attempt duration)
        · On hitting 3: all specs from that point onward are re-run headless
    - Headed mode uses --workers=1 (one browser window at a time)
    - Results written to test_execution/reports/json/{timestamp}_results.json

Output (both modes):
    {
        "module": "ui_execution",
        "suite": "<project>",
        "mode": "playwright" | "pytest",
        "passed": N, "failed": N, "skipped": N,
        "returncode": N,
        "results": [...],
        "report_json": "<path>",
    }
"""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import BaseAgent
from tools.shared import get_logger
from tools.constants import PROJECTS_BASE as _ASSETS_BASE

# ── Constants ─────────────────────────────────────────────────────────────────

# First-attempt duration below which a browser-close is considered
# "no interaction occurred" (browser was closed before any Playwright
# action in the spec could complete).  Generous at 5 s to handle slow
# initial page navigations.
_NO_INTERACTION_MAX_MS = 5_000

_BROWSER_CLOSE_COMMENT = "Browser closed by user — skipped"
_INTERRUPT_COMMENT = "Execution was interrupted before this test ran"

_BROWSER_CLOSE_PATTERNS = [
    "target closed",
    "page has been closed",
    "browser has been closed",
    "browser was disconnected",
    "browser disconnected",
    "connection closed",
    "session closed",
    "target crashed",
    "target page, context or browser has been closed",
]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Playwright list-reporter output line after ANSI stripping:
#   "  ✓  1 [chromium-headed] › path/to/test.spec.ts › Test title (1.2s)"
_LIST_RESULT_RE = re.compile(
    r"^\s*([✓✔✗✘×\-·○])"
    r"\s+\d+\s+"
    r"\[[\w\-]+\]"
    r"\s*[›>]\s*"
    r"(.+?\.spec\.ts)"
    r"\s*[›>]\s*"
    r"(.+?)(?:\s+\([\d.]+[smh]+\))?\s*$"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


def _is_browser_close_error(text: str) -> bool:
    t = text.lower()
    return any(pat in t for pat in _BROWSER_CLOSE_PATTERNS)


def _count_results(results: List[Dict]) -> Tuple[int, int, int]:
    passed = sum(1 for r in results if r.get("status") in ("success", "expected"))
    failed = sum(1 for r in results if r.get("status") == "failed")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    return passed, failed, skipped


def _find_scripts(scripts_dir: str, suffix: str) -> List[str]:
    """Recursively find files under scripts_dir ending in suffix, returned as
    paths relative to scripts_dir. Modular projects nest specs one level down
    (test_scripts/M01/*.spec.ts, test_scripts/M02/*.spec.ts, …) — a flat
    os.listdir() would miss everything when no --module filter narrows
    scripts_dir down to a single module subdirectory."""
    found = []
    for root, _dirs, files in os.walk(scripts_dir):
        for f in files:
            if f.endswith(suffix):
                found.append(os.path.relpath(os.path.join(root, f), scripts_dir))
    return sorted(found)


# ── Agent ─────────────────────────────────────────────────────────────────────

class UIExecutionAgent(BaseAgent):
    MODULE_NAME = "ui_execution"

    def __init__(self, _provider=None, settings: Optional[Dict] = None):
        self.settings = settings or {}
        self.logger = get_logger("agent.ui_execution")

    def execute(self, request: dict, _state: dict) -> Dict[str, Any]:
        project_name = request.get("project_name") or request.get("message", "project")
        safe = _safe_name(project_name)
        headless = request.get("headless", True)
        # Orchestrator already resolved the active module's URL (project.yaml
        # modules[].url, narrowed by --module) onto request["url"] — forward it
        # as BASE_URL so playwright.config.ts doesn't have to re-derive it by
        # regex-scraping project.yaml (which can't tell modules apart anyway).
        base_url = request.get("url")

        self._log(f"Starting — project='{project_name}' headless={headless}")

        scripts_dir = os.path.join(_ASSETS_BASE, safe, "test_creation", "test_scripts")
        reports_dir = os.path.join(_ASSETS_BASE, safe, "test_execution", "reports")

        # Suite-based execution: resolve suite → specific spec file paths
        suite_name = request.get("suite")
        if suite_name:
            from tools.suite_orchestrator import resolve_suite_spec_files
            project_dir = os.path.join(_ASSETS_BASE, safe)
            try:
                resolved = resolve_suite_spec_files(project_dir, suite_name)
            except FileNotFoundError as exc:
                msg = str(exc)
                self._log(msg, level="error")
                return {"module": "ui_execution", "status": "failed", "error": msg}

            if not resolved:
                msg = f"Suite '{suite_name}' resolved to zero spec files — check suite scenarios against test_suite.json"
                self._log(msg, level="warning")
                return {"module": "ui_execution", "status": "skipped", "reason": msg}

            summary = [
                os.path.basename(str(e["path"])) + (f' [grep={e["grep"]}]' if e["grep"] else "")
                for e in resolved
            ]
            self._log(f"Suite '{suite_name}' — {len(resolved)} spec(s): {summary}")
            return self._run_suite(
                resolved=resolved,
                project_name=project_name,
                safe=safe,
                scripts_dir=scripts_dir,
                reports_dir=reports_dir,
                headless=headless,
                auth_config=request.get("auth_config"),
                auth_storage_state=request.get("auth_storage_state", ""),
                base_url=base_url,
            )

        # Direct spec-file targeting: re-run only these specs (relative to
        # scripts_dir), skipping suite/module resolution entirely. Used by
        # HealingAgent's run_tests tool to verify a patch without re-running
        # the whole project. Mirrors the private spec_files plumbing
        # _run_suite already passes to _run_playwright, just reachable here
        # from the public execute() surface.
        spec_files = request.get("spec_files")
        if spec_files:
            abs_paths = [os.path.join(scripts_dir, sf).replace(os.sep, "/") for sf in spec_files]
            ts_files = [sf for sf in spec_files if sf.endswith(".spec.ts")]
            self._log(f"spec_files targeting — {len(abs_paths)} spec(s): {ts_files}")
            return self._run_playwright(
                project_name=project_name,
                safe=safe,
                scripts_dir=scripts_dir,
                reports_dir=reports_dir,
                ts_files=ts_files,
                headless=headless,
                auth_config=request.get("auth_config"),
                auth_storage_state=request.get("auth_storage_state", ""),
                spec_files=abs_paths,
                base_url=base_url,
            )

        # When module_filter is set, scope execution to that module's subdirectory
        module_filter = request.get("module_filter")
        if module_filter:
            module_scripts_dir = os.path.join(scripts_dir, module_filter)
            if os.path.isdir(module_scripts_dir):
                self._log(f"Module filter '{module_filter}' — scoping to '{module_scripts_dir}'")
                scripts_dir = module_scripts_dir
            else:
                self._log(f"Module dir '{module_scripts_dir}' not found — falling back to full test_scripts/", level="warning")

        if not os.path.isdir(scripts_dir):
            msg = f"test_scripts dir not found: '{scripts_dir}'. Run script_generation first."
            self._log(msg, level="error")
            return {"module": "ui_execution", "status": "failed", "error": msg}

        # Recursive: scripts_dir may contain per-module subdirectories (M01/, M02/, …)
        # when no --module filter narrowed it down to a single one.
        ts_files = _find_scripts(scripts_dir, ".spec.ts")
        py_files = _find_scripts(scripts_dir, ".py")

        if ts_files:
            return self._run_playwright(
                project_name=project_name,
                safe=safe,
                scripts_dir=scripts_dir,
                reports_dir=reports_dir,
                ts_files=ts_files,
                headless=headless,
                auth_config=request.get("auth_config"),
                auth_storage_state=request.get("auth_storage_state", ""),
                base_url=base_url,
            )
        elif py_files:
            self._log(
                f"No .spec.ts files found — falling back to pytest for {len(py_files)} .py file(s)",
                level="warning",
            )
            return self._run_pytest_compat(
                project_name=project_name,
                safe=safe,
                scripts_dir=scripts_dir,
                py_files=py_files,
                headless=headless,
            )
        else:
            msg = f"No .spec.ts or .py test files found in '{scripts_dir}'."
            self._log(msg, level="error")
            return {"module": "ui_execution", "status": "failed", "error": msg}

    # ── Suite execution (handles no-grep batch + per-grep individual runs) ────────

    def _run_suite(
        self,
        resolved: List[Dict],
        project_name: str,
        safe: str,
        scripts_dir: str,
        reports_dir: str,
        headless: bool,
        auth_config: Optional[dict] = None,
        auth_storage_state: str = "",
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Entries without grep are batched into one Playwright call.
        # Entries with grep each get their own Playwright call (grep is per-file).
        no_grep = [e for e in resolved if not e["grep"]]
        with_grep = [e for e in resolved if e["grep"]]

        runs: List[Dict[str, Any]] = []

        if no_grep:
            sf = [str(e["path"]) for e in no_grep]
            tf = [os.path.basename(p) for p in sf]
            runs.append(self._run_playwright(
                project_name=project_name, safe=safe,
                scripts_dir=scripts_dir, reports_dir=reports_dir,
                ts_files=tf, headless=headless,
                auth_config=auth_config, auth_storage_state=auth_storage_state,
                spec_files=sf, base_url=base_url,
            ))

        for entry in with_grep:
            sf = [str(entry["path"])]
            tf = [os.path.basename(sf[0])]
            self._log(f"Grep run: {tf[0]} — grep='{entry['grep']}'")
            runs.append(self._run_playwright(
                project_name=project_name, safe=safe,
                scripts_dir=scripts_dir, reports_dir=reports_dir,
                ts_files=tf, headless=headless, base_url=base_url,
                auth_config=auth_config, auth_storage_state=auth_storage_state,
                spec_files=sf, grep_pattern=entry["grep"],
            ))

        if len(runs) == 1:
            return runs[0]

        # Merge multiple runs into one result
        merged: List[Dict] = []
        passed = failed = skipped = 0
        for r in runs:
            merged.extend(r.get("results", []))
            passed += r.get("passed", 0)
            failed += r.get("failed", 0)
            skipped += r.get("skipped", 0)

        last = runs[-1]
        return {
            **last,
            "results": merged,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "scenarios_executed": passed + failed + skipped,
        }

    # ── TypeScript / Playwright ────────────────────────────────────────────────

    def _run_playwright(
        self,
        project_name: str,
        safe: str,
        scripts_dir: str,
        reports_dir: str,
        ts_files: List[str],
        headless: bool,
        auth_config: Optional[dict] = None,
        auth_storage_state: str = "",
        spec_files: Optional[List[str]] = None,
        grep_pattern: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._log(f"TypeScript mode — {len(ts_files)} spec(s) found")

        # Dependencies must be installed ahead of time (see README Quick Start).
        # No installs are performed during execution — locked-down client servers
        # often have no outbound network access mid-run.
        if not _playwright_package_installed():
            msg = (
                "Playwright is not installed. Run `npm install` once before "
                "executing tests (see README Quick Start)."
            )
            self._log(msg, level="error")
            return {"module": "ui_execution", "status": "failed", "error": msg}

        # Report paths
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_report_dir = os.path.join(reports_dir, "json")
        html_report_dir = os.path.join(reports_dir, "html", ts)
        os.makedirs(json_report_dir, exist_ok=True)
        os.makedirs(html_report_dir, exist_ok=True)
        json_report_path = os.path.join(json_report_dir, f"{ts}_results.json")

        # Fix 5: one browser window at a time in headed mode
        workers = "1" if not headless else "2"

        # When spec_files is set (suite run), pass individual paths; otherwise pass the directory
        if spec_files:
            targets = [p.replace(os.sep, "/") for p in spec_files]
        else:
            targets = [scripts_dir.replace(os.sep, "/")]   # Fix 1: forward slashes on Windows

        cmd = [
            "npx", "playwright", "test",
            *targets,
            "--config", "playwright.config.ts",
            "--project=chromium",
            *(["--headed"] if not headless else []),
            f"--workers={workers}",
            *(["--grep", grep_pattern] if grep_pattern else []),
            # --reporter omitted: playwright.config.ts already declares json+html reporters;
            # adding it here would override the whole array and break the file output.
            f"--output={os.path.join(reports_dir, 'html', ts)}",
        ]

        env = {
            **os.environ,
            "PW_PROJECT": safe,
            "PW_TEST_DIR": _ASSETS_BASE,
            "PW_JSON_REPORT": json_report_path,
            "PW_HTML_REPORT": html_report_dir,
        }
        if base_url:
            # Already resolved by the orchestrator for the active module — takes
            # priority over playwright.config.ts's own project.yaml regex-scrape,
            # which can't tell modules apart and silently falls back to
            # localhost:3000 when it can't find a match.
            env["BASE_URL"] = base_url
        if auth_config and auth_config.get("strategy") == "live_login":
            fresh_state = self._capture_live_auth(auth_config)
            if fresh_state:
                env["PW_STORAGE_STATE"] = fresh_state
                self._log(f"live_login: fresh auth state → PW_STORAGE_STATE='{fresh_state}'")
        elif auth_storage_state:
            env["PW_STORAGE_STATE"] = auth_storage_state
            self._log(f"Auth state injected → PW_STORAGE_STATE='{auth_storage_state}'")

        self._log(f"Running: {' '.join(cmd)}")
        # Fix 2: stream stdout; handle KeyboardInterrupt gracefully.
        # No outer timeout — Playwright's own per-test timeout + retries
        # (playwright.config.ts) already bound the run; an additional
        # suite-level kill here only discards real, already-completed results.
        stdout, stderr, interrupted, returncode = _stream_proc(
            cmd, cwd=os.getcwd(), env=env, logger=self.logger
        )
        self._log(f"npx playwright test exit code: {returncode}")

        # Fix 2: interrupted — return partial summary without losing what ran
        if interrupted:
            self._log("Execution interrupted — summarising partial results", level="warning")
            return self._handle_interrupt(
                ts_files, scripts_dir, json_report_path,
                reports_dir, html_report_dir, ts, safe, stdout,
            )

        if returncode != 0:
            combined = (stderr or "") + (stdout or "")
            if combined.strip():
                self._log(
                    f"Playwright output (first 3000 chars):\n{combined[:3000]}",
                    level="warning",
                )

        if returncode == 4:
            self._log(
                "Exit code 4: no tests collected — check testMatch glob and .spec.ts paths.",
                level="warning",
            )

        # Chromium browser binary must be installed ahead of time — no installs
        # during execution (see README Quick Start).
        binary_missing = (
            "Executable doesn't exist" in (stderr + stdout)
            or "browserType.launch" in (stderr + stdout)
        )
        if returncode != 0 and binary_missing:
            msg = (
                "Playwright's Chromium browser binary is not installed. Run "
                "`npx playwright install chromium` once before executing tests "
                "(see README Quick Start)."
            )
            self._log(msg, level="error")
            return {"module": "ui_execution", "status": "failed", "error": msg, "returncode": returncode}

        # Parse JSON results
        results, _, _ = _parse_playwright_json(json_report_path, self.logger)

        if not results:
            if returncode == 4:
                # Genuine "no tests collected" — a config/glob problem, not a
                # partial run. Every spec file really did get zero attempts,
                # so a synthetic "failed" placeholder per spec is accurate here.
                self._log(
                    f"No test results collected — creating {len(ts_files)} synthetic failure(s)",
                    level="warning",
                )
                for spec in ts_files:
                    results.append({
                        "spec_file": spec,
                        "test_title": "No tests collected",
                        "status": "failed",
                        "duration_ms": 0,
                        "first_attempt_duration_ms": 0,
                        "errors": ["No tests were executed — verify testMatch glob and spec file paths"],
                        "comment": "No tests collected",
                        "no_interaction_close": False,
                    })
            else:
                # The run ended without a clean JSON report for some other
                # reason (crash, external kill, network drop, unexpected
                # non-zero exit) — recover real progress from the streamed
                # list-reporter stdout instead of fabricating blanket failures
                # for tests that may have already passed.
                self._log(
                    "No JSON report produced — recovering real progress from streamed output",
                    level="warning",
                )
                results = _recover_partial_results(ts_files, json_report_path, stdout, self.logger)

        # Fix 3: mark browser-close failures as skipped, tagging interaction info
        results, browser_close_count = _mark_browser_close_as_skipped(results)

        # Fix 4: if 3 consecutive no-interaction browser closes occurred in a headed
        # run, re-run all specs from that point onward in headless mode
        if browser_close_count >= 3 and not headless:
            threshold_idx = _find_headless_threshold(results)
            if threshold_idx >= 0:
                sorted_results = sorted(results, key=lambda r: r.get("spec_file", ""))
                specs_to_rerun = [
                    os.path.basename(r["spec_file"])
                    for r in sorted_results[threshold_idx:]
                ]
                self._log(
                    f"3 consecutive no-interaction browser close(s) at index {threshold_idx} — "
                    f"switching {len(specs_to_rerun)} remaining spec(s) to headless",
                    level="warning",
                )
                results = self._rerun_headless(
                    results=sorted_results,
                    threshold_idx=threshold_idx,
                    scripts_dir=scripts_dir,
                    reports_dir=reports_dir,
                    env=env,
                )

        passed, failed, skipped = _count_results(results)
        _update_report_index(reports_dir, ts, json_report_path, html_report_dir, passed, failed)
        self._log(f"Done — passed={passed} failed={failed} skipped={skipped}")
        return {
            "module": "ui_execution",
            "status": "success",
            "suite": safe,
            "mode": "playwright",
            "scenarios_executed": passed + failed + skipped,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "returncode": returncode,
            "results": results,
            "report_json": json_report_path,
            "report_html": html_report_dir,
        }

    # ── Fix 2: interrupted partial summary ────────────────────────────────────

    def _handle_interrupt(
        self,
        ts_files: List[str],
        scripts_dir: str,
        json_report_path: str,
        reports_dir: str,
        html_report_dir: str,
        ts: str,
        safe: str,
        stdout: str,
    ) -> Dict[str, Any]:
        results = _recover_partial_results(ts_files, json_report_path, stdout, self.logger)
        passed, failed, skipped = _count_results(results)
        _update_report_index(reports_dir, ts, json_report_path, html_report_dir, passed, failed)
        self._log(
            f"Interrupted summary — passed={passed} failed={failed} "
            f"not-started={skipped}"
        )
        return {
            "module": "ui_execution",
            "status": "interrupted",
            "suite": safe,
            "mode": "playwright",
            "scenarios_executed": passed + failed + skipped,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "returncode": 130,
            "results": results,
            "report_json": json_report_path,
            "report_html": html_report_dir,
        }

    # ── Fix 4: headless re-run from threshold ─────────────────────────────────

    def _rerun_headless(
        self,
        results: List[Dict],
        threshold_idx: int,
        scripts_dir: str,
        reports_dir: str,
        env: Dict[str, str],
    ) -> List[Dict]:
        """Re-run results[threshold_idx:] in headless mode and merge back."""
        # spec_file is already relative to scripts_dir (e.g. "M02/test_BS-001….spec.ts"
        # for a whole-project run, or just "test_BS-001….spec.ts" when --module scoped
        # scripts_dir down to a single module) — join it as-is, don't strip to basename
        # first, or nested module subdirectories get silently dropped from the path.
        specs_to_rerun = [
            r.get("spec_file", "")
            for r in results[threshold_idx:]
            if r.get("spec_file")
        ]

        spec_paths = []
        for spec in specs_to_rerun:
            full = os.path.join(scripts_dir, spec)
            if os.path.exists(full):
                spec_paths.append(full.replace(os.sep, "/"))

        if not spec_paths:
            return results

        ts2 = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        html2 = os.path.join(reports_dir, "html", f"{ts2}_headless_retry")
        json2 = os.path.join(reports_dir, "json", f"{ts2}_headless_retry.json")
        os.makedirs(html2, exist_ok=True)

        cmd2 = [
            "npx", "playwright", "test",
            *spec_paths,
            "--config", "playwright.config.ts",
            "--project=chromium",
            "--workers=2",
            f"--output={html2}",
        ]
        env2 = {**env, "PW_JSON_REPORT": json2, "PW_HTML_REPORT": html2}

        self._log(f"Headless re-run: {[os.path.basename(p) for p in spec_paths]}")
        _stream_proc(cmd2, cwd=os.getcwd(), env=env2, logger=self.logger)

        retry_results, _, _ = _parse_playwright_json(json2, self.logger)
        retry_by_basename = {os.path.basename(r["spec_file"]): r for r in retry_results}

        # Keep the headed results for specs before the threshold;
        # replace from threshold onward with headless results
        merged = list(results[:threshold_idx])
        for r in results[threshold_idx:]:
            basename = os.path.basename(r.get("spec_file", ""))
            if basename in retry_by_basename:
                updated = dict(retry_by_basename[basename])
                updated["comment"] = "Re-run headless after consecutive browser close(s)"
                merged.append(updated)
            else:
                merged.append(r)

        return merged

    # ── Live login helper ─────────────────────────────────────────────────────

    def _capture_live_auth(self, auth_config: dict) -> Optional[str]:
        """
        Perform a fresh browser login and save the session to a temp state file.
        Returns the path to the saved file, or None on failure.
        Called immediately before npx playwright test so the session is seconds old.
        """
        storage_state_path = auth_config.get("storage_state_path", "")
        if not storage_state_path:
            self._log("live_login: no storage_state_path configured — cannot capture state for tests", level="warning")
            return None

        auth_dir = os.path.dirname(storage_state_path)
        if auth_dir:
            os.makedirs(auth_dir, exist_ok=True)

        try:
            from playwright.sync_api import sync_playwright
            from tools.auth.live_login import perform_login

            self._log("live_login: capturing fresh auth state before test run...")
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()
                try:
                    perform_login(page, auth_config)
                    context.storage_state(path=storage_state_path)
                    self._log(f"live_login: auth state saved → '{storage_state_path}'")
                finally:
                    context.close()
                    browser.close()
            return storage_state_path
        except Exception as exc:
            self._log(f"live_login: failed to capture auth state — {exc}", level="warning")
            return None

    # ── Python / pytest backward-compat ───────────────────────────────────────

    def _run_pytest_compat(
        self,
        project_name: str,
        safe: str,
        scripts_dir: str,
        py_files: List[str],
        headless: bool,
    ) -> Dict[str, Any]:
        self._log(f"pytest compat mode — {len(py_files)} .py file(s)")
        _write_conftest(scripts_dir, self.logger)

        cmd = [sys.executable, "-m", "pytest", scripts_dir, "-v", "--tb=short", "--no-header"]
        if not headless:
            cmd.append("--headed")

        self._log(f"Running: {' '.join(cmd)}")
        proc = _run_proc(cmd, cwd=os.getcwd(), env=None, timeout=600, logger=self.logger)
        returncode = proc.returncode
        self._log(f"pytest exit code: {returncode}")

        results, passed, failed = _parse_pytest_output(proc.stdout + proc.stderr, {})
        skipped = sum(1 for r in results if r.get("status") == "skipped")
        self._log(f"Done — passed={passed} failed={failed} skipped={skipped}")
        return {
            "module": "ui_execution",
            "status": "success",
            "suite": safe,
            "mode": "pytest",
            "scenarios_executed": passed + failed + skipped,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "returncode": returncode,
            "results": results,
        }


# ── Playwright JSON parser ────────────────────────────────────────────────────

# Mirrors agents/orchestrator/agent.py's _SPEC_ID_RE — duplicated locally
# rather than imported to avoid a reverse dependency from test_execution back
# onto orchestrator. Matches both the legacy hyphenated scheme ("BS-001",
# "SC-001") and the current module-scoped scheme script_generation names
# specs with ("M03_BS_006").
_SPEC_ID_RE = re.compile(r"([A-Za-z]+\d+_BS_\d+|BS-\d+|SC-\d+)")


def _extract_test_case_id(spec_file: str) -> str:
    match = _SPEC_ID_RE.search(spec_file or "")
    return match.group(1) if match else ""


def _parse_playwright_json(
    json_path: str, logger
) -> Tuple[List[Dict], int, int]:
    if not os.path.exists(json_path):
        logger.warning(f"[UIExecutionAgent] Playwright JSON report not found: {json_path}")
        return [], 0, 0

    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning(f"[UIExecutionAgent] Could not read Playwright JSON: {exc}")
        return [], 0, 0

    results = []
    passed = 0
    failed = 0

    for suite in _iter_suites(data.get("suites", [])):
        for spec in suite.get("specs", []):
            spec_file = spec.get("file", "")
            spec_title = spec.get("title", "")

            for test in spec.get("tests", []):
                status = test.get("status", "")
                # "flaky" = failed on the first attempt but passed on retry —
                # Playwright's own summary counts it as a pass, not a failure.
                # Previously only "passed"/"expected" counted as ok, so a
                # flaky test's earlier failed attempt silently reported the
                # whole test as "failed" even though it ultimately succeeded.
                ok = status in ("passed", "expected", "flaky")
                if ok:
                    passed += 1
                else:
                    failed += 1

                test_results = test.get("results", [])
                errors = [
                    r.get("error", {}).get("message", "") or ""
                    for r in test_results
                    if r.get("error")
                ]
                # First-attempt duration used for "no-interaction" browser-close detection
                first_attempt_ms = test_results[0].get("duration", 0) if test_results else 0

                results.append({
                    "spec_file": spec_file,
                    "test_title": spec_title,
                    "test_case_id": _extract_test_case_id(spec_file),
                    "business_scenario_id": _extract_test_case_id(spec_file),
                    "status": "success" if ok else "failed",
                    "flaky": status == "flaky",
                    "duration_ms": test.get("duration", 0),
                    "first_attempt_duration_ms": first_attempt_ms,
                    "errors": errors,
                    "comment": "",
                    "no_interaction_close": False,
                })

    return results, passed, failed


def _iter_suites(suites: list):
    for suite in suites:
        yield suite
        for child in _iter_suites(suite.get("suites", [])):
            yield child


# ── Fix 3: browser-close → skipped ───────────────────────────────────────────

def _mark_browser_close_as_skipped(
    results: List[Dict],
) -> Tuple[List[Dict], int]:
    """
    Mark failed tests whose errors contain browser-close signatures as
    "skipped" with a comment.  Also tag no_interaction_close=True when the
    first-attempt duration is below the threshold (browser was closed before
    any action in the spec could complete).
    Returns (results, total_browser_close_count).
    """
    count = 0
    for r in results:
        if r.get("status") == "failed":
            if any(_is_browser_close_error(e) for e in r.get("errors", [])):
                r["status"] = "skipped"
                r["comment"] = _BROWSER_CLOSE_COMMENT
                # Treat as "no interaction" when first attempt was very short
                first_ms = r.get("first_attempt_duration_ms", 0)
                r["no_interaction_close"] = first_ms < _NO_INTERACTION_MAX_MS
                count += 1
    return results, count


# ── Fix 4: find the headless switch threshold ─────────────────────────────────

def _find_headless_threshold(results: List[Dict]) -> int:
    """
    Walk results sorted by spec_file name and count consecutive
    no-interaction browser closes.

    Returns the index of the FIRST spec that should run headless — i.e. the
    test AFTER the 3rd consecutive no-interaction close (mirroring the
    original PlaywrightScanner loop where headless was enabled for
    subsequent tests, not for the 3 that triggered the switch).

    Returns -1 if the threshold was never hit or there is nothing left to
    re-run after the trigger.
    """
    sorted_r = sorted(results, key=lambda r: r.get("spec_file", ""))
    consecutive = 0
    for i, r in enumerate(sorted_r):
        if r.get("no_interaction_close"):
            consecutive += 1
            if consecutive >= 3:
                next_idx = i + 1
                # Nothing left after the 3rd close — nothing to re-run
                return next_idx if next_idx < len(sorted_r) else -1
        else:
            consecutive = 0
    return -1


# ── Fix 2: list-reporter stdout parser ────────────────────────────────────────

def _parse_list_output(stdout: str) -> Tuple[List[Dict], set]:
    """Parse Playwright list-reporter lines for partial results on interrupt."""
    results: List[Dict] = []
    seen: set = set()

    for raw in stdout.splitlines():
        line = _strip_ansi(raw)
        m = _LIST_RESULT_RE.match(line)
        if not m:
            continue
        char = m.group(1)
        spec_file = os.path.basename(m.group(2).strip())
        test_title = m.group(3).strip()

        if char in ("✓", "✔"):
            status = "success"
        elif char in ("✗", "✘", "×"):
            status = "failed"
        else:
            status = "skipped"

        seen.add(spec_file)
        results.append({
            "spec_file": spec_file,
            "test_title": test_title,
            "status": status,
            "duration_ms": 0,
            "first_attempt_duration_ms": 0,
            "errors": [],
            "comment": "",
            "no_interaction_close": False,
        })

    return results, seen


def _recover_partial_results(
    ts_files: List[str],
    json_report_path: str,
    stdout: str,
    logger,
) -> List[Dict[str, Any]]:
    """
    Recover real per-test results whenever a run didn't end with a clean,
    fully-written JSON report — a KeyboardInterrupt, a crash, an external
    kill, a network drop, or any other non-graceful exit. Prefers the JSON
    report (may be fully or partially written), falls back to parsing the
    already-streamed list-reporter stdout lines, and marks only specs that
    genuinely never started as "skipped" — never fabricates "failed" for a
    test that may have already passed.
    """
    results, _, _ = _parse_playwright_json(json_report_path, logger)
    results, _ = _mark_browser_close_as_skipped(results)

    completed_basenames = {os.path.basename(r.get("spec_file", "")) for r in results}

    # If JSON is empty, recover what we can from list-reporter stdout lines
    if not results:
        results, completed_basenames = _parse_list_output(stdout)

    # Append "not started" skipped entries for specs not yet reached.
    # ts_files may be relative paths ("M02/test_BS-001….spec.ts") while
    # completed_basenames holds bare basenames — compare like-for-like.
    for spec in ts_files:
        if os.path.basename(spec) not in completed_basenames:
            results.append({
                "spec_file": spec,
                "test_title": spec,
                "status": "skipped",
                "duration_ms": 0,
                "errors": [],
                "comment": _INTERRUPT_COMMENT,
                "first_attempt_duration_ms": 0,
                "no_interaction_close": False,
            })

    return results


# ── pytest output parser (backward compat) ───────────────────────────────────

def _parse_pytest_output(
    output: str, tc_meta: Dict
) -> Tuple[List[Dict], int, int]:
    results = []
    passed = 0
    failed = 0
    for line in output.splitlines():
        line_s = line.strip()
        if "::" not in line_s:
            continue
        is_passed = "PASSED" in line_s
        is_failed = "FAILED" in line_s
        if not (is_passed or is_failed):
            continue
        tc_id, tc_name = _parse_pytest_line(line_s)
        meta = tc_meta.get(tc_id, {})
        status = "success" if is_passed else "failed"
        if is_passed:
            passed += 1
        else:
            failed += 1
        results.append({
            "test_case_id": tc_id,
            "test_case_name": meta.get("test_case_name", tc_name),
            "status": status,
            "comment": "",
        })
    return results, passed, failed


def _parse_pytest_line(line: str) -> Tuple[str, str]:
    file_part = line.split("::")[0].strip()
    fname = os.path.basename(file_part)
    m = re.match(r"test_(TC-\d+)_(.+)\.py$", fname)
    if m:
        return m.group(1), m.group(2).replace("_", " ")
    return fname, fname


# ── Report index ──────────────────────────────────────────────────────────────

def _update_report_index(
    reports_dir: str,
    ts: str,
    json_path: str,
    html_path: str,
    passed: int,
    failed: int,
) -> None:
    index_path = os.path.join(reports_dir, "index.json")
    entries = []
    if os.path.exists(index_path):
        try:
            with open(index_path, encoding="utf-8") as f:
                loaded = json.load(f)
            entries = loaded if isinstance(loaded, list) else []
        except Exception:
            entries = []

    entries.insert(0, {
        "timestamp": ts,
        "json": json_path,
        "html": html_path,
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
    })

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


# ── Subprocess helpers ────────────────────────────────────────────────────────

def _stream_proc(
    cmd: List[str],
    cwd: str,
    env: Optional[Dict],
    logger,
    timeout: Optional[int] = None,
) -> Tuple[str, str, bool, int]:
    """
    Run cmd with real-time stdout streaming.
    Returns (stdout, stderr, interrupted, returncode).
    On KeyboardInterrupt: kills the process tree and returns interrupted=True.

    `timeout` is optional and off by default — Playwright already bounds itself
    via its own per-test timeout + retries (playwright.config.ts), so there is
    no outer suite-level kill unless a caller explicitly opts in with a value.
    """
    stdout_lines: List[str] = []
    stderr_lines: List[str] = []
    interrupted = False

    try:
        proc = subprocess.Popen(
            _resolve_cmd(cmd),
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        logger.error(f"[UIExecutionAgent] Failed to start process: {exc}")
        return "", str(exc), False, 1

    q: "queue.Queue[Tuple[str, Optional[str]]]" = queue.Queue()

    def _reader(pipe, tag: str) -> None:
        try:
            for line in pipe:
                q.put((tag, line))
        finally:
            q.put((tag, None))

    t1 = threading.Thread(target=_reader, args=(proc.stdout, "out"), daemon=True)
    t2 = threading.Thread(target=_reader, args=(proc.stderr, "err"), daemon=True)
    t1.start()
    t2.start()

    done = {"out": False, "err": False}
    deadline = time.monotonic() + timeout if timeout else None

    try:
        while not all(done.values()):
            if deadline is not None and time.monotonic() > deadline:
                logger.warning(f"[UIExecutionAgent] Playwright timed out after {timeout}s — killing")
                _kill_proc(proc)
                interrupted = True
                break
            try:
                tag, line = q.get(timeout=0.1)
            except queue.Empty:
                continue
            if line is None:
                done[tag] = True
            elif tag == "out":
                stdout_lines.append(line)
                logger.info(f"[PW] {line.rstrip()}")
            else:
                stderr_lines.append(line)
    except KeyboardInterrupt:
        interrupted = True
        logger.warning("[UIExecutionAgent] Interrupted — terminating Playwright")
        _kill_proc(proc)

    # Drain any remaining buffered output after kill/timeout
    t1.join(timeout=3)
    t2.join(timeout=3)
    try:
        while True:
            tag, line = q.get_nowait()
            if line is not None:
                (stdout_lines if tag == "out" else stderr_lines).append(line)
    except queue.Empty:
        pass

    # Wait for the process to exit cleanly
    try:
        proc.wait(timeout=5)
    except (subprocess.TimeoutExpired, Exception):
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass

    rc = proc.returncode if proc.returncode is not None else (130 if interrupted else 1)
    return "".join(stdout_lines), "".join(stderr_lines), interrupted, rc


def _resolve_cmd(cmd: List[str]) -> List[str]:
    """Resolve cmd[0] to a full executable path so the command can run without
    a shell. On Windows `npx` is `npx.cmd`, which CreateProcess only finds via
    PATHEXT lookup — the old workaround ran everything through `shell=True`,
    and cmd.exe then mis-parsed any unquoted path containing `(`/`)` (e.g. a
    user profile directory named like `Name(Org)`), failing every run with rc=1."""
    if not cmd:
        return cmd
    resolved = shutil.which(cmd[0])
    return [resolved, *cmd[1:]] if resolved else list(cmd)


def _kill_proc(proc: subprocess.Popen) -> None:
    """Kill the process and its child tree (node spawned by npx, browsers …)."""
    try:
        if sys.platform == "win32":
            # /T kills the entire tree (npx.cmd → node → browser workers)
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=10,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception:
        pass


def _run_proc(cmd, cwd, env, timeout, logger) -> subprocess.CompletedProcess:
    """Blocking subprocess run — used for pytest compat mode only."""
    try:
        return subprocess.run(
            _resolve_cmd(cmd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
    except subprocess.TimeoutExpired:
        logger.error(f"[UIExecutionAgent] Command timed out after {timeout}s: {cmd[0]}")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="timed out")
    except FileNotFoundError as exc:
        logger.error(f"[UIExecutionAgent] Command not found: {exc}")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(exc))


def _playwright_package_installed() -> bool:
    """Check the npm 'playwright' package is actually usable, not just present.

    A stale or partial node_modules/playwright directory (missing lib/program.js,
    the module npx playwright test loads) is otherwise indistinguishable from a
    complete install by presence-of-directory checks alone.
    """
    return os.path.isfile(os.path.join("node_modules", "playwright", "lib", "program.js"))


# ── Conftest (Python backward compat) ─────────────────────────────────────────

_CONFTEST = '''\
"""conftest.py — auto-generated human-input guard for pytest-playwright runs."""
import pytest

@pytest.fixture(autouse=True)
def human_input_guard(page):
    page.add_init_script("""
        window.__qaHumanInput = false;
        ['mousemove','keydown','touchstart'].forEach(function(t) {
            document.addEventListener(t, function(e) {
                if (e.isTrusted) window.__qaHumanInput = true;
            }, {passive: true, capture: true});
        });
    """)
    yield
    try:
        if page.evaluate("window.__qaHumanInput"):
            pytest.skip("Human input detected — skipped to preserve test integrity")
    except Exception:
        pass
'''


def _write_conftest(scripts_dir: str, logger) -> None:
    path = os.path.join(scripts_dir, "conftest.py")
    if os.path.exists(path):
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(_CONFTEST)
        logger.info(f"[UIExecutionAgent] conftest.py written → {path}")
    except Exception as exc:
        logger.warning(f"[UIExecutionAgent] Could not write conftest.py: {exc}")


def _safe_name(name: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in name).strip("_") or "project"
