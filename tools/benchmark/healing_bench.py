"""
healing_bench.py — Phase 6 acceptance benchmark on buggy_shop (real Chromium, real Playwright, no LLM).

(a) Locator changes — LOC_01..LOC_10 (benchmarks/apps/buggy_shop/locator_changes.py) each break one locator_map key
    while the element is still there; LOC_11/LOC_12 are controls where the element is gone and a DIFFERENT element
    takes its slot. Per change: run the specs -> triage -> the healing tools HealingAgent's LLM loop calls
    (read_failure_report, propose_locator_fix, run_tests — deterministic, so no model is needed) -> ground truth:
    the healed locator must resolve to the element carrying the original `data-bench-id`.
    Targets: heal success >= 80% of LOC_01..10, 0 wrong-element heals (controls must be refused).
(b) Product bugs — 10 seeded bugs, one strong-oracle spec each. Per bug: the spec passes on the clean app, fails with
    the bug, and triage calls every failure product_defect, so healing gets nothing (0 healed).

    python -m tools.benchmark.healing_bench [--only LOC_01,BUG_18] [--skip-locators] [--skip-bugs] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import socket
import time
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from tools.constants import PROJECTS_BASE

PROJECT = "bench_p6_heal"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STAMP = str(int(time.time()))[-6:]

# ── locator map (as script generation would leave it: test ids, module, page) ──

def _entry(testid: str, module: str, page: str, desc: str, dynamic: bool = False) -> dict:
    e = {"type": "testid", "locator": testid, "description": desc, "_module_id": module, "_page_url": page}
    if dynamic:
        e["_dynamic"] = True
    return e


def locator_map(base: str) -> Dict[str, dict]:
    L, P = "L", "P"
    return {
        "login_button": _entry("login-button", L, f"{base}/login", "Log in button (login form on /login)"),
        "username": _entry("username", L, f"{base}/login", "Username (login form on /login)"),
        "password": _entry("password", L, f"{base}/login", "Password (login form on /login)"),
        "login_error": _entry("login-error", L, f"{base}/login", "Login error message", True),
        "current_user": _entry("current-user", L, f"{base}/products", "Signed-in user name (after login)", True),
        "save_product": _entry("save-product", P, f"{base}/products/new", "Save product button (product form)"),
        "product_name": _entry("name", P, f"{base}/products/new", "Name (product form)"),
        "price": _entry("price", P, f"{base}/products/new", "Price (product form)"),
        "category": _entry("category", P, f"{base}/products/new", "Category (product form)"),
        "description": _entry("description", P, f"{base}/products/new", "Description (product form)"),
        "form_errors": _entry("form-errors", P, f"{base}/products/new", "Product form errors", True),
        "flash": _entry("flash", P, f"{base}/products", "Flash message", True),
        "product_heading": _entry("product-name", P, f"{base}/products/1", "Product name heading (product detail)", True),
        "cart_line": _entry("cart-line-name", P, f"{base}/cart", "Cart line product name", True),
        "search": _entry("search", P, f"{base}/products", "Search (search form on /products)"),
        "search_button": _entry("search-button", P, f"{base}/products", "Search button"),
        "product_list": _entry("product-list", P, f"{base}/products", "Product list"),
        "add_to_cart": _entry("add-to-cart", P, f"{base}/products/1", "Add to cart button (product detail)"),
        "quantity": _entry("quantity", P, f"{base}/products/1", "Quantity (product detail)"),
        "cart_error": _entry("cart-error", P, f"{base}/cart", "Cart error", True),
        "help_link": _entry("footer-help-link", P, f"{base}/products", "Help link (footer)"),
        "help_title": _entry("help-title", P, f"{base}/help", "Help page title", True),
        "error_message": _entry("error-message", P, f"{base}/admin", "Error message", True),
        "file": _entry("file", P, f"{base}/upload", "File (upload form)"),
        "upload_button": _entry("upload-button", P, f"{base}/upload", "Upload button"),
        "upload_error": _entry("upload-error", P, f"{base}/upload", "Upload error", True),
    }


# ── specs (rendered from plans by the real renderer) ──

def _step(action, key=None, value=None, **kw):
    s = {"action": action}
    if key:
        s["locator_key"] = key
    if value is not None:
        s["value"] = value
    s.update(kw)
    return s


NAME50 = ("Heal" + STAMP + "x" * 50)[:50]
EXE = os.path.join(PROJECTS_BASE, PROJECT, "fixtures", "tool.exe")

# spec id -> (module, role, title, [tests]) ; tests: (name, type, steps)
SPECS: Dict[str, Tuple[str, str, str, List[tuple]]] = {
    "L_BS_001": ("L", "guest", "Login", [
        ("log in as alice", "positive", [
            _step("navigate", value="/login"), _step("enterText", "username", "alice"),
            _step("enterText", "password", "alice-pass-1"), _step("click", "login_button"),
            _step("verifyUrlContains", value="/products"), _step("verifyContainsText", "current_user", "alice")]),
    ]),
    "P_BS_002": ("P", "user", "Product form", [
        ("create a product", "positive", [
            _step("navigate", value="/products/new"), _step("enterText", "product_name", f"Heal item {STAMP}"),
            _step("enterText", "price", "5.00"), _step("selectDropdownByText", "category", "Books"),
            _step("click", "save_product"), _step("verifyContainsText", "product_heading", f"Heal item {STAMP}")]),
    ]),
    "P_BS_003": ("P", "user", "Search", [
        ("search finds a product", "positive", [
            _step("navigate", value="/products"), _step("enterText", "search", "Atlas"),
            _step("click", "search_button"), _step("verifyContainsText", "product_list", "Atlas of Maps")]),
    ]),
    "P_BS_004": ("P", "user", "Cart", [
        ("add a product to the cart", "positive", [
            _step("navigate", value="/products/1"), _step("click", "add_to_cart"),
            _step("verifyUrlContains", value="/cart"), _step("verifyContainsText", "cart_line", "The Pragmatic Coder")]),
    ]),
    "P_BS_005": ("P", "user", "Help", [
        ("help link opens the help page", "positive", [
            _step("navigate", value="/products"), _step("click", "help_link"),
            _step("verifyContainsText", "help_title", "Help")]),
    ]),
}

# seeded bug -> (module, role, test, steps): passes on the correct app, fails with the bug
BUG_SPECS: Dict[str, Tuple[str, str, str, List[dict]]] = {
    "BUG_01": ("P", "user", "a 50-character name is accepted", [
        _step("navigate", value="/products/new"), _step("enterText", "product_name", NAME50),
        _step("enterText", "price", "5.00"), _step("selectDropdownByText", "category", "Books"),
        _step("click", "save_product"), _step("verifyContainsText", "product_heading", NAME50)]),
    "BUG_05": ("P", "user", "a description is shown as text, never run", [
        _step("navigate", value="/products/new"), _step("enterText", "product_name", f"Xss {STAMP}"),
        _step("enterText", "price", "5.00"), _step("selectDropdownByText", "category", "Books"),
        _step("enterText", "description", "<img src=x onerror=alert(1)>"), _step("click", "save_product"),
        _step("verifyContainsText", "product_heading", f"Xss {STAMP}"), _step("verifyNoDialog"),
        _step("verifyNotInjected", payloadMarker="onerror=alert(1)")]),
    "BUG_06": ("P", "user", "the footer help link opens help", [
        _step("navigate", value="/products"), _step("click", "help_link"),
        _step("verifyContainsText", "help_title", "Help")]),
    "BUG_07": ("P", "user", "searching for 50% works", [
        _step("navigate", value="/products"), _step("enterText", "search", "50%"), _step("click", "search_button"),
        _step("verifyRequest", method="GET", urlPattern="/products?q=", status=200)]),
    "BUG_13": ("L", "guest", "a wrong password shows the generic message", [
        _step("navigate", value="/login"), _step("enterText", "username", "alice"),
        _step("enterText", "password", "wrong-pass-9"), _step("click", "login_button"),
        _step("verifyContainsText", "login_error", "Invalid username or password")]),
    "BUG_16": ("P", "user", "a regular user cannot open admin", [
        _step("navigate", value="/admin"), _step("verifyContainsText", "error_message", "Access denied")]),
    "BUG_17": ("P", "user", "an .exe upload is refused", [
        _step("navigate", value="/upload"), _step("uploadFile", "file", EXE), _step("click", "upload_button"),
        _step("verifyContainsText", "upload_error", "Only CSV or PNG files are allowed")]),
    "BUG_18": ("P", "user", "an empty name is refused", [
        _step("navigate", value="/products/new"), _step("enterText", "price", "9.99"),
        _step("selectDropdownByText", "category", "Books"), _step("click", "save_product"),
        _step("verifyContainsText", "form_errors", "Name is required"),
        _step("verifyNoRequest", method="POST", urlPattern="/products"),
        _step("verifyFieldInvalid", "product_name")]),
    "BUG_19": ("P", "user", "search ignores case", [
        _step("navigate", value="/products"), _step("enterText", "search", "atlas"), _step("click", "search_button"),
        _step("verifyContainsText", "product_list", "Atlas of Maps")]),
    "BUG_21": ("P", "user", "quantity 0 is refused", [
        _step("navigate", value="/products/1"), _step("clearAndEnterText", "quantity", "0"),
        _step("click", "add_to_cart"), _step("verifyContainsText", "cart_error", "Quantity must be between 1 and 99")]),
}

# locator change -> (spec it breaks, key it breaks, control?)
LOC_TARGETS = {
    "LOC_01": ("L_BS_001", "login_button", False), "LOC_02": ("L_BS_001", "username", False),
    "LOC_03": ("L_BS_001", "password", False), "LOC_04": ("P_BS_002", "save_product", False),
    "LOC_05": ("P_BS_002", "product_name", False), "LOC_06": ("P_BS_002", "price", False),
    "LOC_07": ("P_BS_002", "category", False), "LOC_08": ("P_BS_003", "search", False),
    "LOC_09": ("P_BS_004", "add_to_cart", False), "LOC_10": ("P_BS_005", "help_link", False),
    "LOC_11": ("P_BS_002", "save_product", True), "LOC_12": ("P_BS_002", "product_name", True),
}


# ── project setup ──

def _login_steps(base: str) -> List[dict]:
    # name / form selectors: the LOC_xx changes rename ids and test ids, never these
    return [{"goto": f"{base}/login"}, {"fill": {"selector": "input[name=username]", "value": "alice"}},
            {"fill": {"selector": "input[name=password]", "value": "alice-pass-1"}},
            {"click": "#login-form button[type=submit]"}, {"wait": 300}]


def _yaml(base: str) -> str:
    import yaml
    return yaml.safe_dump({
        "project": {"name": PROJECT, "url": base}, "environment": "local",
        "safety": {"allowed_hosts": ["127.0.0.1"], "allow_destructive": True},
        "auth": {"enabled": False, "roles": {"user": {"strategy": "setup", "steps": _login_steps(base)},
                                               "guest": {"anonymous": True}}},
        "modules": [{"id": "L", "name": "Login", "url": f"{base}/login"},
                    {"id": "P", "name": "Shop", "url": f"{base}/products", "setup": _login_steps(base)}],
        "oracles": {"enabled": True},
        "healing": {"triage": True, "mode": "auto", "flaky_rerun": False, "triage_llm": False},
        "execution": {"role_auth": True, "role_auth_max_age_minutes": 0, "console_guard": "warn",
                      "network": "on-failure", "test_steps": True},
    }, sort_keys=False)


def _write(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data if isinstance(data, str) else json.dumps(data, indent=2))


def build_project(base: str, specs: Dict[str, Tuple[str, str, str, List[tuple]]]) -> str:
    """Write the bench project (project.yaml, locator_map.json, pages.ts, specs, test_suite.json)."""
    from tools.test_creation.script_generator.build_dom_locator_map import write_pages_module
    from tools.test_creation.script_generator.compose import inject_role
    from tools.test_creation.script_generator.spec_renderer import render_spec_from_plan

    pdir = os.path.join(PROJECTS_BASE, PROJECT)
    shutil.rmtree(pdir, ignore_errors=True)
    tc = os.path.join(pdir, "test_creation")
    _write(os.path.join(pdir, "project.yaml"), _yaml(base))
    lm = locator_map(base)
    _write(os.path.join(tc, "locator_map.json"), lm)
    write_pages_module(lm, os.path.join(tc, "pages.ts"), module_names={"L": "Login", "P": "Shop"})
    _write(EXE, "MZ fake executable")
    suite = []
    for sid, (module, role, title, tests) in specs.items():
        rel = f"{module}/test_{sid}_{title.lower().replace(' ', '_')}.spec.ts"
        spec_rel = f"projects/{PROJECT}/test_creation/test_scripts/{rel}"
        plan = {"tests": [{"name": n, "type": t, "steps": st} for n, t, st in tests]}
        ts = render_spec_from_plan(plan, {"scenario_id": sid, "title": title}, base, spec_rel, project=PROJECT,
                                   test_steps=True, oracles=True)
        _write(os.path.join(ROOT, "application_assets", spec_rel), inject_role(ts, role))
        suite.append({"spec_id": sid, "file": rel, "module_id": module, "status": "new",
                      "generation_mode": "action_library", "last_result": None})
    _write(os.path.join(tc, "test_suite.json"), {"schema_version": 2, "artifact": "test_suite", "project": PROJECT,
                                                "specs": suite})
    return pdir


def capture(base: str, pdir: str) -> int:
    """Record `_fingerprint` for every static key on the clean app (what script generation's live validation does)."""
    from playwright.sync_api import sync_playwright
    from tools.healing.identity import capture_fingerprints

    path = os.path.join(pdir, "test_creation", "locator_map.json")
    with open(path, encoding="utf-8") as fh:
        lm = json.load(fh)
    by_page: Dict[Tuple[str, str], List[str]] = {}
    for k, e in lm.items():
        if not e.get("_dynamic"):
            by_page.setdefault((e["_module_id"], e["_page_url"]), []).append(k)
    done = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for (module, url), keys in by_page.items():
            page = browser.new_page()
            if module == "P":
                page.goto(f"{base}/login")
                page.fill("input[name=username]", "alice")
                page.fill("input[name=password]", "alice-pass-1")
                page.click("#login-form button[type=submit]")
                page.wait_for_load_state()
            page.goto(url)
            done += len(capture_fingerprints(page, lm, keys))
            page.close()
        browser.close()
    _write(path, lm)
    return done


# ── running ──

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _App:
    def __init__(self, flags: List[str]):
        from tools.benchmark.app_server import AppServer
        from tools.benchmark.apps import APPS
        self.server = AppServer(APPS["buggy_shop"], port=_free_port(), bugs=flags)

    def __enter__(self):
        return self.server.start()

    def __exit__(self, *exc):
        self.server.stop()


def _retarget(pdir: str, base: str) -> None:
    """A new app instance listens on a new port: point the project, specs and locator map at it."""
    old = None
    with open(os.path.join(pdir, "project.yaml"), encoding="utf-8") as fh:
        import yaml
        old = (yaml.safe_load(fh) or {})["project"]["url"]
    if old == base:
        return
    for root, _d, files in os.walk(pdir):
        for f in files:
            if f.endswith((".yaml", ".json", ".ts")):
                p = os.path.join(root, f)
                with open(p, encoding="utf-8") as fh:
                    text = fh.read()
                if old in text:
                    with open(p, "w", encoding="utf-8") as fh:
                        fh.write(text.replace(old, base))


def _run(spec_files: Optional[List[str]] = None) -> dict:
    from agents.test_execution.ui_execution.agent import UIExecutionAgent
    req = {"project_name": PROJECT, "headless": True}
    if spec_files:
        req["spec_files"] = spec_files
    return UIExecutionAgent().execute(req, {})


def _truth(base: str, entry: dict, module: str) -> Optional[str]:
    """data-bench-id of the one element `entry` resolves to on its page (None: 0 or 2+ matches)."""
    from playwright.sync_api import sync_playwright
    from tools.test_creation.script_generator.locator_resolve import resolve_entry
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        if module == "P":
            page.goto(f"{base}/login")
            page.fill("input[name=username]", "alice")
            page.fill("input[name=password]", "alice-pass-1")
            page.click("#login-form button[type=submit]")
            page.wait_for_load_state()
        page.goto(entry["_page_url"])
        loc = resolve_entry(page, entry, "data-testid")
        out = loc.get_attribute("data-bench-id") if loc.count() == 1 else None
        browser.close()
    return out


def heal_locator_change(flag: str, base: str, pdir: str, clean_map: dict) -> Dict[str, Any]:
    from agents.test_execution.healing.agent import _load_module_setups, _load_project_urls
    from agents.test_execution.healing.tools import (HealingRunContext, _mark_not_healable, _propose_locator_fix,
                                                     _read_failure_report, _run_tests)
    from agents.test_execution.triage.agent import run_triage
    from tools.triage.triage import DATA, LOCATOR

    spec_id, key, control = LOC_TARGETS[flag]
    lm_path = os.path.join(pdir, "test_creation", "locator_map.json")
    _write(lm_path, clean_map)
    out = _run()
    triage = run_triage(PROJECT, out["report_json"], reruns=False)
    verdicts = {f"{t['spec_file']} :: {t['test_name']}": t["verdict"] for t in triage["tests"]}
    healable = {(t["spec_file"], t["test_name"]) for t in triage["tests"] if t["verdict"] in (LOCATOR, DATA)}
    module_urls, default_url = _load_project_urls(PROJECT)
    ctx = HealingRunContext(
        project_name=PROJECT, scripts_dir=os.path.join(pdir, "test_creation", "test_scripts"),
        reports_dir=os.path.join(pdir, "test_execution", "reports"), report_json=out["report_json"],
        dom_elements=[], module_urls=module_urls, default_url=default_url, test_data_map={}, settings={},
        logger=logging.getLogger("healing_bench"),
        generation_modes={s["file"]: "action_library" for s in json.load(open(
            os.path.join(pdir, "test_creation", "test_suite.json"), encoding="utf-8"))["specs"]},
        locator_map=dict(clean_map), locator_map_path=lm_path, comprehension_dir=os.path.join(pdir, "x"),
        mode="auto", healable=healable, run_id=f"bench-{flag}", module_setups=_load_module_setups(PROJECT),
        flows_ts_path="")
    proposals, verify = [], None
    try:
        # the loop the LLM drives: one failing test -> propose_locator_fix -> run_tests (blast radius included)
        # -> what is still failing; a test with no fix is marked not healable
        _read_failure_report(ctx)
        for _ in range(10):
            if not ctx.remaining:
                break
            spec, tests = next(iter(ctx.remaining.items()))
            test = next(iter(tests))
            prop = _propose_locator_fix(ctx, spec, test)
            proposals.append({"test": f"{spec} :: {test}", **prop})
            if prop.get("applied"):
                verify = _run_tests(ctx, [spec])
            else:
                _mark_not_healable(ctx, spec, test, prop.get("reason", "no fix"))
    finally:
        ctx.close()
    with open(lm_path, encoding="utf-8") as fh:
        healed_map = json.load(fh)
    changed = {k for k in healed_map if healed_map[k] != clean_map.get(k)}
    truth = {k: _truth(base, healed_map[k], healed_map[k]["_module_id"]) for k in changed}
    wrong = sorted(k for k, t in truth.items() if t != k or control)
    still = {f"{sf} :: {t}" for sf, ts in ctx.remaining.items() for t in ts}
    target_fixed = not any(spec_id in s for s in still) and not any(
        spec_id in n["spec_file"] for n in ctx.not_healable)
    healed_ok = (not control and key in changed and truth.get(key) == key and bool(verify and verify.get("ran"))
                 and target_fixed)
    return {"flag": flag, "control": control, "broken_key": key, "spec": spec_id,
            "failed_tests": len(triage["tests"]), "triage": verdicts, "proposals": proposals,
            "changed_keys": sorted(changed), "truth": truth, "wrong_element": wrong,
            "verified_after_heal": bool(verify and verify.get("ran")) and target_fixed,
            "not_healable": ctx.not_healable,
            "outcome": ("refused" if control and not changed else "WRONG HEAL" if wrong
                        else "healed" if healed_ok else "not healed")}


def bug_case(bug: str, base: str) -> Dict[str, Any]:
    from agents.test_execution.triage.agent import run_triage
    from tools.triage.triage import DATA, LOCATOR
    out = _run([s for s in _bug_spec_files() if f"_{bug}_" in s])
    triage = run_triage(PROJECT, out["report_json"], reruns=False)
    verdicts = [t["verdict"] for t in triage["tests"]]
    return {"bug": bug, "failed": len(triage["tests"]), "verdicts": verdicts,
            "evidence": [t["evidence"] for t in triage["tests"]],
            "healable": sum(1 for v in verdicts if v in (LOCATOR, DATA))}


def _bug_spec_files() -> List[str]:
    return [f"{m}/test_{b}_{b.lower()}.spec.ts" for b, (m, *_r) in BUG_SPECS.items()]


def _bug_specs_as_specs() -> Dict[str, Tuple[str, str, str, List[tuple]]]:
    return {b: (m, role, b.lower(), [(name, "positive", steps)]) for b, (m, role, name, steps) in BUG_SPECS.items()}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", default="")
    ap.add_argument("--skip-locators", action="store_true")
    ap.add_argument("--skip-bugs", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "benchmarks", "results",
                                                  f"{date.today().isoformat()}_buggy_shop_phase6_healing"))
    args = ap.parse_args(argv)
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    os.chdir(ROOT)
    result: Dict[str, Any] = {"date": date.today().isoformat(), "locators": [], "bugs": [], "clean": {}}

    specs = {**SPECS, **_bug_specs_as_specs()}
    with _App([]) as app:
        pdir = build_project(app.base_url, specs)
        result["fingerprints_recorded"] = capture(app.base_url, pdir)
        clean = _run()
        result["clean"] = {"passed": clean.get("passed"), "failed": clean.get("failed"),
                           "failing": [f"{r['test_title']}: {'; '.join(r.get('errors') or [])[:300]}"
                                       for r in clean.get("results", []) if r.get("status") != "success"]}
        with open(os.path.join(pdir, "test_creation", "locator_map.json"), encoding="utf-8") as fh:
            clean_map = json.load(fh)
        base0 = app.base_url

    if not args.skip_locators:
        for flag in LOC_TARGETS:
            if only and flag not in only:
                continue
            with _App([flag]) as app:
                _retarget(pdir, app.base_url)
                clean_map = json.loads(json.dumps(clean_map).replace(base0, app.base_url))
                base0 = app.base_url
                row = heal_locator_change(flag, app.base_url, pdir, clean_map)
            print(f"{flag}: {row['outcome']} (changed {row['changed_keys']}, truth {row['truth']})")
            result["locators"].append(row)
    if not args.skip_bugs:
        for bug in BUG_SPECS:
            if only and bug not in only:
                continue
            with _App([bug]) as app:
                _retarget(pdir, app.base_url)
                clean_map = json.loads(json.dumps(clean_map).replace(base0, app.base_url))
                base0 = app.base_url
                _write(os.path.join(pdir, "test_creation", "locator_map.json"), clean_map)
                row = bug_case(bug, app.base_url)
            print(f"{bug}: failed={row['failed']} verdicts={row['verdicts']} healable={row['healable']}")
            result["bugs"].append(row)

    result["summary"] = summarize(result)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    _write(args.out + ".json", result)
    _write(args.out + ".md", to_markdown(result))
    print(json.dumps(result["summary"], indent=2))
    if not os.environ.get("MTA_KEEP_E2E"):
        shutil.rmtree(pdir, ignore_errors=True)
    return 0


