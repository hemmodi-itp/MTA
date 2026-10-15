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
from typing import Any, Dict, List, Optional, Tuple, Union

from agents.base_agent import BaseAgent
from tools.base_url import (
    BaseUrlUnresolved,
    load_project_yaml,
    module_ids_of_targets,
    module_urls,
    resolve_execution_base_url,
    resolve_project_base_url,
)
from tools.execution.cmdline import cmd_exe_line, resolve_cmd
from tools.execution.config import KNOWN_PROJECTS, effective_retries, project_slug, resolve_execution_config
from tools.execution.shards import ShardSpecError, blob_root, parse_shard, plan_shards, single_shard
from tools.safety.hosts import url_allowed
from tools.safety.policy import SafetyPolicy, hosts_env_value
from tools.shared import get_logger
from tools.constants import PROJECTS_BASE as _ASSETS_BASE

# ── Constants ─────────────────────────────────────────────────────────────────

# First-attempt duration below which a browser-close is considered
# "no interaction occurred" (browser was closed before any Playwright
# action in the spec could complete).  Generous at 5 s to handle slow
# initial page navigations.
_NO_INTERACTION_MAX_MS = 5_000

_BROWSER_CLOSE_COMMENT = "Browser closed by user — skipped"
_HEADLESS_CLOSE_COMMENT = "Browser closed unexpectedly in a headless run — counted as an error"
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

