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
import difflib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from tools.healing import audit, identity
from tools.healing.blast import specs_using_keys
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
        mode: str = "auto",
        proposals_dir: str = "",
        healable: Optional[set] = None,
        run_id: str = "",
        module_setups: Optional[Dict[str, list]] = None,
        flows_ts_path: str = "",
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
        # Phase 6-lean: "auto" applies patches; "propose" writes diffs to proposals_dir instead.
        self.mode = mode
        self.proposals_dir = proposals_dir
        self.proposals: List[Dict[str, str]] = []
        # {(spec_key, test_title)} triaged as test_defect.* -- None = no triage, heal everything.
        self.healable = healable
        # Phase 6.5-6.9: audit rows carry the run id; module setup steps sign the validation page in;
        # repaired locator keys (before/after) drive the blast-radius re-run and a revert on regression.
        self.run_id = run_id
        self.module_setups = module_setups or {}
        self.flows_ts_path = flows_ts_path
        self.repaired: Dict[str, Dict[str, Any]] = {}
        self.reverted: List[Dict[str, Any]] = []
        self.fixed: set = set()          # (spec_key, title) that failed and passed after a fix (burn-in input)
        self.review: List[Dict[str, Any]] = []
        self.passing_before: set = _passing_tests(report_json)

        self.remaining: Dict[str, Dict[str, str]] = {}
        self.not_healable: List[Dict[str, str]] = []
        self.healed_specs: set = set()
        self.tests_healed: int = 0
        self.rounds: List[Dict[str, Any]] = []
        self.validation_pages: Dict[str, Tuple[Any, Any]] = {}
        # one Playwright + browser per run (sync Playwright allows one per thread); one context per module (its login)
        self._scanner = None
        self._contexts: Dict[str, Any] = {}
        self._pw_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None

    def test_id_attribute(self) -> str:
        """The project's execution.test_id_attribute (Phase 4) — the attribute the TS runtime's
        getByTestId uses, so live checks look at the same attribute."""
        if not hasattr(self, "_test_id_attribute"):
            from tools.execution.config import load_execution_config
            safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in self.project_name).strip("_")
            self._test_id_attribute = load_execution_config(safe or "project")["test_id_attribute"]
        return self._test_id_attribute

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
            scanners = {id(sc): sc for sc, _page in self.validation_pages.values() if sc is not None}
            for scanner in scanners.values():
                try:
                    self._pw_executor.submit(scanner.close).result(timeout=10)
                except Exception:
                    pass
            self._pw_executor.shutdown(wait=False)