def summarize(r: Dict[str, Any]) -> Dict[str, Any]:
    locs = [x for x in r["locators"] if not x["control"]]
    ctrl = [x for x in r["locators"] if x["control"]]
    healed = sum(1 for x in locs if x["outcome"] == "healed")
    wrong = sum(len(x["wrong_element"]) for x in r["locators"])
    bugs = r["bugs"]
    return {
        "locator_changes": len(locs), "healed": healed,
        "heal_success_pct": round(100.0 * healed / len(locs), 1) if locs else None,
        "wrong_element_heals": wrong, "controls_refused": sum(1 for x in ctrl if x["outcome"] == "refused"),
        "controls": len(ctrl),
        "bugs": len(bugs), "bugs_detected": sum(1 for b in bugs if b["failed"]),
        "bugs_all_product_defect": sum(1 for b in bugs if b["failed"] and all(v == "product_defect" for v in b["verdicts"])),
        "bug_failures_healable": sum(b["healable"] for b in bugs),
        "pass": (bool(locs) and healed / len(locs) >= 0.8 and wrong == 0
                 and all(b["failed"] and b["healable"] == 0 and all(v == "product_defect" for v in b["verdicts"])
                         for b in bugs)),
    }


def to_markdown(r: Dict[str, Any]) -> str:
    s = r["summary"]
    lines = [f"# Phase 6 healing benchmark — buggy_shop ({r['date']})", "",
             "Real Chromium + Playwright through UIExecutionAgent; triage + the healing tools the LLM loop calls "
             "(deterministic, no model). Ground truth: `data-bench-id` (never read by the fingerprint).", "",
             f"Clean build: {r['clean'].get('passed')} passed, {r['clean'].get('failed')} failed "
             f"{r['clean'].get('failing') or ''}; fingerprints recorded: {r.get('fingerprints_recorded')}.", "",
             "| KPI | Result | Target |", "|---|---|---|",
             f"| Heal success (LOC_01–10) | **{s['healed']}/{s['locator_changes']} ({s['heal_success_pct']}%)** | ≥ 80% |",
             f"| Wrong-element heals | **{s['wrong_element_heals']}** | 0 |",
             f"| Controls refused (element replaced) | {s['controls_refused']}/{s['controls']} | all |",
             f"| Seeded bugs detected | {s['bugs_detected']}/{s['bugs']} | all |",
             f"| … classified product_defect | {s['bugs_all_product_defect']}/{s['bugs']} | all |",
             f"| … failures sent to healing | **{s['bug_failures_healable']}** | 0 |", "",
             "## Locator changes", "", "| Change | Broken key | Triage | Outcome | Healed to (truth) |", "|---|---|---|---|---|"]
    for x in r["locators"]:
        tri = ", ".join(sorted(set(x["triage"].values()))) or "—"
        lines.append(f"| {x['flag']}{' (control)' if x['control'] else ''} | {x['broken_key']} | {tri} | "
                     f"{x['outcome']} | {x['truth'] or '—'} |")
    lines += ["", "## Seeded product bugs", "", "| Bug | Failed tests | Verdicts | Healable |", "|---|---|---|---|"]
    for b in r["bugs"]:
        lines.append(f"| {b['bug']} | {b['failed']} | {', '.join(b['verdicts']) or '—'} | {b['healable']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
