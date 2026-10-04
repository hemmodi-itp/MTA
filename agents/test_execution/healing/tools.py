"""
tools.py — ADK FunctionTool definitions for HealingAgent's diagnose -> repair ->
verify loop.

Every tool is a thin closure (built by build_tools(ctx)) over a module-level,
directly-testable helper function that operates on a HealingRunContext. This
keeps the actual diagnosis/repair/patch logic unit-testable without spinning up
ADK or a live LLM — only the closures know about ToolContext/FunctionTool.

No function here can write to business_scenarios.json, acceptance criteria,
assertion values, intents.yaml, dom_intents.json, or any workflows/*.yaml —
that is the structural safety boundary: the tool surface simply has no path to
those files.
"""

import concurrent.futures
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from tools.test_creation.script_generator.build_dom_locator_map import get_playwright_expr, repair_named_locator

_SPEC_SCRIPTS_MARKER = "test_creation/test_scripts/"

_LOCATOR_CALL_RE = re.compile(
    r"page\.(getByPlaceholder|getByRole|getByText|getByLabel|getByTestId|locator)\("
    r"""(['"])((?:(?!\2).)*)\2"""
    r"""(?:\s*,\s*\{\s*name:\s*(['"])((?:(?!\4).)*)\4\s*\})?"""
    r"\)"
)

# action-library specs call `action.<verb>('locator_key', ...)` / `pageObject
# getters — never a raw page.getBy*(...) call — so _LOCATOR_CALL_RE matches
# nothing in them. This is the equivalent extraction for that spec shape.
_ACTION_CALL_RE = re.compile(r"action\.\w+\(\s*['\"]([\w.-]+)['\"]")

_GOTO_RE = re.compile(r"""page\.goto\(\s*['"]([^'"]*)['"]""")

_FILL_LITERAL_RE = re.compile(r"""\.fill\(\s*['"]([^'"]*)['"]\s*\)""")

_SPEC_ID_RE = re.compile(r"([A-Za-z]+\d+_BS_\d+|BS-\d+|SC-\d+)")

# Matches both the raw Node ENOENT text (older/legacy runtime builds) and the
# clearer message ActionEngine.uploadFile() now throws instead — see
# application_assets/_shared/runtime/ActionEngine.ts.
_FIXTURE_MISSING_RE = re.compile(
    r"(?:ENOENT: no such file or directory, stat|Upload fixture not found:) '([^']+)'"
)

_DEPRECATED_API_SUBS = [
    (re.compile(r"page\.\$eval\("), "page.locator("),
    (re.compile(r"""page\.click\((['"][^'"]+['"])\)"""), r"page.locator(\1).click()"),
    (re.compile(r"""page\.fill\((['"][^'"]+['"])\s*,"""), r"page.locator(\1).fill("),
    (re.compile(r"page\.waitForSelector\("), "page.locator("),
]


class HealingRunContext:
    """Mutable, process-local state for one HealingAgent.execute() call.

    Deliberately NOT stored in ADK session state — a live Playwright Page
    can't be JSON-serialized, and every tool call runs in the same process as
    agent.py's asyncio.run() bridge, so plain Python state is simpler and
    sufficient.
    """

    def __init__(
        self,
        project_name: str,
        scripts_dir: str,
        reports_dir: str,
        report_json: str,
        dom_elements: List[Dict[str, Any]],
        module_urls: Dict[str, str],
        default_url: str,
        test_data_map: Dict[str, Any],
        settings: dict,
        logger,
        generation_modes: Optional[Dict[str, str]] = None,
        locator_map: Optional[Dict[str, Any]] = None,
        locator_map_path: str = "",
        comprehension_dir: str = "",
    ):
        self.project_name = project_name
        self.scripts_dir = scripts_dir
        self.reports_dir = reports_dir
        self.report_json = report_json
        self.dom_elements = dom_elements
        self.module_urls = module_urls
        self.default_url = default_url
        self.test_data_map = test_data_map
        self.settings = settings
        self.logger = logger
        # {spec_file: "action_library"} from test_suite.json — a spec absent
        # here (or any other value) is a legacy raw-TS spec and keeps using
        # the original page.getBy*(...) patch-the-.spec.ts path unchanged.
        self.generation_modes = generation_modes or {}
        self.locator_map = locator_map or {}
        self.locator_map_path = locator_map_path
        self.comprehension_dir = comprehension_dir

        self.remaining: Dict[str, Dict[str, str]] = {}
        self.not_healable: List[Dict[str, str]] = []
        self.healed_specs: set = set()
        self.tests_healed: int = 0
        self.rounds: List[Dict[str, Any]] = []
        self.validation_pages: Dict[str, Tuple[Any, Any]] = {}
        self._pw_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None

    def remaining_total(self) -> int:
        return sum(len(v) for v in self.remaining.values())

    def pw_executor(self) -> concurrent.futures.ThreadPoolExecutor:
        """A single dedicated worker thread for every sync-Playwright call.

        Required because tool calls run inside HealingAgent's own asyncio
        event loop (the ADK bridge) — Playwright's sync API refuses to run in
        any thread that has a running event loop, so every launch/goto/
        locator check must be submitted to this plain OS thread instead."""
        if self._pw_executor is None:
            self._pw_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        return self._pw_executor

    def close(self) -> None:
        """Close every launched browser and shut down the worker thread."""
        if self._pw_executor is not None:
            for scanner, _page in self.validation_pages.values():
                if scanner is not None:
                    try:
                        self._pw_executor.submit(scanner.close).result(timeout=10)
                    except Exception:
                        pass
            self._pw_executor.shutdown(wait=False)