def _write_proposal(ctx: HealingRunContext, rel_path: str, old: str, new: str, evidence: str) -> str:
    """Write a unified diff (+ evidence) under proposals_dir; returns the diff path."""
    diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}"))
    safe = re.sub(r"[^\w.-]+", "_", rel_path)
    path = os.path.join(ctx.proposals_dir, safe + ".diff")
    os.makedirs(ctx.proposals_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# evidence: {evidence}\n{diff}")
    ctx.proposals.append({"target": rel_path, "diff": path})
    return path


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


def _passing_tests(report_json: str) -> set:
    """{(spec_key, title)} that passed in the run being healed — a blast-radius re-run must keep them passing."""
    if not report_json or not os.path.exists(report_json):
        return set()
    try:
        with open(report_json, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return set()
    out = set()
    for suite in _iter_suites(data.get("suites", [])):
        for spec in suite.get("specs", []):
            key = _spec_key_from_report_path(spec.get("file", ""))
            for test in spec.get("tests", []):
                if test.get("status") in ("passed", "expected"):
                    out.add((key, spec.get("title", "")))
    return out


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


# The renderer emits a traced test's details object on its test(...) header line (spec_renderer.render_test_details).
_DETAILS_RE = re.compile(r"\{\s*tag\s*:\s*\[[^\n]*?\]\s*,\s*annotation\s*:\s*\[[^\n]*?\]\s*\}")


def _header_details(block: str) -> Optional[str]:
    """The { tag, annotation } object on a test block's header line (whitespace-normalised), or None."""
    header = next((ln for ln in (block or "").splitlines() if re.search(r"test(?:\.skip|\.fixme)?\(", ln)), "")
    m = _DETAILS_RE.search(header)
    return re.sub(r"\s+", " ", m.group(0)) if m else None


# Phase 4.6 / 6.6: a timing fix may never add a fixed sleep (it hides races and slows every run).
_FIXED_SLEEP_RE = re.compile(r"\bwaitForTimeout\s*\(|\bsetTimeout\s*\(|\bsleep\s*\(")
_SLEEP_ALTERNATIVES = ("a web-first wait instead: await expect(locator).toBeVisible() / toHaveText(...), "
                       "action.waitForElement(\"<key>\"), page.waitForURL(...), page.waitForResponse(...), "
                       "expect.poll(...) or expect(...).toPass()")


def _fixed_sleeps(block: str) -> int:
    return len(_FIXED_SLEEP_RE.findall(block or ""))


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


def _build_python_locator(page, method: str, primary: str, role_name: Optional[str],
                           test_id_attribute: Optional[str] = None):
    if method == "getByPlaceholder":
        return page.get_by_placeholder(primary)
    if method == "getByRole":
        return page.get_by_role(primary, name=role_name) if role_name is not None else page.get_by_role(primary)
    if method == "getByText":
        return page.get_by_text(primary)
    if method == "getByLabel":
        return page.get_by_label(primary)
    if method == "getByTestId":
        from tools.test_creation.script_generator.locator_resolve import by_test_id
        return by_test_id(page, primary, test_id_attribute)
    if method == "locator":
        return page.locator(primary)
    return None


def _ctx_test_id_attribute(ctx) -> Optional[str]:
    """ctx.test_id_attribute(), tolerant of lightweight test doubles that lack it (-> Playwright default)."""
    fn = getattr(ctx, "test_id_attribute", None)
    try:
        return fn() if callable(fn) else None
    except Exception:
        return None


def _live_locator_resolves(ctx: "HealingRunContext", page, expr: str) -> bool:
    calls = _extract_locator_calls(expr)
    if not calls:
        return False
    method, primary, role_name = calls[0]

    def _check():
        locator = _build_python_locator(page, method, primary, role_name, _ctx_test_id_attribute(ctx))
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


def _get_validation_page(ctx: HealingRunContext, module_id: str = "", page_url: str = ""):
    """Lazily launch (and cache, per module + page) one headless page for live
    locator dry-run checks — reused across every tool call in this run that
    targets the same page. The module's setup steps (its login) run first, so
    a page behind a login is checked signed in. Returns (scanner, page), both
    None if a browser genuinely can't be launched — callers must treat that
    as 'can't verify', not a rejection."""
    cache_key = f"{module_id}|{page_url}" if page_url else module_id
    if cache_key in ctx.validation_pages:
        return ctx.validation_pages[cache_key]

    def _launch():
        from tools.playwright_scanner import PlaywrightScanner
        scanner = getattr(ctx, "_scanner", None)
        if scanner is None:
            scanner = PlaywrightScanner(headless=True)
            first_page = scanner.launch()
            ctx._scanner = scanner
            ctx._contexts[module_id] = scanner.context
            page, fresh = first_page, True
        elif module_id in ctx._contexts:
            page, fresh = ctx._contexts[module_id].new_page(), False      # same module: already signed in
        else:
            ctx._contexts[module_id] = scanner.browser.new_context()
            page, fresh = ctx._contexts[module_id].new_page(), True
        setup = ctx.module_setups.get(module_id)
        if setup and fresh:
            scanner._execute_setup_steps(page, setup)
        url = page_url or ctx.module_urls.get(module_id) or ctx.default_url
        if url:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
        return scanner, page

    try:
        ctx.validation_pages[cache_key] = ctx.pw_executor().submit(_launch).result()
    except Exception as exc:
        ctx.logger.warning(f"Locator dry-run page unavailable for module '{module_id}': {exc}")
        ctx.validation_pages[cache_key] = (None, None)
    return ctx.validation_pages[cache_key]


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
            if ctx.healable is not None and (spec_key, tn) not in ctx.healable:
                continue
            entry[tn] = _get_error_for_test(ctx.report_json, spec_key, tn)
        if entry:
            ctx.remaining[spec_key] = entry
    return {
        "failing_tests": [
            {"spec_file": sf, "test_name": tn, "error_message": err}
            for sf, tests in ctx.remaining.items()
            for tn, err in tests.items()
        ],
        "total_failing": ctx.remaining_total(),
    }


def _locator_entry_resolves(page, entry: dict, test_id_attribute: Optional[str] = None) -> bool:
    """Same {type, locator, name?, frame?, scope?} -> Locator resolution LocatorManager.ts
    performs at test-run time, done in Python for a live dry-run check. Shared with
    ScriptGenerationAgent through tools/ (Phase 2) instead of two private copies; the
    count()==1 rule and the fail-open on unknown types / errors are unchanged."""
    from tools.test_creation.script_generator.locator_resolve import entry_resolves
    return entry_resolves(page, entry, test_id_attribute)


_LOCATOR_FIELDS = ("type", "locator", "name", "scope", "frame")


def _dom_element_for(ctx: HealingRunContext, entry: dict) -> Optional[dict]:
    sid = entry.get("_source_locator_id")
    return next((el for el in ctx.dom_elements if sid and el.get("locator_id") == sid), None)


def _with_locator(entry: dict, new_locator: dict) -> dict:
    """The entry with only its locator fields replaced — description, module, page and the recorded
    `_fingerprint` (the identity of the ORIGINAL element) stay."""
    out = {k: v for k, v in entry.items() if k not in _LOCATOR_FIELDS}
    out.update({k: v for k, v in new_locator.items() if k in _LOCATOR_FIELDS})
    return out


def _find_same_element(ctx: HealingRunContext, page, key: str, entry: dict) -> dict:
    """Phase 6.3: a replacement locator for `key` that points at the SAME element (identity score >= threshold).
    Tries the DOM re-scan repair first, then a live identity search; never accepts a mere "something resolves"."""
    tid = _ctx_test_id_attribute(ctx)
    original, source = identity.original_fingerprint(entry, key, _dom_element_for(ctx, entry))
    best_seen = None
    # 1. DOM re-scan repair (repair_named_locator), on a scratch copy — then the identity check on the live page.
    if ctx.locator_map_path and os.path.exists(ctx.locator_map_path):
        scratch_dir = ctx.proposals_dir or ctx.reports_dir
        os.makedirs(scratch_dir, exist_ok=True)
        scratch = os.path.join(scratch_dir, f".heal_scratch_{key}.json")
        with open(ctx.locator_map_path, encoding="utf-8") as src, open(scratch, "w", encoding="utf-8") as dst:
            dst.write(src.read())
        try:
            if repair_named_locator(scratch, ctx.comprehension_dir, key):
                with open(scratch, encoding="utf-8") as f:
                    candidate = (json.load(f) or {}).get(key) or {}
                cand_loc = {k: candidate[k] for k in _LOCATOR_FIELDS if k in candidate}
                if cand_loc and cand_loc != {k: entry[k] for k in _LOCATOR_FIELDS if k in entry}:
                    fp = ctx.pw_executor().submit(identity.live_fingerprint, page, cand_loc, tid).result()
                    if fp:
                        sc = identity.identity_score(original, fp)
                        best_seen = sc["score"]
                        if sc["eligible"] and sc["score"] >= identity.THRESHOLD:
                            return {"accepted": True, "locator": cand_loc, "score": sc["score"], "parts": sc["parts"],
                                    "method": "dom_rescan", "fingerprint_source": source}
        finally:
            if os.path.exists(scratch):
                os.remove(scratch)
    # 2. Live identity search over the page's elements.
    res = ctx.pw_executor().submit(identity.heal_live, page, original, tid).result()
    best = res.get("best") or {}
    if res.get("accepted"):
        return {"accepted": True, "locator": res["entry"], "score": best.get("score"), "parts": best.get("parts"),
                "runner_up": res.get("runner_up_score"), "method": "live_identity", "fingerprint_source": source}
    return {"accepted": False, "reason": res.get("reason"), "score": best.get("score", best_seen),
            "runner_up": res.get("runner_up_score"), "fingerprint_source": source,
            "best_candidate": best.get("entry")}


def _refuse(ctx: HealingRunContext, spec_file: str, test_name: str, key: str, found: dict) -> dict:
    reason = (f"locator_key '{key}' is broken and no replacement passed the identity check "
              f"({found.get('reason')}; fingerprint from {found.get('fingerprint_source')}) — needs a human to update "
              "locator_map.json")
    audit.append(ctx.reports_dir, {"run_id": ctx.run_id, "mode": ctx.mode, "kind": "locator_map", "target": key,
                                   "test": f"{spec_file} :: {test_name}", "before": ctx.locator_map.get(key),
                                   "after": found.get("best_candidate"), "evidence": found.get("reason"),
                                   "confidence": found.get("score"), "outcome": "refused"})
    ctx.review.append({"key": key, "spec_file": spec_file, "test_name": test_name, "reason": found.get("reason"),
                       "score": found.get("score")})
    return {"resolved": False, "reason": reason, "identity_score": found.get("score")}


def _propose_locator_fix_action_library(ctx: HealingRunContext, spec_file: str, test_name: str) -> dict:
    """Locator diagnosis/repair for a plan-rendered (generation_mode ==
    "action_library") spec: extract the implicated locator_key(s) from
    `action.<verb>('key', ...)` calls, live-check each against locator_map.json, and
    repair a confirmed-broken key in the one shared locator_map.json entry — which fixes
    every spec that references the key, so every such spec is re-run (blast radius, 6.5).

    Phase 6.3: the replacement must be the SAME element — its fingerprint (role, accessible name, tag, label,
    container, position) has to match the original's above the identity threshold. Otherwise nothing is changed
    and the key goes to human review. Every decision is written to healing_audit.jsonl (6.9)."""
    block = _read_test_block(ctx, spec_file, test_name)
    if block is None:
        return {"resolved": False, "reason": f"test block '{test_name}' not found in {spec_file}"}

    keys = _ACTION_CALL_RE.findall(block)
    if not keys:
        return {"resolved": False, "reason": "no action.<verb>('locator_key', ...) call in the failing block"}

    module_id = _module_id_from_spec_file(spec_file)
    for key in dict.fromkeys(keys):
        entry = ctx.locator_map.get(key)
        if not entry or entry.get("_dynamic"):
            # a `_dynamic` element (a message, an error area) appears only after an action — absent on a fresh
            # page load is expected, so a load-time check can never call it broken (same rule as ScriptGeneration)
            continue
        _scanner, page = _get_validation_page(ctx, entry.get("_module_id") or module_id, entry.get("_page_url") or "")
        if page is None:
            return {"resolved": False, "reason": "headless validation page unavailable — cannot live-check locators"}
        try:
            resolves = ctx.pw_executor().submit(_locator_entry_resolves, page, entry,
                                               _ctx_test_id_attribute(ctx)).result()
        except Exception:
            resolves = True
        if resolves:
            continue  # this key is fine — the failure is something else

        found = _find_same_element(ctx, page, key, entry)
        if not found["accepted"]:
            return _refuse(ctx, spec_file, test_name, key, found)

        new_entry = _with_locator(entry, found["locator"])
        blast = specs_using_keys(ctx.scripts_dir, [key], ctx.flows_ts_path)
        row = {"run_id": ctx.run_id, "mode": ctx.mode, "kind": "locator_map", "target": key,
               "test": f"{spec_file} :: {test_name}", "before": entry, "after": new_entry,
               "evidence": f"locator_key '{key}' failed live resolution; replacement found by {found['method']} "
                           f"(identity parts {found.get('parts')}, fingerprint from {found['fingerprint_source']})",
               "confidence": found["score"], "blast_radius": blast}
        with open(ctx.locator_map_path, encoding="utf-8") as f:
            old_text = f.read()
        full = json.loads(old_text)
        full[key] = new_entry
        new_text = json.dumps(full, indent=2)
        if ctx.mode == "propose":
            _write_proposal(ctx, "locator_map.json", old_text, new_text,
                            f"locator_key '{key}' failed live resolution; identity score {found['score']}")
            audit.append(ctx.reports_dir, {**row, "outcome": "proposed"})
            for tn in list(ctx.remaining.get(spec_file, {})):
                _mark_not_healable(ctx, spec_file, tn, "patch proposed (healing.mode=propose), not applied")
            return {"resolved": True, "applied": False, "proposed": True, "repaired_key": key,
                    "identity_score": found["score"], "blast_radius": blast,
                    "note": "propose mode: locator_map.json diff written to healing_proposals; nothing applied"}
        with open(ctx.locator_map_path, "w", encoding="utf-8") as f:
            f.write(new_text)
        ctx.locator_map = full
        ctx.repaired[key] = {"before": entry, "after": new_entry, "spec_file": spec_file, "test_name": test_name,
                             "score": found["score"], "blast_radius": blast, "verified": False}
        audit.append(ctx.reports_dir, {**row, "outcome": "applied"})
        return {
            "resolved": True,
            "applied": True,
            "repaired_key": key,
            "identity_score": found["score"],
            "blast_radius": blast,
            "note": "locator_map.json entry repaired directly — no apply_patch needed for this fix. Call run_tests "
                    "next; it re-runs every spec in blast_radius automatically.",
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

    refused = None
    for method, primary, role_name in calls:
        original = _fingerprint_of_call(method, primary, role_name)
        candidates = _rank_candidate_elements(ctx.dom_elements, primary, role_name)
        for el in candidates:
            expr = get_playwright_expr(el)
            if not expr:
                continue
            # Phase 6.3: the replacement must be the same element, not just one that exists.
            sc = identity.identity_score(original, identity.fingerprint_from_dom_element(el))
            score = sc["score"]
            if not sc["eligible"] or score < identity.THRESHOLD:
                refused = refused or (expr, score)
                continue
            if _live_locator_resolves(ctx, page, expr):
                return {
                    "resolved": True,
                    "old_call": _format_call(method, primary, role_name),
                    "new_expr": expr,
                    "identity_score": score,
                }
    if refused:
        audit.append(ctx.reports_dir, {"run_id": ctx.run_id, "mode": ctx.mode, "kind": "spec_patch",
                                       "target": spec_file, "test": test_name, "after": refused[0],
                                       "evidence": "candidate failed the identity check", "confidence": refused[1],
                                       "outcome": "refused"})
        return {"resolved": False, "reason": f"the closest replacement ({refused[0]}) scored {refused[1]} on the "
                                             f"identity check (< {identity.THRESHOLD}) — not the same element; "
                                             "needs human review"}
    return {"resolved": False, "reason": "no DOM element resolved a working replacement locator"}


def _fingerprint_of_call(method: str, primary: str, role_name: Optional[str]) -> dict:
    """What a raw page.getBy*(...) call says about its element (the weakest fingerprint source)."""
    if method == "getByRole":
        return {"role": primary, "name": role_name or "", "position": None}
    if method in ("getByText", "getByPlaceholder"):
        return {"name": primary, "position": None}
    if method == "getByLabel":
        return {"name": primary, "label": primary, "position": None}
    return {"name": re.sub(r"[#.\[\]=\"'_-]+", " ", primary).strip(), "attrs": {"testid": primary, "id": primary.lstrip("#")},
            "position": None}


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
        locator = _build_python_locator(page, method, primary, role_name, _ctx_test_id_attribute(ctx))
        locator.wait_for(timeout=15000)

    try:
        ctx.pw_executor().submit(_wait).result()
        call = _format_call(method, primary, role_name)
        return {
            "is_timing_issue": True,
            "locator": call,
            "resolved_within_ms": 15000,
            # Phase 4.6: the fix is a web-first wait before the step that raced — never a fixed sleep.
            "suggested_fix": f"await expect({call}, 'element should be visible before it is used').toBeVisible();",
            "forbidden": "page.waitForTimeout / action.waitForTimeout / setTimeout — apply_patch rejects fixed sleeps",
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

    # Phase 4.6 guard: never introduce a fixed sleep (one the block already had may stay).
    if _fixed_sleeps(new_block) > _fixed_sleeps(old_block):
        return {
            "applied": False,
            "reason": "new_block adds a fixed sleep (waitForTimeout / setTimeout) — not allowed; use "
                      + _SLEEP_ALTERNATIVES,
        }

    # Phase 1 traceability guard: a test's { tag, annotation } details object links it to its acceptance
    # criteria and test-case id. A patch may change the body (or turn the test into test.skip), never that link.
    old_details = _header_details(old_block)
    if old_details is not None and _header_details(new_block) != old_details:
        return {
            "applied": False,
            "reason": "new_block must keep the test's { tag: [...], annotation: [...] } object unchanged, on the "
                      f"test(...) line — copy it exactly: {old_details}",
        }

    new_content = content.replace(old_block, new_block, 1)
    if new_content == content:
        return {"applied": False, "reason": "replacement produced no change to the file"}

    row = {"run_id": ctx.run_id, "mode": ctx.mode, "kind": "spec_patch", "target": spec_file, "test": test_name,
           "before": old_block, "after": new_block, "evidence": ctx.remaining.get(spec_file, {}).get(test_name, "")}
    if ctx.mode == "propose":
        path = _write_proposal(ctx, spec_file, content, new_content, f"test '{test_name}'")
        audit.append(ctx.reports_dir, {**row, "outcome": "proposed", "diff": path})
        _mark_not_healable(ctx, spec_file, test_name, "patch proposed (healing.mode=propose), not applied")
        return {"applied": False, "proposed": True, "diff": path, "spec_file": spec_file, "test_name": test_name}

    tmp_path = spec_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    os.replace(tmp_path, spec_path)
    audit.append(ctx.reports_dir, {**row, "outcome": "applied"})

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

    # Phase 6.5: a repaired locator_map key changes every spec that uses it — all of them run, not only these.
    pending = {k: r for k, r in ctx.repaired.items() if not r.get("verified")}
    blast = sorted({sf for r in pending.values() for sf in r.get("blast_radius") or []})
    spec_files = list(dict.fromkeys(list(spec_files) + blast))
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
            if title in ctx.remaining.get(spec_key, {}):
                ctx.fixed.add((spec_key, title))
            ctx.remaining.get(spec_key, {}).pop(title, None)
        elif r.get("status") == "flaky" and spec_key in ctx.remaining and title in ctx.remaining[spec_key]:
            # Phase 4.7: passing only on a retry is not a verified fix — keep it open, say why.
            ctx.remaining[spec_key][title] = ("flaky after the patch — passed only on a retry, not counted as healed: "
                                              + ("; ".join(r.get("errors", [])) or ""))
        elif spec_key in ctx.remaining and title in ctx.remaining[spec_key]:
            ctx.remaining[spec_key][title] = "; ".join(r.get("errors", [])) or r.get("comment", "")

    ctx.remaining = {sf: tests for sf, tests in ctx.remaining.items() if tests}
    regressions = _check_blast_radius(ctx, pending, result.get("results", []))
    ctx.rounds.append({
        "round": len(ctx.rounds) + 1,
        "spec_files": list(spec_files),
        "ran": True,
        "passed": result.get("passed", 0),
        "failed": result.get("failed", 0),
        "remaining_after": ctx.remaining_total(),
        "blast_radius": blast,
        "reverted": [r["key"] for r in regressions],
    })
    return {
        "ran": True,
        "blast_radius": blast,
        "reverted_keys": regressions,
        "passed": result.get("passed", 0),
        "failed": result.get("failed", 0),
        "still_failing": _remaining_summary(ctx),
        "all_resolved": not ctx.remaining,
    }


def _check_blast_radius(ctx: HealingRunContext, pending: Dict[str, Dict[str, Any]], results: List[dict]) -> List[dict]:
    """A test that passed before the heal and fails now, in a spec using a repaired key, means the fix broke it:
    the key is reverted (the original entry restored) and audited. Returns [{key, broke: [...]}]."""
    if not pending:
        return []
    now_failing = set()
    for r in results:
        if r.get("status") not in ("success", "flaky"):
            now_failing.add((_spec_key_from_report_path(r.get("spec_file", "")), r.get("test_title", "")))
    out = []
    for key, rep_ in pending.items():
        specs = set(rep_.get("blast_radius") or [])
        broke = sorted(f"{sf} :: {t}" for sf, t in now_failing & ctx.passing_before if sf in specs)
        if not broke:
            rep_["verified"] = True
            continue
        full = dict(ctx.locator_map)
        full[key] = rep_["before"]
        with open(ctx.locator_map_path, "w", encoding="utf-8") as f:
            json.dump(full, f, indent=2)
        ctx.locator_map = full
        del ctx.repaired[key]
        ctx.reverted.append({"key": key, "broke": broke})
        audit.append(ctx.reports_dir, {"run_id": ctx.run_id, "mode": ctx.mode, "kind": "locator_map", "target": key,
                                       "before": rep_["after"], "after": rep_["before"], "outcome": "reverted",
                                       "evidence": f"the fix broke previously passing test(s): {broke[:5]}"})
        tests = ctx.remaining.setdefault(rep_["spec_file"], {})
        tests.pop(rep_["test_name"], None)
        _mark_not_healable(ctx, rep_["spec_file"], rep_["test_name"],
                           f"locator fix for '{key}' was reverted: it broke {len(broke)} passing test(s)")
        out.append({"key": key, "broke": broke})
    return out


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