# Phase 4.7: only these mean "a human closed the window" — and only in a headed run. A crash or a dropped
# connection ("target crashed", "connection closed", ...) is an error in every mode.
_HUMAN_CLOSE_PATTERNS = [
    "target closed",
    "page has been closed",
    "browser has been closed",
    "browser was disconnected",
    "browser disconnected",
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


def _is_human_close_error(text: str) -> bool:
    t = text.lower()
    return any(pat in t for pat in _HUMAN_CLOSE_PATTERNS)


def _count_results(results: List[Dict]) -> Tuple[int, int, int]:
    """(passed, failed, skipped). A "flaky" result is none of these — count it with _count_flaky (Phase 4.7)."""
    passed = sum(1 for r in results if r.get("status") in ("success", "expected"))
    failed = sum(1 for r in results if r.get("status") == "failed")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    return passed, failed, skipped


def _count_flaky(results: List[Dict]) -> int:
    """Phase 4.7: failed, then passed on a retry — never counted as passed."""
    return sum(1 for r in results if r.get("status") == "flaky")


def _load_results(mta_path: str, json_path: str, logger) -> Tuple[List[Dict], str]:
    """Phase 4.7: per-test results from the MTA reporter file (the source of truth: keeps flaky / skipped /
    timedOut apart), falling back to Playwright's JSON report when the MTA file is missing or empty
    (execution.mta_reporter: false, an interrupted run, a reporter crash). Returns (results, source)."""
    from tools.execution.mta_results import load_mta_results, to_execution_results

    doc = load_mta_results(mta_path) if mta_path else None
    if doc is not None and doc.get("tests"):
        return to_execution_results(doc), "mta_results"
    results, _, _ = _parse_playwright_json(json_path, logger)
    return results, "playwright_json"


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
        try:
            self._configure_run(request, safe)
        except ShardSpecError as exc:
            self._log(str(exc), level="error")
            return {"module": "ui_execution", "status": "failed", "error": str(exc)}
        if request.get("merge_run"):
            result = self._merge_only(project_name, safe, str(request["merge_run"]))
        else:
            result = self._execute(request, _state)
        return self._finalise(result)

    # ── Phase 4 run configuration (execution: block + request overrides) ──────

    def _configure_run(self, request: dict, safe: str) -> None:
        """Resolve the project's `execution:` block (tools/execution/config.py) and this request's
        overrides: browsers, grep / grep_invert, shard ("i/n", CI job), shards (local N-shard run +
        merge), run_id (shared blob folder of a CI run)."""
        project_cfg = load_project_yaml(_ASSETS_BASE, safe)
        cfg = request.get("execution") if isinstance(request.get("execution"), dict) else None
        cfg = cfg or resolve_execution_config(project_cfg)
        projects = list(cfg.get("projects") or ["chromium"])
        browsers = request.get("browsers")
        if browsers:
            wanted = [project_slug(b) for b in (browsers if isinstance(browsers, list) else [browsers])]
            override = [p for p in KNOWN_PROJECTS if p in wanted]
            if override:
                projects = override
        headless = request.get("headless", True)
        shard = parse_shard(request.get("shard"))
        shards = int(request.get("shards") or cfg.get("shards") or 1)
        if not headless and (shard or shards > 1):
            self._log("Sharding is disabled in headed mode (one visible browser at a time)", level="warning")
            shard, shards = None, 1
        if request.get("spec_files"):
            shard, shards = None, 1     # healing re-runs a few specs; never shard them
        self._exec_cfg = cfg
        self._headless = headless
        self._project_cfg = project_cfg
        self._projects = projects
        self._grep = request.get("grep") or None
        self._grep_invert = request.get("grep_invert") or None
        # Phase 6: healing burn-in / triage flaky re-run — every test N times, no retries (a retry would hide it)
        self._repeat_each = int(request.get("repeat_each") or 0) or None
        # Phase 10: worker count override (order-independence runs use 1 and 4)
        self._workers = int(request.get("workers") or 0) or None
        self._health_done = False
        # Phase 7.2: approve visual baselines (python -m tools.nonfunctional.visual approve)
        self._update_snapshots = bool(request.get("update_snapshots"))
        self._shard = shard
        self._shards = shards if shard is None else 1
        self._run_id = str(request.get("run_id")) if request.get("run_id") else None
        self._role_auth_done = False
        self._role_auth = None

    def _cfg(self) -> Dict[str, Any]:
        cfg = getattr(self, "_exec_cfg", None)
        if cfg is None:
            cfg = self._exec_cfg = resolve_execution_config({})
        return cfg

    def _ensure_role_auth(self, safe: str) -> None:
        """Phase 4.3 — once per execute(): log in every auth.roles role (execution.role_auth: true)
        so `test.use({ role })` finds .auth/<role>.json. Never fatal."""
        if getattr(self, "_role_auth_done", True) or not self._cfg().get("role_auth"):
            return
        self._role_auth_done = True
        try:
            from tools.auth.role_states import ensure_role_states, project_roles

            roles = project_roles(getattr(self, "_project_cfg", None) or load_project_yaml(_ASSETS_BASE, safe))
            if not roles:
                self._log("execution.role_auth is on but project.yaml declares no auth.roles", level="warning")
                return
            self._role_auth = ensure_role_states(
                safe, roles, max_age_minutes=self._cfg().get("role_auth_max_age_minutes", 30))
        except Exception as exc:
            self._log(f"role auth pre-step failed (non-fatal): {exc}", level="warning")
            self._role_auth = {"roles": [], "failed": [], "error": str(exc)[:300]}

    def _health_check(self, safe: str, base_url: str, base_only: bool = False) -> Optional[Dict[str, Any]]:
        """None = healthy (or no health_check block); else the `environment_blocked` result. Done once per execute().
        `base_only` (before the role logins): only the base-URL check, and the full check still runs after."""
        if getattr(self, "_health_done", False):
            return None
        from tools.execution import health
        if base_only:
            res = health.check(os.path.join(_ASSETS_BASE, safe), base_url, base_only=True)
            return None if res.get("ok") else self._blocked(res)
        self._health_done = True

        def _refresh(role: str) -> None:
            from tools.auth.role_states import ensure_role_states, project_roles
            roles = project_roles(getattr(self, "_project_cfg", None) or load_project_yaml(_ASSETS_BASE, safe))
            ensure_role_states(safe, roles, force=True, only=[role])
        res = health.check(os.path.join(_ASSETS_BASE, safe), base_url, refresh=_refresh)
        if res.get("ok"):
            self._health = res
            if res.get("checks"):
                self._log(f"Health check passed ({len(res['checks'])} check(s))")
            return None
        return self._blocked(res)

    def _blocked(self, res: Dict[str, Any]) -> Dict[str, Any]:
        self._health = res
        bad = [c for c in res["checks"] if not c["ok"]]
        msg = "environment blocked — " + "; ".join(f"{c['name']}: {c['detail']}" for c in bad)
        self._log(msg, level="error")
        return {"module": "ui_execution", "status": "environment_blocked", "error": msg, "health": res,
                "passed": 0, "failed": 0, "skipped": 0, "flaky": 0, "results": []}

    def _finalise(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return result
        if getattr(self, "_role_auth", None) is not None:
            result["role_auth"] = self._role_auth
        if result.get("mode") == "playwright":
            result.setdefault("projects", list(getattr(self, "_projects", ["chromium"])))
        return result

    def _execute(self, request: dict, _state: dict) -> Dict[str, Any]:
        project_name = request.get("project_name") or request.get("message", "project")
        safe = _safe_name(project_name)
        headless = request.get("headless", True)
        # Orchestrator already resolved the active module's URL (project.yaml
        # modules[].url, narrowed by --module) onto request["url"] — forward it
        # as BASE_URL so playwright.config.ts doesn't have to re-derive it by
        # regex-scraping project.yaml (which can't tell modules apart anyway).
        base_url = request.get("url")
        # Phase 0 safety rails — forwarded to the TS runtime as MTA_ALLOWED_HOSTS.
        self._safety = request.get("safety") if isinstance(request.get("safety"), dict) else None

        self._log(f"Starting — project='{project_name}' headless={headless}")

        scripts_dir = os.path.join(_ASSETS_BASE, safe, "test_creation", "test_scripts")
        reports_dir = os.path.join(_ASSETS_BASE, safe, "test_execution", "reports")

        # Suite-based execution: resolve suite → specific spec file paths
        suite_name = request.get("suite")
        if suite_name and self._cfg().get("suite_mode") == "grep":
            return self._run_suite_grep(
                suite_name=suite_name, project_name=project_name, safe=safe,
                scripts_dir=scripts_dir, reports_dir=reports_dir, headless=headless,
                auth_config=request.get("auth_config"),
                auth_storage_state=request.get("auth_storage_state", ""),
                base_url=base_url,
            )
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

        return _merge_runs(runs)

    # ── Phase 4.9: suite → one --grep run ───────────────────────────────────────

    def _run_suite_grep(
        self,
        suite_name: str,
        project_name: str,
        safe: str,
        scripts_dir: str,
        reports_dir: str,
        headless: bool,
        auth_config: Optional[dict] = None,
        auth_storage_state: str = "",
        base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """execution.suite_mode: grep — test_suites/<suite>_suite.json becomes one grep expression over
        the project's specs (tools/execution/suite_grep.py) instead of one Playwright run per entry."""
        from tools.execution.suite_grep import build_suite_grep

        try:
            sg = build_suite_grep(os.path.join(_ASSETS_BASE, safe), suite_name)
        except FileNotFoundError as exc:
            self._log(str(exc), level="error")
            return {"module": "ui_execution", "status": "failed", "error": str(exc)}
        if sg.empty:
            msg = f"Suite '{suite_name}' selects nothing — unresolved ids: {sg.unresolved}"
            self._log(msg, level="warning")
            return {"module": "ui_execution", "status": "skipped", "reason": msg, "suite_unresolved": sg.unresolved}
        targets, ts_files = _grep_targets(scripts_dir, sg.modules)
        if not targets:
            msg = f"Suite '{suite_name}': no .spec.ts files under '{scripts_dir}' for modules {sg.modules or 'all'}"
            self._log(msg, level="warning")
            return {"module": "ui_execution", "status": "skipped", "reason": msg}
        self._log(f"Suite '{suite_name}' (grep mode) — {len(ts_files)} spec file(s) in scope, grep={sg.grep!r}")
        out = self._run_playwright(
            project_name=project_name, safe=safe, scripts_dir=scripts_dir, reports_dir=reports_dir,
            ts_files=ts_files, headless=headless, auth_config=auth_config,
            auth_storage_state=auth_storage_state, spec_files=targets, grep_pattern=sg.grep,
            base_url=base_url,
        )
        out["suite_grep"] = sg.grep
        if sg.unresolved:
            out["suite_unresolved"] = sg.unresolved
        return out

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

        # Phase 0.6 — the base URL is resolved explicitly or the run fails fast;
        # there is no localhost default anywhere any more. A run whose specs span
        # modules with different URLs is split into one Playwright run per module
        # (each with its own BASE_URL) instead of sending every module's specs to
        # whichever URL happens to come first.
        project_cfg = load_project_yaml(_ASSETS_BASE, safe)
        abs_targets = (
            [p.replace(os.sep, "/") for p in spec_files] if spec_files
            else [os.path.join(scripts_dir, f).replace(os.sep, "/") for f in ts_files]
        )
        if not base_url and not resolve_project_base_url(
            {"project": project_cfg.get("project"), "url": project_cfg.get("url")}
        ):
            groups = _group_targets_by_module(abs_targets)
            by_module = module_urls(project_cfg)
            if (len(groups) > 1 and all(by_module.get(m) for m in groups)
                    and len({by_module[m] for m in groups}) > 1):
                return self._run_per_module(
                    groups, by_module, project_name=project_name, safe=safe,
                    scripts_dir=scripts_dir, reports_dir=reports_dir, headless=headless,
                    auth_config=auth_config, auth_storage_state=auth_storage_state,
                    grep_pattern=grep_pattern,
                )
        try:
            base_url, url_source = resolve_execution_base_url(
                base_url, project_cfg, module_ids_of_targets(abs_targets)
            )
        except BaseUrlUnresolved as exc:
            msg = str(exc)
            self._log(msg, level="error")
            return {"module": "ui_execution", "status": "failed", "blocking": True, "error": msg}
        self._log(f"Base URL: {base_url} (from {url_source})")

        safety = getattr(self, "_safety", None)
        policy = SafetyPolicy.from_request(safety) if safety else SafetyPolicy.from_project_config(project_cfg)
        if not url_allowed(base_url, policy.allowed_hosts):
            self._log(
                f"Base URL host of '{base_url}' is not in safety.allowed_hosts "
                f"{policy.allowed_hosts} — every navigation will be refused by the runtime",
                level="warning",
            )

        # Phase 10.4 — a dead app is blocked before the role logins (each would wait for its own timeouts)
        blocked = self._health_check(safe, base_url, base_only=True)
        if blocked is not None:
            return blocked
        # Phase 4.3 — per-role storage states, once per execute() (execution.role_auth)
        self._ensure_role_auth(safe)
        # Phase 10.4 — pre-run health check (project.yaml health_check): a broken environment blocks the run
        blocked = self._health_check(safe, base_url)
        if blocked is not None:
            return blocked
        cfg = self._cfg()
        projects = list(getattr(self, "_projects", None) or cfg.get("projects") or ["chromium"])

        # Report paths. Phase 4: --output (screenshots/traces/videos) gets its own folder — it used to be
        # the HTML report folder, which the HTML reporter empties when it writes the report.
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_report_dir = os.path.join(reports_dir, "json")
        html_report_dir = os.path.join(reports_dir, "html", ts)
        os.makedirs(json_report_dir, exist_ok=True)
        os.makedirs(html_report_dir, exist_ok=True)
        json_report_path = os.path.join(json_report_dir, f"{ts}_results.json")
        test_results_dir = os.path.join(reports_dir, "test-results", ts)
        junit_path = os.path.join(reports_dir, "junit", f"{ts}.xml") if cfg.get("junit", True) else ""
        mta_path = os.path.join(reports_dir, "mta", f"{ts}.mta_results.json") if cfg.get("mta_reporter", True) else ""
        run_id = getattr(self, "_run_id", None) or ts
        grep = _combine_grep(grep_pattern, getattr(self, "_grep", None))
        grep_invert = getattr(self, "_grep_invert", None)

        # Fix 5: one browser window at a time in headed mode
        workers = "1" if not headless else "2"
        if getattr(self, "_workers", None) and headless:
            workers = str(self._workers)

        # When spec_files is set (suite run), pass individual paths; otherwise pass the directory
        if spec_files:
            targets = [p.replace(os.sep, "/") for p in spec_files]
        else:
            targets = [scripts_dir.replace(os.sep, "/")]   # Fix 1: forward slashes on Windows

        cmd = [
            "npx", "playwright", "test",
            *targets,
            "--config", "playwright.config.ts",
            *[f"--project={p}" for p in projects],
            *(["--headed"] if not headless else []),
            # Phase 4.7: a human closing a headed window must not relaunch the test — no retries when headed.
            *(["--retries=0"] if not headless or getattr(self, "_repeat_each", None) else []),
            *([f"--repeat-each={self._repeat_each}"] if getattr(self, "_repeat_each", None) else []),
            *(["--update-snapshots"] if getattr(self, "_update_snapshots", False) else []),
            f"--workers={workers}",
            *(["--grep", grep] if grep else []),
            *(["--grep-invert", grep_invert] if grep_invert else []),
            # --reporter omitted: playwright.config.ts already declares its reporters;
            # adding it here would override the whole array and break the file output.
            f"--output={test_results_dir}",
        ]

        env = {
            **os.environ,
            "PW_PROJECT": safe,
            "PW_TEST_DIR": _ASSETS_BASE,
            "PW_JSON_REPORT": json_report_path,
            "PW_HTML_REPORT": html_report_dir,
            # The config builder enables exactly these projects (a request's `browsers` override
            # may name projects project.yaml's matrix does not enable).
            "MTA_PROJECTS": ",".join(projects),
            "MTA_RUN_ID": run_id,
        }
        for key in ("PW_JUNIT_REPORT", "MTA_RESULTS_FILE", "PW_BLOB_DIR", "MTA_BLOB_ONLY"):
            env.pop(key, None)
        if junit_path:
            env["PW_JUNIT_REPORT"] = junit_path
        if mta_path:
            env["MTA_RESULTS_FILE"] = mta_path
        # Always set: resolved above (request -> project.url -> module URL), so
        # playwright.config.ts never has to guess.
        env["BASE_URL"] = base_url
        env["MTA_ALLOWED_HOSTS"] = hosts_env_value(policy.allowed_hosts)
        # Phase 4.4: the run-time destructive-action guard applies the same policy that filters plans.
        env["MTA_DESTRUCTIVE_ALLOWED"] = "1" if policy.destructive_allowed else "0"
        env["MTA_SAFETY_ENVIRONMENT"] = policy.environment
        if auth_config and auth_config.get("strategy") == "live_login":
            fresh_state = self._capture_live_auth(auth_config)
            if fresh_state:
                env["PW_STORAGE_STATE"] = fresh_state
                self._log(f"live_login: fresh auth state → PW_STORAGE_STATE='{fresh_state}'")
        elif auth_storage_state:
            env["PW_STORAGE_STATE"] = auth_storage_state
            self._log(f"Auth state injected → PW_STORAGE_STATE='{auth_storage_state}'")

        shard = getattr(self, "_shard", None)
        shards = getattr(self, "_shards", 1) or 1
        if shards > 1:
            # Phase 4.8 — every shard locally, then one merge into the normal outputs.
            stdout, stderr, interrupted, returncode = self._run_shards(
                cmd, env, shards, reports_dir=reports_dir, run_id=run_id, test_results_dir=test_results_dir,
                json_path=json_report_path, html_dir=html_report_dir, junit_path=junit_path, mta_path=mta_path,
            )
        else:
            if shard:
                # A CI job: this shard only — normal reports plus a blob for a later merge_run.
                cmd, env = single_shard(cmd, env, shard[0], shard[1], reports_dir, run_id, invocation=ts)
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

        # Browser binaries must be installed ahead of time — no installs
        # during execution (see README Quick Start).
        binary_missing = (
            "Executable doesn't exist" in (stderr + stdout)
            or "browserType.launch" in (stderr + stdout)
        )
        if returncode != 0 and binary_missing:
            msg = _browser_missing_message(stderr + stdout, projects)
            self._log(msg, level="error")
            return {"module": "ui_execution", "status": "failed", "error": msg, "returncode": returncode}

        # Phase 4.7: per-test results from the MTA reporter file (flaky stays flaky), JSON report as fallback
        results, results_source = _load_results(mta_path, json_report_path, self.logger)

        # A grep that selects nothing: Playwright exits 1 with "No tests found" — report it as
        # skipped instead of recovering a "not started" entry per spec file.
        if not results and grep and "No tests found" in (stdout + stderr):
            msg = f"No tests match grep {grep!r}"
            self._log(msg, level="warning")
            return {"module": "ui_execution", "status": "skipped", "reason": msg, "mode": "playwright",
                    "grep": grep, "passed": 0, "failed": 0, "skipped": 0, "results": [], "returncode": returncode}

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
                results = _recover_partial_results(ts_files, json_report_path, stdout, self.logger,
                                                   headed=not headless)

        # Fix 3 (Phase 4.7: headed runs only): a human closed the window -> skipped, tagging interaction info.
        # Headless, a browser-close error stays a failure.
        results, browser_close_count = _mark_browser_close_as_skipped(results, headed=not headless)

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
        flaky = _count_flaky(results)
        _update_report_index(reports_dir, ts, json_report_path, html_report_dir, passed, failed)
        self._log(f"Done — passed={passed} flaky={flaky} failed={failed} skipped={skipped} "
                  f"(results from {results_source})")
        extra = _run_outputs(junit_path, mta_path, projects, shards=shards, shard=shard, run_id=run_id,
                             grep=grep, reports_dir=reports_dir)
        extra["results_source"] = results_source
        extra["retries"] = effective_retries(cfg, headed=not headless)
        _write_execution_results(
            reports_dir, ts, project=safe, base_url=base_url, results=results,
            passed=passed, failed=failed, skipped=skipped, returncode=returncode,
            report_json=json_report_path, logger=self.logger, extra={**extra, "flaky": flaky},
        )
        _apply_traceability(safe, results, ts, logger=self.logger)
        return {
            "module": "ui_execution",
            "status": "success",
            "suite": safe,
            "mode": "playwright",
            "scenarios_executed": passed + flaky + failed + skipped,
            "passed": passed,
            "flaky": flaky,
            "failed": failed,
            "skipped": skipped,
            "returncode": returncode,
            "results": results,
            "report_json": json_report_path,
            "report_html": html_report_dir,
            **extra,
        }

    # ── Phase 4.8: local shards + merge ──────────────────────────────────────

    def _run_shards(self, cmd: List[str], env: Dict[str, str], total: int, *, reports_dir: str, run_id: str,
                    test_results_dir: str, json_path: str, html_dir: str, junit_path: str,
                    mta_path: str) -> Tuple[str, str, bool, int]:
        """Run shards 1..total (max_parallel_shards at a time) with only list + blob reporters, then
        merge the blobs into the run's json / html / junit / mta outputs. Returns the combined
        (stdout, stderr, interrupted, returncode): rc is the first non-zero shard rc, else the merge's."""
        from concurrent.futures import ThreadPoolExecutor
        from tools.execution.merge_reports import merge_blob_reports, merge_env

        root = blob_root(reports_dir, run_id)
        if os.path.isdir(root):
            shutil.rmtree(root, ignore_errors=True)
        runs = plan_shards(cmd, env, total, reports_dir, run_id, test_results_dir)
        parallel = max(1, min(int(self._cfg().get("max_parallel_shards", 1) or 1), total))
        self._log(f"Sharded run {run_id}: {total} shard(s), {parallel} at a time")

        def _one(run):
            self._log(f"Shard {run.index}/{run.total}: {' '.join(run.cmd)}")
            return _stream_proc(run.cmd, cwd=os.getcwd(), env=run.env, logger=self.logger)

        if parallel == 1:
            outs = []
            for run in runs:
                outs.append(_one(run))
                if outs[-1][2]:          # interrupted — don't start the remaining shards
                    break
        else:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                outs = list(pool.map(_one, runs))

        stdout = "".join(o[0] for o in outs)
        stderr = "".join(o[1] for o in outs)
        interrupted = any(o[2] for o in outs)
        rcs = [o[3] for o in outs]
        menv = merge_env(env, json_path=json_path, html_dir=html_dir, junit_path=junit_path, mta_path=mta_path)
        names, (m_out, m_err, m_int, m_rc) = merge_blob_reports(
            root, menv, lambda c, cwd, e: _stream_proc(c, cwd=cwd, env=e, logger=self.logger))
        self._log(f"merge-reports: {len(names)} blob(s) → rc={m_rc}")
        if m_rc != 0:
            self._log(f"merge-reports failed: {(m_err or m_out)[:2000]}", level="warning")
        rc = next((r for r in rcs if r != 0), 0) or m_rc
        return stdout + m_out, stderr + m_err, interrupted or m_int, rc

    def _merge_only(self, project_name: str, safe: str, run_id: str) -> Dict[str, Any]:
        """merge_run: <run_id> — a CI merge job: merge reports/blob/<run_id>/ (one folder per shard job)
        into this project's normal reports, index, execution_results and traceability."""
        from tools.execution.merge_reports import merge_blob_reports, merge_env

        reports_dir = os.path.join(_ASSETS_BASE, safe, "test_execution", "reports")
        root = blob_root(reports_dir, run_id)
        if not os.path.isdir(root):
            msg = f"No blob reports for run '{run_id}' (expected {root})"
            self._log(msg, level="error")
            return {"module": "ui_execution", "status": "failed", "error": msg}
        cfg = self._cfg()
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_path = os.path.join(reports_dir, "json", f"{ts}_results.json")
        html_dir = os.path.join(reports_dir, "html", ts)
        junit_path = os.path.join(reports_dir, "junit", f"{ts}.xml") if cfg.get("junit", True) else ""
        mta_path = os.path.join(reports_dir, "mta", f"{ts}.mta_results.json") if cfg.get("mta_reporter", True) else ""
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        env = merge_env({**os.environ, "PW_PROJECT": safe, "MTA_RUN_ID": run_id},
                        json_path=json_path, html_dir=html_dir, junit_path=junit_path, mta_path=mta_path)
        names, (_out, err, _int, rc) = merge_blob_reports(
            root, env, lambda c, cwd, e: _stream_proc(c, cwd=cwd, env=e, logger=self.logger))
        results, results_source = _load_results(mta_path, json_path, self.logger)
        if rc != 0 and not results:
            msg = f"merge-reports failed for run '{run_id}' ({len(names)} blob(s)): {(err or '')[:500]}"
            self._log(msg, level="error")
            return {"module": "ui_execution", "status": "failed", "error": msg, "returncode": rc}
        passed, failed, skipped = _count_results(results)
        flaky = _count_flaky(results)
        _update_report_index(reports_dir, ts, json_path, html_dir, passed, failed)
        extra = _run_outputs(junit_path, mta_path, list(getattr(self, "_projects", ["chromium"])),
                             shards=len(names), shard=None, run_id=run_id, grep=None, reports_dir=reports_dir)
        extra["results_source"] = results_source
        _write_execution_results(
            reports_dir, ts, project=safe, base_url="", results=results, passed=passed, failed=failed,
            skipped=skipped, returncode=rc, report_json=json_path, logger=self.logger, extra={**extra, "flaky": flaky},
        )
        _apply_traceability(safe, results, ts, logger=self.logger)
        self._log(f"Merged run {run_id}: {len(names)} blob(s) — passed={passed} flaky={flaky} failed={failed} "
                  f"skipped={skipped}")
        return {
            "module": "ui_execution", "status": "success", "suite": safe, "mode": "playwright",
            "scenarios_executed": passed + flaky + failed + skipped, "passed": passed, "flaky": flaky,
            "failed": failed, "skipped": skipped, "returncode": rc, "results": results,
            "report_json": json_path, "report_html": html_dir, **extra,
        }

    # ── Per-module split (Phase 0.6) ──────────────────────────────────────────

    def _run_per_module(
        self,
        groups: Dict[str, List[str]],
        by_module: Dict[str, str],
        project_name: str,
        safe: str,
        scripts_dir: str,
        reports_dir: str,
        headless: bool,
        auth_config: Optional[dict] = None,
        auth_storage_state: str = "",
        grep_pattern: Optional[str] = None,
    ) -> Dict[str, Any]:
        runs: List[Dict[str, Any]] = []
        for module_id, targets in groups.items():
            self._log(f"Module {module_id}: {len(targets)} spec(s) against {by_module[module_id]}")
            runs.append(self._run_playwright(
                project_name=project_name, safe=safe,
                scripts_dir=scripts_dir, reports_dir=reports_dir,
                ts_files=[os.path.basename(t) for t in targets], headless=headless,
                auth_config=auth_config, auth_storage_state=auth_storage_state,
                spec_files=targets, grep_pattern=grep_pattern,
                base_url=by_module[module_id],
            ))
        return _merge_runs(runs)

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
        results = _recover_partial_results(ts_files, json_report_path, stdout, self.logger,
                                           headed=not getattr(self, "_headless", True))
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
            "scenarios_executed": passed + failed + skipped + _count_flaky(results),
            "passed": passed,
            "flaky": _count_flaky(results),
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

        projects = [p for p in env.get("MTA_PROJECTS", "chromium").split(",") if p] or ["chromium"]
        cmd2 = [
            "npx", "playwright", "test",
            *spec_paths,
            "--config", "playwright.config.ts",
            *[f"--project={p}" for p in projects],
            "--workers=2",
            "--output=" + os.path.join(reports_dir, "test-results", f"{ts2}_headless_retry"),
        ]
        env2 = {**env, "PW_JSON_REPORT": json2, "PW_HTML_REPORT": html2}
        for key in ("PW_JUNIT_REPORT", "MTA_RESULTS_FILE"):
            env2.pop(key, None)

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


def _write_execution_results(reports_dir: str, ts: str, *, project: str, base_url: str,
                             results: List[Dict], passed: int, failed: int, skipped: int,
                             returncode: int, report_json: str, logger=None,
                             extra: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Phase 0.7 — the MTA-normalised run record (contracts: execution_results v2),
    written to reports/mta/ (never reports/json/, which healing scans for the latest
    Playwright report). A write failure never fails the run."""
    try:
        from contracts.artifacts import save_artifact

        path = os.path.join(reports_dir, "mta", f"{ts}.execution_results.json")
        return save_artifact("execution_results", path, {
            "project": project, "status": "success", "mode": "playwright", "base_url": base_url,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "passed": passed, "failed": failed, "skipped": skipped, "returncode": returncode,
            "report_json": report_json,
            **(extra or {}),
            "results": [
                {**r, "spec_file": str(r.get("spec_file", "")), "status": str(r.get("status", ""))}
                for r in results
            ],
        })
    except Exception as exc:  # pragma: no cover — defensive
        if logger:
            logger.warning(f"[ui_execution] could not write execution_results: {exc}")
        return None


def _apply_traceability(safe: str, results: List[Dict], ts: str, logger=None) -> None:
    """Phase 1.2: fold this run's results into traceability.json (no-op unless requirements.enabled).
    Runs for every Playwright run, including healing's re-runs. A failure never fails the run."""
    try:
        from tools.requirements.traceability import apply_results_for_project

        trace = apply_results_for_project(safe, results, run=ts)   # flag read from project.yaml
        if trace is not None and logger:
            s = trace.summary
            logger.info(f"[ui_execution] traceability: {s.get('acs_passing')} AC(s) passing, "
                        f"{s.get('acs_failing')} failing, {s.get('unmatched_results', 0)} unmatched result(s)")
    except Exception as exc:
        if logger:
            logger.warning(f"[ui_execution] traceability update failed (non-fatal): {exc}")


def _group_targets_by_module(targets: List[str]) -> Dict[str, List[str]]:
    """{module_id: [spec paths]} for paths shaped .../test_scripts/<module>/<spec>;
    a path with no module segment groups under ''."""
    groups: Dict[str, List[str]] = {}
    for t in targets:
        mids = module_ids_of_targets([t])
        groups.setdefault(mids[0] if mids else "", []).append(t)
    return groups


def _merge_runs(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge several _run_playwright results into one (suite/grep runs and the
    per-module split). A failed sub-run's error is kept in `run_errors`."""
    if len(runs) == 1:
        return runs[0]
    merged: List[Dict] = []
    passed = failed = skipped = flaky = 0
    errors = []
    for r in runs:
        merged.extend(r.get("results", []))
        passed += r.get("passed", 0)
        failed += r.get("failed", 0)
        skipped += r.get("skipped", 0)
        flaky += r.get("flaky", 0)
        if r.get("status") == "failed" and r.get("error"):
            errors.append(r["error"])
    if errors and all(r.get("status") == "failed" for r in runs):
        return {**runs[0], "error": "; ".join(errors)}
    ok = [r for r in runs if r.get("status") != "failed"]
    out = {
        **ok[-1],
        "results": merged,
        "passed": passed,
        "flaky": flaky,
        "failed": failed,
        "skipped": skipped,
        "scenarios_executed": passed + flaky + failed + skipped,
    }
    if errors:
        out["run_errors"] = errors
    # Phase 4: every sub-run writes its own JUnit / MTA file — keep all of them, not just the last.
    for key in ("report_junit", "mta_results", "report_json"):
        paths = [r[key] for r in runs if r.get(key)]
        if len(paths) > 1:
            out[f"{key}_all"] = paths
    return out


def _combine_grep(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Both patterns must match (a suite's grep AND the request's --grep)."""
    if a and b:
        return f"^(?=.*(?:{a}))(?=.*(?:{b}))"
    return a or b or None


def _run_outputs(junit_path: str, mta_path: str, projects: List[str], *, shards: int, shard, run_id: str,
                 grep: Optional[str], reports_dir: str) -> Dict[str, Any]:
    """Phase 4 additions to a run's result and execution_results record (only files that exist)."""
    out: Dict[str, Any] = {"projects": list(projects), "run_id": run_id}
    if junit_path and os.path.exists(junit_path):
        out["report_junit"] = junit_path
    if mta_path and os.path.exists(mta_path):
        out["mta_results"] = mta_path
    if shards and shards > 1:
        out["shards"] = shards
        out["blob_dir"] = blob_root(reports_dir, run_id)
    if shard:
        out["shard"] = f"{shard[0]}/{shard[1]}"
        out["blob_dir"] = blob_root(reports_dir, run_id)
    if grep:
        out["grep"] = grep
    return out


_PROJECT_BROWSER = {"chromium": "chromium", "pixel-7": "chromium", "firefox": "firefox",
                    "webkit": "webkit", "iphone-14": "webkit"}


def _browser_missing_message(output: str, projects: List[str]) -> str:
    """Name the missing browser(s) and the install command (no installs during execution)."""
    low = (output or "").lower()
    named = [b for b in ("chromium", "firefox", "webkit") if b in low and "executable doesn't exist" in low]
    browsers = named or sorted({_PROJECT_BROWSER.get(p, "chromium") for p in projects})
    label = ", ".join(b.capitalize() for b in browsers)
    return (
        f"Playwright's {label} browser binary is not installed. Run "
        f"`npx playwright install {' '.join(browsers)}` once before executing tests "
        "(see README Quick Start)."
    )


def _grep_targets(scripts_dir: str, modules: List[str]) -> Tuple[List[str], List[str]]:
    """Targets for a grep run: one folder per module (keeps the command line short and the
    per-module base-URL split working), plus top-level spec files of a flat project.
    Returns (absolute targets, spec files relative to scripts_dir)."""
    targets: List[str] = []
    ts_files: List[str] = []
    for rel in _find_scripts(scripts_dir, ".spec.ts"):
        parts = rel.replace(os.sep, "/").split("/")
        if len(parts) > 1:
            if modules and parts[0] not in modules:
                continue
            target = os.path.join(scripts_dir, parts[0]).replace(os.sep, "/")
        else:
            if modules:
                continue
            target = os.path.join(scripts_dir, rel).replace(os.sep, "/")
        ts_files.append(rel)
        if target not in targets:
            targets.append(target)
    return targets, ts_files


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
                # Phase 4.7: "flaky" (failed, then passed on a retry) is its own result — never a pass — and
                # Playwright "skipped" stays "skipped" (Phase 1 D6). Everything else ("unexpected") is a failure.
                result_status = _PW_STATUS_TO_RESULT.get(status, "failed")
                if result_status == "success":
                    passed += 1
                elif result_status == "failed":
                    failed += 1

                test_results = test.get("results", [])
                errors = [
                    r.get("error", {}).get("message", "") or ""
                    for r in test_results
                    if r.get("error")
                ]
                # First-attempt duration used for "no-interaction" browser-close detection
                first_attempt_ms = test_results[0].get("duration", 0) if test_results else 0
                trace_fields = _trace_fields(spec, test)

                results.append({
                    "spec_file": spec_file,
                    "test_title": spec_title,
                    "test_case_id": _extract_test_case_id(spec_file),
                    "business_scenario_id": _extract_test_case_id(spec_file),
                    "status": result_status,
                    "flaky": status == "flaky",
                    "duration_ms": test.get("duration", 0),
                    "first_attempt_duration_ms": first_attempt_ms,
                    "errors": errors,
                    "comment": "",
                    "no_interaction_close": False,
                    **trace_fields,
                })

    return results, passed, failed


_PW_STATUS_TO_RESULT = {"expected": "success", "passed": "success", "flaky": "flaky", "skipped": "skipped"}


def _trace_fields(spec: dict, test: dict) -> Dict:
    """Phase 1.3: Playwright's raw status plus the test's tags/annotations (tc / ac ids for traceability).
    pw_status keeps Playwright's own word ("expected" / "unexpected" / "flaky" / "skipped")."""
    annotations = [
        {"type": str(a.get("type", "")), "description": str(a.get("description", ""))}
        for a in (test.get("annotations") or []) if isinstance(a, dict)
    ]
    # runtime annotations (testInfo.annotations.push during the run) are reported per attempt as well
    seen = {(a["type"], a["description"]) for a in annotations}
    for r in test.get("results") or []:
        for a in r.get("annotations") or []:
            item = {"type": str(a.get("type", "")), "description": str(a.get("description", ""))}
            if (item["type"], item["description"]) not in seen:
                seen.add((item["type"], item["description"]))
                annotations.append(item)
    last = (test.get("results") or [{}])[-1] or {}
    # Phase 11.4: evidence of the last attempt (screenshot, trace, video, HAR, console log) for defect reports
    attachments = [{"name": str(a.get("name", "")), "path": a.get("path"), "content_type": a.get("contentType", "")}
                   for a in last.get("attachments") or [] if isinstance(a, dict) and a.get("path")]
    fields: Dict = {"pw_status": test.get("status", ""), "tags": list(spec.get("tags") or []),
                    "annotations": annotations, "browser": test.get("projectName") or "",
                    "attachments": attachments}
    tc = [a["description"] for a in annotations if a["type"] == "tc"]
    if tc:
        fields["tc_id"] = tc[0]
    acs = [a["description"] for a in annotations if a["type"] == "ac"]
    if acs:
        fields["ac_ids"] = acs
    return fields


def _iter_suites(suites: list):
    for suite in suites:
        yield suite
        for child in _iter_suites(suite.get("suites", [])):
            yield child


# ── Fix 3: browser-close → skipped ───────────────────────────────────────────

def _mark_browser_close_as_skipped(
    results: List[Dict], headed: bool = True,
) -> Tuple[List[Dict], int]:
    """
    Headed runs only (Phase 4.7): mark failed tests whose errors say a human
    closed the window as "skipped" with a comment. Also tag
    no_interaction_close=True when the first-attempt duration is below the
    threshold (browser was closed before any action in the spec could complete).
    Headless/CI runs have no human to close anything: a browser-close error
    stays a failure, tagged error_kind="browser_closed".
    Returns (results, total_browser_close_count).
    """
    count = 0
    for r in results:
        if r.get("status") == "failed" and not headed:
            if any(_is_browser_close_error(e) for e in r.get("errors", [])):
                r["error_kind"] = "browser_closed"
                r["comment"] = _HEADLESS_CLOSE_COMMENT
            continue
        if r.get("status") == "failed":
            if any(_is_human_close_error(e) for e in r.get("errors", [])):
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
    headed: bool = True,
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
    results, _ = _mark_browser_close_as_skipped(results, headed=headed)

    completed_basenames = {os.path.basename(r.get("spec_file", "")) for r in results}

    # If JSON is empty, recover what we can from list-reporter stdout lines
    if not results:
        results, completed_basenames = _parse_list_output(stdout)

    # Append "not started" skipped entries for specs not yet reached.
    # ts_files may be relative paths ("M02/test_BS-001….spec.ts") while
    # completed_basenames holds bare basenames — compare like-for-like.
    for spec in ts_files:
        if not str(spec).endswith(".spec.ts"):
            continue    # a folder target (per-module / grep runs) is not a spec
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


def _resolve_cmd(cmd: List[str]) -> Union[List[str], str]:
    """Resolve cmd[0] to a full executable path so the command can run without
    a shell. On Windows `npx` is `npx.cmd`, which CreateProcess only finds via
    PATHEXT lookup — the old workaround ran everything through `shell=True`,
    and cmd.exe then mis-parsed any unquoted path containing `(`/`)` (e.g. a
    user profile directory named like `Name(Org)`), failing every run with rc=1.
    Phase 4: a .cmd target still runs through cmd.exe, so tools/execution/cmdline.py quotes its metacharacters
    (a `|` in --grep used to become a pipe)."""
    return resolve_cmd(cmd)


_cmd_exe_line = cmd_exe_line


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