# ── Report parsing (module-relative spec keys — fixes the old basename() bug) ──

def _spec_key_from_report_path(file_path: str) -> str:
    """Return the spec path relative to test_creation/test_scripts/, preserving
    any module subdirectory (e.g. 'M01/test_BS_006.spec.ts'). Falls back to the
    bare basename if the marker segment isn't present in the reported path."""
    norm = (file_path or "").replace("\\", "/")
    idx = norm.find(_SPEC_SCRIPTS_MARKER)
    if idx >= 0:
        return norm[idx + len(_SPEC_SCRIPTS_MARKER):]
    return os.path.basename(norm)


def _iter_suites(suites: list):
    for suite in suites:
        yield suite
        for child in _iter_suites(suite.get("suites", [])):
            yield child


def _get_failing_tests(report_json: str, logger) -> Dict[str, List[str]]:
    """Return {spec_key: [failing_test_title, ...]}."""
    if not report_json or not os.path.exists(report_json):
        return {}
    try:
        with open(report_json, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning(f"Could not read report: {exc}")
        return {}

    failing: Dict[str, List[str]] = {}
    for suite in _iter_suites(data.get("suites", [])):
        for spec in suite.get("specs", []):
            spec_key = _spec_key_from_report_path(spec.get("file", ""))
            for test in spec.get("tests", []):
                status = test.get("status", "")
                # "flaky" = failed its first attempt but passed on Playwright's
                # own retry — already a real pass, same as ui_execution/agent.py
                # treats it. Without this, HealingAgent would burn a repair
                # cycle "fixing" a test that already recovered on its own,
                # potentially patching a perfectly fine locator based on a
                # one-off timing hiccup.
                if status not in ("passed", "expected", "flaky"):
                    failing.setdefault(spec_key, []).append(spec.get("title", ""))
    return failing


def _get_error_for_test(report_json: str, spec_key: str, test_name: str) -> str:
    if not report_json or not os.path.exists(report_json):
        return ""
    try:
        with open(report_json, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""
    for suite in _iter_suites(data.get("suites", [])):
        for spec in suite.get("specs", []):
            if _spec_key_from_report_path(spec.get("file", "")) != spec_key:
                continue
            if spec.get("title", "") != test_name:
                continue
            for test in spec.get("tests", []):
                for result in test.get("results", []):
                    err = result.get("error", {})
                    if err:
                        return err.get("message", "") or err.get("value", "")
    return ""


# ── Spec block extraction — generalized start-anchor (fixes the old regex
#    that required the literal 'async' keyword and couldn't match test.skip/
#    test.fixme stubs) ────────────────────────────────────────────────────────

def _extract_test_block(spec_content: str, test_name: str) -> str:
    escaped = re.escape(test_name)
    pattern = rf"""([ \t]*test(?:\.skip|\.fixme)?\(['"]{escaped}['"]\s*,\s*(?:async\s*)?[^\n]*\{{)"""
    m = re.search(pattern, spec_content)
    if not m:
        return ""

    start = m.start()
    # depth starts at 1 and scanning at m.end(): the match itself already
    # consumed the block's opening brace. Starting the scan at m.start()
    # instead (as a prior version of this function did) double-counts any
    # brace inside the header itself — e.g. async ({ page }) => { — closing
    # the destructured-params brace would falsely zero out the depth counter
    # and truncate the block right after the parameter list.
    depth = 1
    i = m.end()
    in_string = None
    while i < len(spec_content):
        ch = spec_content[i]
        if in_string:
            if ch == "\\" and i + 1 < len(spec_content):
                i += 2
                continue
            if ch == in_string:
                in_string = None
        else:
            if ch in ('"', "'", "`"):
                in_string = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return spec_content[start:i + 3]
        i += 1
    return ""


def _read_test_block(ctx: HealingRunContext, spec_file: str, test_name: str) -> Optional[str]:
    spec_path = os.path.join(ctx.scripts_dir, spec_file)
    if not os.path.exists(spec_path):
        return None
    with open(spec_path, encoding="utf-8") as f:
        content = f.read()
    block = _extract_test_block(content, test_name)
    return block or None


def _structurally_valid_block(block: str) -> bool:
    if not block or not block.strip():
        return False
    if not re.search(r"test(?:\.skip|\.fixme)?\(", block):
        return False
    if block.count("{") != block.count("}"):
        return False
    if block.count("(") != block.count(")"):
        return False
    return True


# ── Locator call parsing/building (Python side, for live dry-run checks) ─────

def _extract_locator_calls(text: str) -> List[Tuple[str, str, Optional[str]]]:
    calls = []
    for m in _LOCATOR_CALL_RE.finditer(text):
        method, _, primary, _, role_name = m.groups()
        calls.append((method, primary, role_name))
    return calls


def _format_call(method: str, primary: str, role_name: Optional[str]) -> str:
    if role_name is not None:
        return f"page.{method}('{primary}', {{ name: '{role_name}' }})"
    return f"page.{method}('{primary}')"


def _build_python_locator(page, method: str, primary: str, role_name: Optional[str]):
    if method == "getByPlaceholder":
        return page.get_by_placeholder(primary)
    if method == "getByRole":
        return page.get_by_role(primary, name=role_name) if role_name is not None else page.get_by_role(primary)
    if method == "getByText":
        return page.get_by_text(primary)
    if method == "getByLabel":
        return page.get_by_label(primary)
    if method == "getByTestId":
        return page.get_by_test_id(primary)
    if method == "locator":
        return page.locator(primary)
    return None


def _live_locator_resolves(ctx: "HealingRunContext", page, expr: str) -> bool:
    calls = _extract_locator_calls(expr)
    if not calls:
        return False
    method, primary, role_name = calls[0]

    def _check():
        locator = _build_python_locator(page, method, primary, role_name)
        # A replacement candidate matching 2+ elements is exactly as broken
        # as one matching 0 — see _locator_entry_resolves for the same fix.
        return locator is not None and locator.count() == 1

    try:
        return ctx.pw_executor().submit(_check).result()
    except Exception:
        return False


def _module_id_from_spec_file(spec_file: str) -> str:
    """Return the leading module subdirectory of a spec key (e.g. 'M01' from
    'M01/test_x.spec.ts'), or '' for a flat, non-module-scoped project."""
    parts = (spec_file or "").replace("\\", "/").split("/")
    return parts[0] if len(parts) > 1 else ""


def _url_for_spec_file(ctx: HealingRunContext, spec_file: str) -> str:
    """Projects commonly declare url per-module (project.yaml modules[].url)
    rather than at the top level — resolve whichever applies to this spec."""
    module_id = _module_id_from_spec_file(spec_file)
    return ctx.module_urls.get(module_id) or ctx.default_url


def _get_validation_page(ctx: HealingRunContext, module_id: str = ""):
    """Lazily launch (and cache, per module) one headless page for live
    locator dry-run checks — reused across every tool call in this run that
    targets the same module. Returns (scanner, page), both None if a browser
    genuinely can't be launched — callers must treat that as 'can't verify',
    not a rejection."""
    if module_id in ctx.validation_pages:
        return ctx.validation_pages[module_id]

    def _launch():
        from tools.playwright_scanner import PlaywrightScanner
        scanner = PlaywrightScanner(headless=True)
        page = scanner.launch()
        url = ctx.module_urls.get(module_id) or ctx.default_url
        if url:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
        return scanner, page

    try:
        ctx.validation_pages[module_id] = ctx.pw_executor().submit(_launch).result()
    except Exception as exc:
        ctx.logger.warning(f"Locator dry-run page unavailable for module '{module_id}': {exc}")
        ctx.validation_pages[module_id] = (None, None)
    return ctx.validation_pages[module_id]


def _element_text_blob(el: dict) -> str:
    """Collect every human-readable text field an element carries. Checks both
    a flat compact-summary shape (description/text_content/aria_label/
    placeholder at the top level) and the real dom_elements.json shape (
    display_text at the top level, the rest nested under semantic_locators)
    — the two schemas coexist depending on what produced the element list."""
    semantic = el.get("semantic_locators") or {}
    parts = [
        el.get("description", ""),
        el.get("text_content", ""),
        el.get("display_text", ""),
        el.get("aria_label", ""),
        el.get("placeholder", ""),
        semantic.get("aria_label", ""),
        semantic.get("label", ""),
        semantic.get("placeholder", ""),
        semantic.get("title", ""),
    ]
    parts.extend(el.get("intent_hints") or [])
    return " ".join(p for p in parts if isinstance(p, str) and p)


def _rank_candidate_elements(dom_elements: List[dict], primary: str, role_name: Optional[str]) -> List[dict]:
    """Rank DOM elements by keyword overlap against the failing locator's own
    text, so live-checking tries the most plausible replacement first."""
    query_tokens = set(re.findall(r"\w+", f"{primary} {role_name or ''}".lower()))
    if not query_tokens:
        return []
    scored = []
    for el in dom_elements:
        tokens = set(re.findall(r"\w+", _element_text_blob(el).lower()))
        overlap = len(query_tokens & tokens)
        if overlap > 0:
            scored.append((overlap, el))
    scored.sort(key=lambda x: -x[0])
    return [el for _, el in scored[:8]]


# ── Repair-proposal logic ─────────────────────────────────────────────────────

def _read_failure_report(ctx: HealingRunContext) -> dict:
    failing = _get_failing_tests(ctx.report_json, ctx.logger)
    ctx.remaining = {}
    for spec_key, test_names in failing.items():
        entry = {}
        for tn in test_names:
            entry[tn] = _get_error_for_test(ctx.report_json, spec_key, tn)
        ctx.remaining[spec_key] = entry
    return {
        "failing_tests": [
            {"spec_file": sf, "test_name": tn, "error_message": err}
            for sf, tests in ctx.remaining.items()
            for tn, err in tests.items()
        ],
        "total_failing": ctx.remaining_total(),
    }


def _locator_entry_resolves(page, entry: dict) -> bool:
    """Same {type, locator, name?} -> Locator resolution ActionEngine/
    LocatorManager.ts perform at test-run time, done in Python for a live
    dry-run check. Deliberately duplicated from ScriptGenerationAgent's
    equivalent rather than a cross-agent import — HealingAgent doesn't
    depend on ScriptGenerationAgent's package."""
    t = entry.get("type")
    v = entry.get("locator", "")
    name = entry.get("name")
    try:
        if t == "css":
            locator = page.locator(v)
        elif t == "xpath":
            locator = page.locator(f"xpath={v}")
        elif t == "role":
            locator = page.get_by_role(v, name=name) if name else page.get_by_role(v)
        elif t == "text":
            locator = page.get_by_text(v)
        elif t == "label":
            locator = page.get_by_label(v)
        elif t == "testid":
            locator = page.get_by_test_id(v)
        elif t == "placeholder":
            locator = page.get_by_placeholder(v)
        else:
            return True  # unknown type — can't check, don't reject
        # Exactly 1, not just >0: a locator matching 2+ elements (e.g. two
        # "Sign in" buttons — one text, one icon, shown responsively) is a
        # Playwright strict-mode violation at actual runtime just as surely
        # as matching 0 — the old ">0" check reported these as fine.
        return locator.count() == 1
    except Exception:
        return True  # a resolution error is "can't tell", not a rejection


def _propose_locator_fix_action_library(ctx: HealingRunContext, spec_file: str, test_name: str) -> dict:
    """Locator diagnosis/repair for a plan-rendered (generation_mode ==
    "action_library") spec: extract the implicated locator_key(s) from
    `action.<verb>('key', ...)` calls (not raw page.getBy*(...) — those don't
    appear in this spec shape), live-check each against locator_map.json, and
    — unlike the legacy path — repair a confirmed-broken key directly via
    repair_named_locator instead of proposing a .spec.ts patch. No block
    replacement needed: fixing the one shared locator_map.json entry fixes
    every spec that references the key."""
    block = _read_test_block(ctx, spec_file, test_name)
    if block is None:
        return {"resolved": False, "reason": f"test block '{test_name}' not found in {spec_file}"}

    keys = _ACTION_CALL_RE.findall(block)
    if not keys:
        return {"resolved": False, "reason": "no action.<verb>('locator_key', ...) call in the failing block"}

    _scanner, page = _get_validation_page(ctx, _module_id_from_spec_file(spec_file))
    if page is None:
        return {"resolved": False, "reason": "headless validation page unavailable — cannot live-check locators"}

    for key in keys:
        entry = ctx.locator_map.get(key)
        if not entry:
            continue
        try:
            resolves = ctx.pw_executor().submit(_locator_entry_resolves, page, entry).result()
        except Exception:
            resolves = True
        if resolves:
            continue  # this key is fine — the failure is something else

        repaired = repair_named_locator(ctx.locator_map_path, ctx.comprehension_dir, key)
        if not repaired:
            return {
                "resolved": False,
                "reason": f"locator_key '{key}' failed live resolution and could not be repaired "
                          "automatically (no confident match on re-scan) — needs a human to update "
                          "locator_map.json",
            }
        with open(ctx.locator_map_path, encoding="utf-8") as f:
            ctx.locator_map = json.load(f)
        return {
            "resolved": True,
            "applied": True,
            "repaired_key": key,
            "note": "locator_map.json entry repaired directly — no apply_patch needed for this fix, call run_tests next",
        }

    return {
        "resolved": False,
        "reason": "every locator_key in the failing block already resolves live — the failure is likely not a locator issue",
    }


def _propose_locator_fix(ctx: HealingRunContext, spec_file: str, test_name: str) -> dict:
    if ctx.generation_modes.get(spec_file) == "action_library":
        return _propose_locator_fix_action_library(ctx, spec_file, test_name)

    block = _read_test_block(ctx, spec_file, test_name)
    if block is None:
        return {"resolved": False, "reason": f"test block '{test_name}' not found in {spec_file}"}

    calls = _extract_locator_calls(block)
    if not calls:
        return {"resolved": False, "reason": "no recognizable Playwright locator call in the failing block"}

    _scanner, page = _get_validation_page(ctx, _module_id_from_spec_file(spec_file))
    if page is None:
        return {"resolved": False, "reason": "headless validation page unavailable — cannot live-check locators"}

    for method, primary, role_name in calls:
        candidates = _rank_candidate_elements(ctx.dom_elements, primary, role_name)
        for el in candidates:
            expr = get_playwright_expr(el)
            if not expr:
                continue
            if _live_locator_resolves(ctx, page, expr):
                return {
                    "resolved": True,
                    "old_call": _format_call(method, primary, role_name),
                    "new_expr": expr,
                }
    return {"resolved": False, "reason": "no DOM element resolved a working replacement locator"}


def _propose_timing_fix(ctx: HealingRunContext, spec_file: str, test_name: str) -> dict:
    block = _read_test_block(ctx, spec_file, test_name)
    if block is None:
        return {"is_timing_issue": False, "reason": f"test block '{test_name}' not found in {spec_file}"}

    calls = _extract_locator_calls(block)
    if not calls:
        return {"is_timing_issue": False, "reason": "no locator call found in the failing block"}

    _scanner, page = _get_validation_page(ctx, _module_id_from_spec_file(spec_file))
    if page is None:
        return {"is_timing_issue": False, "reason": "validation page unavailable"}

    method, primary, role_name = calls[0]

    def _wait():
        locator = _build_python_locator(page, method, primary, role_name)
        locator.wait_for(timeout=15000)

    try:
        ctx.pw_executor().submit(_wait).result()
        return {
            "is_timing_issue": True,
            "locator": _format_call(method, primary, role_name),
            "resolved_within_ms": 15000,
        }
    except Exception:
        return {
            "is_timing_issue": False,
            "reason": "locator still does not resolve given a longer wait — likely a stale selector, not a race",
        }


def _propose_compilation_fix(ctx: HealingRunContext, spec_file: str, test_name: str) -> dict:
    block = _read_test_block(ctx, spec_file, test_name)
    if block is None:
        return {"fixed": False, "reason": f"test block '{test_name}' not found in {spec_file}"}

    if block.count("{") != block.count("}"):
        return {"fixed": False, "reason": "unbalanced braces in block — cannot safely auto-patch"}

    new_block = block
    applied = []
    for pattern, repl in _DEPRECATED_API_SUBS:
        if pattern.search(new_block):
            new_block = pattern.sub(repl, new_block)
            applied.append(pattern.pattern)

    if not applied:
        return {"fixed": False, "reason": "no known deprecated/incorrect Playwright API pattern detected"}
    return {"fixed": True, "new_block": new_block, "patterns_fixed": applied}


def _propose_test_data_fix(ctx: HealingRunContext, spec_file: str, test_name: str) -> dict:
    block = _read_test_block(ctx, spec_file, test_name)
    if block is None:
        return {"fixed": False, "reason": f"test block '{test_name}' not found in {spec_file}"}

    m = _SPEC_ID_RE.search(spec_file)
    if not m:
        return {"fixed": False, "reason": "could not determine scenario id from spec filename"}

    scenario_id = m.group(1)
    dataset = ctx.test_data_map.get(scenario_id)
    if not dataset:
        return {"fixed": False, "reason": f"no test_data.json entry for {scenario_id}"}

    # Real test_data.json schema: positive_dataset is a list of
    # {field_name, field_type, value} records, not a flat {name: value} dict.
    positive_fields = dataset.get("positive_dataset")
    if not isinstance(positive_fields, list):
        positive_fields = []
    expected = {
        f["field_name"]: f.get("value", "")
        for f in positive_fields
        if isinstance(f, dict) and f.get("field_name")
    }
    expected_values = {str(v) for v in expected.values() if v not in (None, "")}
    literals = _FILL_LITERAL_RE.findall(block)
    stale = [v for v in literals if v and v not in expected_values]

    if not stale:
        return {"fixed": False, "reason": "no stale literal test-data values found in block"}
    return {
        "fixed": False,
        "reason": "stale literal value(s) found — use expected_dataset to build the replacement block via apply_patch",
        "stale_values": stale,
        "expected_dataset": expected,
    }


def _propose_navigation_fix(ctx: HealingRunContext, spec_file: str, test_name: str) -> dict:
    block = _read_test_block(ctx, spec_file, test_name)
    if block is None:
        return {"fixed": False, "reason": f"test block '{test_name}' not found in {spec_file}"}

    m = _GOTO_RE.search(block)
    if not m:
        return {"fixed": False, "reason": "no page.goto(...) call found in the failing block"}

    hardcoded_url = m.group(1)
    configured_url = _url_for_spec_file(ctx, spec_file)
    if not configured_url:
        return {"fixed": False, "reason": "project.yaml has no configured url to compare against"}

    if hardcoded_url.rstrip("/") == configured_url.rstrip("/"):
        return {
            "fixed": False,
            "reason": "goto() URL already matches project.yaml's configured url — "
                      "this looks like an unreachable environment, not a config mismatch",
        }

    new_block = block.replace(m.group(0), f"page.goto('{configured_url}'")
    return {"fixed": True, "old_url": hardcoded_url, "new_url": configured_url, "new_block": new_block}


def _propose_fixture_fix(ctx: HealingRunContext, spec_file: str, test_name: str) -> dict:
    """Detect a missing-upload-fixture failure (ActionEngine.uploadFile()'s
    ENOENT / "Upload fixture not found" error) — a test-data/fixture
    generation gap (TestDataAgent referenced a file it never created on
    disk), never a locator or timing problem, even though the error is
    tagged with a [locator_key=...] exactly like every other ActionEngine
    failure and could otherwise be misdiagnosed by propose_locator_fix as a
    stale selector. No tool in this file can create the missing file, so
    this is never itself a fix — it's a fast, confident classification
    that routes straight to mark_not_healable instead of burning a repair
    cycle re-scanning a perfectly fine locator."""
    error = ctx.remaining.get(spec_file, {}).get(test_name, "")
    match = _FIXTURE_MISSING_RE.search(error or "")
    if not match:
        return {
            "is_fixture_issue": False,
            "reason": "error message does not match a missing-fixture-file signature",
        }
    missing_file = match.group(1)
    return {
        "is_fixture_issue": True,
        "missing_file": missing_file,
        "reason": (
            f"Upload fixture '{missing_file}' does not exist on disk — this is a test-data/"
            "fixture generation gap, not a locator, timing, or navigation issue. No tool here "
            "can create a fixture file — call mark_not_healable with this reason rather than "
            "trying propose_locator_fix."
        ),
    }


def _apply_patch(ctx: HealingRunContext, spec_file: str, test_name: str, new_block: str) -> dict:
    if not _structurally_valid_block(new_block):
        return {
            "applied": False,
            "reason": "new_block failed structural validation — must be a non-empty "
                      "test(...)/test.skip(...)/test.fixme(...) block with balanced braces/parens",
        }

    spec_path = os.path.join(ctx.scripts_dir, spec_file)
    if not os.path.exists(spec_path):
        return {"applied": False, "reason": f"spec file not found: {spec_file}"}

    with open(spec_path, encoding="utf-8") as f:
        content = f.read()

    old_block = _extract_test_block(content, test_name)
    if not old_block:
        return {"applied": False, "reason": f"could not locate existing test block '{test_name}' in {spec_file}"}

    new_content = content.replace(old_block, new_block, 1)
    if new_content == content:
        return {"applied": False, "reason": "replacement produced no change to the file"}

    tmp_path = spec_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    os.replace(tmp_path, spec_path)

    ctx.healed_specs.add(spec_file)
    ctx.tests_healed += 1
    return {"applied": True, "spec_file": spec_file, "test_name": test_name}


def _remaining_summary(ctx: HealingRunContext) -> List[dict]:
    return [
        {"spec_file": sf, "test_name": tn, "error_message": err}
        for sf, tests in ctx.remaining.items()
        for tn, err in tests.items()
    ]


def _run_tests(ctx: HealingRunContext, spec_files: List[str]) -> dict:
    from agents.test_execution.ui_execution.agent import UIExecutionAgent

    agent = UIExecutionAgent(settings=ctx.settings)
    result = agent.execute(
        {"project_name": ctx.project_name, "spec_files": spec_files, "headless": True},
        {},
    )
    if result.get("status") not in ("success", "interrupted"):
        error = result.get("error", "ui_execution did not complete successfully")
        ctx.rounds.append({
            "round": len(ctx.rounds) + 1,
            "spec_files": list(spec_files),
            "ran": False,
            "passed": 0,
            "failed": 0,
            "remaining_after": ctx.remaining_total(),
            "error": error,
        })
        return {
            "ran": False,
            "error": error,
            "still_failing": _remaining_summary(ctx),
        }

    for r in result.get("results", []):
        spec_key = _spec_key_from_report_path(r.get("spec_file", ""))
        if spec_key not in ctx.remaining:
            spec_key = os.path.basename(r.get("spec_file", ""))
        title = r.get("test_title", "")
        if r.get("status") == "success":
            ctx.remaining.get(spec_key, {}).pop(title, None)
        elif spec_key in ctx.remaining and title in ctx.remaining[spec_key]:
            ctx.remaining[spec_key][title] = "; ".join(r.get("errors", [])) or r.get("comment", "")

    ctx.remaining = {sf: tests for sf, tests in ctx.remaining.items() if tests}
    ctx.rounds.append({
        "round": len(ctx.rounds) + 1,
        "spec_files": list(spec_files),
        "ran": True,
        "passed": result.get("passed", 0),
        "failed": result.get("failed", 0),
        "remaining_after": ctx.remaining_total(),
    })
    return {
        "ran": True,
        "passed": result.get("passed", 0),
        "failed": result.get("failed", 0),
        "still_failing": _remaining_summary(ctx),
        "all_resolved": not ctx.remaining,
    }


def _mark_not_healable(ctx: HealingRunContext, spec_file: str, test_name: str, reason: str) -> dict:
    ctx.not_healable.append({"spec_file": spec_file, "test_name": test_name, "reason": reason})
    if spec_file in ctx.remaining:
        ctx.remaining[spec_file].pop(test_name, None)
        if not ctx.remaining[spec_file]:
            del ctx.remaining[spec_file]
    return {"acknowledged": True, "remaining_total": ctx.remaining_total()}


# ── ADK FunctionTool factory ───────────────────────────────────────────────────

def build_tools(ctx: HealingRunContext) -> list:
    """Return the ADK FunctionTool list bound to this run's context. Import of
    google.adk.tools is local so this module stays importable (and its helper
    functions above stay directly unit-testable) even where google-adk isn't
    installed."""
    from google.adk.tools import FunctionTool

    def read_failure_report(tool_context) -> dict:
        """Parse the Playwright JSON failure report into structured failing
        test entries grouped by spec file. Call this first, before any repair
        tool, to see what needs healing."""
        return _read_failure_report(ctx)

    def propose_locator_fix(spec_file: str, test_name: str, tool_context) -> dict:
        """Live-re-resolve the failing test's locator against the current DOM
        (a headless page). For a legacy spec, proposes a replacement
        Playwright expression by priority order (getByPlaceholder > getByRole
        > getByText > name > id > css) for you to hand to apply_patch. For an
        action-library spec (generation_mode == "action_library" in
        test_suite.json), this ALREADY REPAIRS the shared locator_map.json
        entry directly when the result has "applied": true — do not call
        apply_patch for that case, go straight to run_tests instead."""
        return _propose_locator_fix(ctx, spec_file, test_name)

    def propose_timing_fix(spec_file: str, test_name: str, tool_context) -> dict:
        """Check whether the same locator resolves given a longer wait — a
        genuine race condition rather than a stale selector."""
        return _propose_timing_fix(ctx, spec_file, test_name)

    def propose_compilation_fix(spec_file: str, test_name: str, tool_context) -> dict:
        """Detect and fix deprecated/incorrect Playwright API shapes (e.g.
        page.$eval, page.click(selector)) preventing the test from compiling
        or running correctly."""
        return _propose_compilation_fix(ctx, spec_file, test_name)

    def propose_test_data_fix(spec_file: str, test_name: str, tool_context) -> dict:
        """Identify stale/conflicting literal test-data values baked into the
        failing block, returning the project's current expected dataset so a
        corrected block can be built."""
        return _propose_test_data_fix(ctx, spec_file, test_name)

    def propose_navigation_fix(spec_file: str, test_name: str, tool_context) -> dict:
        """Check the block's hardcoded page.goto(...) URL against project.yaml's
        configured url — a config/environment mismatch is fixable; a goto()
        that already matches the configured url is not (the environment
        itself is unreachable)."""
        return _propose_navigation_fix(ctx, spec_file, test_name)

    def propose_fixture_fix(spec_file: str, test_name: str, tool_context) -> dict:
        """Check whether the failure is a missing upload-fixture file (ENOENT
        / "Upload fixture not found" from an uploadFile action). If
        "is_fixture_issue": true, this can NEVER be healed by any other tool
        here (no tool creates files) — call mark_not_healable with the
        returned reason immediately, do not try propose_locator_fix even
        though the error carries a [locator_key=...] tag like every other
        ActionEngine failure."""
        return _propose_fixture_fix(ctx, spec_file, test_name)

    def apply_patch(spec_file: str, test_name: str, new_block: str, tool_context) -> dict:
        """Structurally validate new_block (non-empty, balanced braces/parens,
        a real test/test.skip/test.fixme block) and, if valid, atomically
        replace the named test block in spec_file. The ONLY tool that writes
        to a .spec.ts file."""
        return _apply_patch(ctx, spec_file, test_name, new_block)

    def run_tests(spec_files: list, tool_context) -> dict:
        """Re-run only these spec files (relative to test_scripts/) via
        UIExecutionAgent to verify a patch, reporting pass/fail per test. Ends
        the healing loop once no failing tests remain."""
        result = _run_tests(ctx, spec_files)
        if not ctx.remaining:
            tool_context.actions.escalate = True
        return result

    def mark_not_healable(spec_file: str, test_name: str, reason: str, tool_context) -> dict:
        """Declare a failure a real application/environment/JS/auth defect —
        it is never sent back through a repair tool again this run. Ends the
        healing loop once no failing tests remain."""
        result = _mark_not_healable(ctx, spec_file, test_name, reason)
        if not ctx.remaining:
            tool_context.actions.escalate = True
        return result

    return [
        FunctionTool(read_failure_report),
        FunctionTool(propose_locator_fix),
        FunctionTool(propose_timing_fix),
        FunctionTool(propose_compilation_fix),
        FunctionTool(propose_test_data_fix),
        FunctionTool(propose_navigation_fix),
        FunctionTool(propose_fixture_fix),
        FunctionTool(apply_patch),
        FunctionTool(run_tests),
        FunctionTool(mark_not_healable),
    ]
