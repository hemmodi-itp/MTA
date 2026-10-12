"""
config.py — the `execution:` block of project.yaml (Phase 4).

    execution:
      matrix: [chromium]                # + firefox | webkit | pixel-7 | iphone-14 (profile smoke -> chromium only)
      test_id_attribute: data-testid    # Playwright's default (sauceLabs keeps data-test explicitly)
      locale: null                      # -> use.locale
      timezone_id: null                 # -> use.timezoneId
      trace: retain-on-failure
      video: retain-on-failure
      screenshot: only-on-failure
      junit: true                       # reports/junit/{ts}.xml
      mta_reporter: true                # reports/mta/{ts}.mta_results.json
      role_auth: false                  # true -> log in every auth.roles role before each run
      role_auth_max_age_minutes: 30
      suite_mode: files                 # files (legacy path targeting) | grep (test_suites/*.json -> --grep)
      shards: 1                         # > 1 -> run N shards locally + merge-reports
      max_parallel_shards: 1
      # Phase 4 (session 2)
      retries: auto                     # auto = 2 in CI, 1 locally; 0-5 overrides. Headed runs always use 0.
      fail_on_flaky_tests: auto         # auto = true in CI (exit code only)
      data_isolation: false             # true -> fullyParallel: true (specs create their data through testData)
      console_guard: warn               # off | warn | fail — new console/page errors vs baseline.json
      network: on-failure               # off | on-failure | on — request log + redacted HAR attachment
      cleanup_failure: warn             # warn | fail — a cleanup error is always reported; fail also fails the test
      test_steps: true                  # renderer: one test.step per plan step
      module_roles: false               # renderer: modules[].role -> test.use({ role }) instead of setup steps

The TypeScript config builder (application_assets/_shared/runtime/config/buildConfig.ts) resolves the
same block for hand runs. Both sides are tested against tests/fixtures/execution_config_cases.json, so
keep the two in step: same keys, same defaults, same fallback for an invalid value (default + warning).
Never raises.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional

import yaml

from tools import constants

_log = logging.getLogger("workflow.execution")

# Playwright project names, in the order they are emitted. Names are slugs (no spaces):
# UIExecutionAgent's list-reporter regex reads the project name as [\w-]+.
KNOWN_PROJECTS = ("chromium", "firefox", "webkit", "pixel-7", "iphone-14")

TRACE_MODES = ("off", "on", "retain-on-failure", "on-first-retry", "on-all-retries", "retain-on-first-failure")
VIDEO_MODES = ("off", "on", "retain-on-failure", "on-first-retry")
SCREENSHOT_MODES = ("off", "on", "only-on-failure", "on-first-failure")
SUITE_MODES = ("files", "grep")
CONSOLE_GUARD_MODES = ("off", "warn", "fail")
NETWORK_MODES = ("off", "on-failure", "on")
CLEANUP_FAILURE_MODES = ("warn", "fail")

DEFAULTS: Dict[str, Any] = {
    "matrix": ["chromium"],
    "test_id_attribute": "data-testid",
    "locale": None,
    "timezone_id": None,
    "trace": "retain-on-failure",
    "video": "retain-on-failure",
    "screenshot": "only-on-failure",
    "junit": True,
    "mta_reporter": True,
    "role_auth": False,
    "role_auth_max_age_minutes": 30,
    "suite_mode": "files",
    "shards": 1,
    "max_parallel_shards": 1,
    "retries": "auto",
    "fail_on_flaky_tests": "auto",
    "data_isolation": False,
    "console_guard": "warn",
    "network": "on-failure",
    "cleanup_failure": "warn",
    "test_steps": True,
    "module_roles": False,
}

_ATTR_RE = re.compile(r"^[A-Za-z_][\w.:-]*$")


def project_slug(name: Any) -> str:
    """'Pixel 7' / 'pixel_7' / 'PIXEL-7' -> 'pixel-7'."""
    return re.sub(r"[\s_]+", "-", str(name).strip().lower())


def _warn(key: str, value: Any, default: Any) -> None:
    _log.warning("[execution] invalid execution.%s=%r — using %r", key, value, default)


def _enum(block: dict, key: str, allowed) -> Any:
    if key not in block or block[key] is None:
        return DEFAULTS[key]
    value = str(block[key]).strip()
    if value in allowed:
        return value
    _warn(key, block[key], DEFAULTS[key])
    return DEFAULTS[key]


def _bool(block: dict, key: str) -> bool:
    value = block.get(key, DEFAULTS[key])
    if isinstance(value, bool):
        return value
    _warn(key, value, DEFAULTS[key])
    return DEFAULTS[key]


def _int(block: dict, key: str, lo: int, hi: int) -> int:
    value = block.get(key, DEFAULTS[key])
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value or not lo <= value <= hi:
        _warn(key, value, DEFAULTS[key])
        return DEFAULTS[key]
    return int(value)


def _opt_str(block: dict, key: str) -> Optional[str]:
    value = block.get(key)
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    _warn(key, value, None)
    return None


def _auto_int(block: dict, key: str, lo: int, hi: int) -> Any:
    """'auto' or an int in [lo, hi]."""
    value = block.get(key, DEFAULTS[key])
    if value is None or (isinstance(value, str) and value.strip().lower() == "auto"):
        return "auto"
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value or not lo <= value <= hi:
        _warn(key, value, DEFAULTS[key])
        return DEFAULTS[key]
    return int(value)


def _auto_bool(block: dict, key: str) -> Any:
    """'auto' or a bool."""
    value = block.get(key, DEFAULTS[key])
    if value is None or (isinstance(value, str) and value.strip().lower() == "auto"):
        return "auto"
    if isinstance(value, bool):
        return value
    _warn(key, value, DEFAULTS[key])
    return DEFAULTS[key]


def _is_ci(env: Optional[dict] = None) -> bool:
    return bool((env if env is not None else os.environ).get("CI"))


def effective_retries(cfg: Dict[str, Any], *, headed: bool = False, env: Optional[dict] = None) -> int:
    """execution.retries for one run: headed -> 0 (a human closing the window must not relaunch the test);
    'auto' -> 2 in CI, 1 locally. Mirrors buildConfig.ts::effectiveRetries."""
    if headed:
        return 0
    value = cfg.get("retries", "auto")
    if value == "auto":
        return 2 if _is_ci(env) else 1
    return int(value)


def effective_fail_on_flaky(cfg: Dict[str, Any], env: Optional[dict] = None) -> bool:
    value = cfg.get("fail_on_flaky_tests", "auto")
    return _is_ci(env) if value == "auto" else bool(value)


def resolve_projects(matrix: List[str], profile: Optional[str]) -> List[str]:
    """Enabled Playwright project names: chromium always first, then the known matrix entries in
    KNOWN_PROJECTS order. Profile `smoke` -> chromium only."""
    wanted = {project_slug(m) for m in matrix}
    if profile == "smoke":
        if wanted - {"chromium"}:
            _log.warning("[execution] test_generation.profile=smoke runs chromium only — ignoring matrix %s",
                         sorted(wanted - {"chromium"}))
        return ["chromium"]
    return [p for p in KNOWN_PROJECTS if p == "chromium" or p in wanted]


def resolve_execution_config(raw: Optional[dict]) -> Dict[str, Any]:
    """project.yaml dict -> resolved execution config (defaults filled; `projects` added)."""
    raw = raw if isinstance(raw, dict) else {}
    block = raw.get("execution") if isinstance(raw.get("execution"), dict) else {}

    matrix_raw = block.get("matrix", DEFAULTS["matrix"])
    if isinstance(matrix_raw, str):
        matrix_raw = [matrix_raw]
    if not isinstance(matrix_raw, list):
        _warn("matrix", matrix_raw, DEFAULTS["matrix"])
        matrix_raw = list(DEFAULTS["matrix"])
    matrix: List[str] = []
    for entry in matrix_raw:
        slug = project_slug(entry)
        if slug not in KNOWN_PROJECTS:
            _log.warning("[execution] unknown execution.matrix entry %r — ignored (known: %s)",
                         entry, ", ".join(KNOWN_PROJECTS))
        elif slug not in matrix:
            matrix.append(slug)

    attr = block.get("test_id_attribute", DEFAULTS["test_id_attribute"])
    if not (isinstance(attr, str) and _ATTR_RE.match(attr.strip())):
        _warn("test_id_attribute", attr, DEFAULTS["test_id_attribute"])
        attr = DEFAULTS["test_id_attribute"]

    tg = raw.get("test_generation") if isinstance(raw.get("test_generation"), dict) else {}
    profile = str(tg.get("profile")).strip().lower() if tg.get("profile") else None

    cfg = {
        "matrix": matrix,
        "test_id_attribute": attr.strip(),
        "locale": _opt_str(block, "locale"),
        "timezone_id": _opt_str(block, "timezone_id"),
        "trace": _enum(block, "trace", TRACE_MODES),
        "video": _enum(block, "video", VIDEO_MODES),
        "screenshot": _enum(block, "screenshot", SCREENSHOT_MODES),
        "junit": _bool(block, "junit"),
        "mta_reporter": _bool(block, "mta_reporter"),
        "role_auth": _bool(block, "role_auth"),
        "role_auth_max_age_minutes": _int(block, "role_auth_max_age_minutes", 0, 100_000),
        "suite_mode": _enum(block, "suite_mode", SUITE_MODES),
        "shards": _int(block, "shards", 1, 64),
        "max_parallel_shards": _int(block, "max_parallel_shards", 1, 16),
        "retries": _auto_int(block, "retries", 0, 5),
        "fail_on_flaky_tests": _auto_bool(block, "fail_on_flaky_tests"),
        "data_isolation": _bool(block, "data_isolation"),
        "console_guard": _enum(block, "console_guard", CONSOLE_GUARD_MODES),
        "network": _enum(block, "network", NETWORK_MODES),
        "cleanup_failure": _enum(block, "cleanup_failure", CLEANUP_FAILURE_MODES),
        "test_steps": _bool(block, "test_steps"),
        "module_roles": _bool(block, "module_roles"),
    }
    cfg["projects"] = resolve_projects(matrix, profile)
    return cfg


def load_execution_config(safe_project: str) -> Dict[str, Any]:
    """Resolve straight from application_assets/projects/<project>/project.yaml (PROJECTS_BASE read at call time)."""
    path = os.path.join(constants.PROJECTS_BASE, safe_project, "project.yaml")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        raw = {}
    return resolve_execution_config(raw)
