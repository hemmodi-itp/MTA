"""
api_tests.py — Phase 8.1: deterministic API test generation (no LLM), run by the same Playwright runner with the
`api` request fixture.

Endpoints = code routes (code_rules.json) ∪ api_inventory.json. Per endpoint, what the inputs support:
  auth        signed out -> 401 (an API route) or a redirect to the login page (a page)        [code: auth style]
  role        a role the code does not allow -> 403                                            [code: role checks]
  ownership   another user's resource -> 403/404           [project.yaml api_tests.ownership: {path, owner, other}]
  method      a method the path does not define -> 405
  valid       a valid request -> its success status; JSON response keys checked                 [code: response keys]
  rules       one case per code rule, sent straight to the server (what the UI would block): missing / too long /
              below the minimum / not an option / bad format -> rejected (4xx); and at the boundary -> accepted
  pagination  page=1 / beyond the last / 0 / not a number -> never a 5xx
  query       unusual values in every other query parameter (%, quotes, 300 chars, ...) -> never a 5xx
  idempotent  PUT / DELETE twice -> the second answer is the same status or 404
  errors      the JSON error bodies of several endpoints share one shape (a warning when they do not)
Requests that change data (valid creates, accepted boundaries) are generated only when the project allows
destructive actions (safety.allow_destructive + a non-prod environment); otherwise they are test.skip with the reason.

Output: test_creation/test_scripts/api/api_<group>.spec.ts, registered like the NFR specs (generation_mode "api").
project.yaml: test_types: {api: true}; api_tests: {ownership: [...], roles: {default: user}}.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from tools.whitebox.python_rules import template_path

FIXTURE_IMPORT = "../../../../../_shared/runtime/fixtures/testFixture"
CHECKS_IMPORT = "../../../../../_shared/runtime/fixtures/apiChecks"
MUTATING = ("POST", "PUT", "PATCH", "DELETE")
ANON = "{ storageState: { cookies: [], origins: [] } }"


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def endpoints(code: Optional[dict], inventory: Optional[dict]) -> List[Dict[str, Any]]:
    """Code routes first (they carry rules / auth / statuses), then inventory endpoints the code does not define."""
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in (code or {}).get("routes") or []:
        out.setdefault((r["method"], r["path_template"]), {**r, "origin": "code"})
    for e in (inventory or {}).get("endpoints") or []:
        key = (str(e.get("method", "GET")).upper(), template_path(e.get("path_template") or ""))
        if key not in out:
            req = e.get("request") or {}
            out[key] = {"method": key[0], "path": e.get("path_template"), "path_template": key[1], "handler": None,
                        "citation": None, "origin": "inventory", "auth": None, "roles": [], "access_checks": [],
                        "validators": [], "statuses": sorted(int(s) for s in (e.get("statuses") or {}) if str(s).isdigit()),
                        "error_status": None, "response_keys": [],
                        "params": {"path": [], "query": list(req.get("query_params") or []),
                                   "form": list(req.get("fields") or []) if e.get("kind") == "form_submit" else [],
                                   "file": [], "json_body": "json" in str(req.get("content_type") or "")}}
    return sorted(out.values(), key=lambda r: (r["path_template"], r["method"]))


def concrete_template(path: str) -> str:
    """/api/orders/1 -> /api/orders/{id} (a concrete URL from config or a crawl, matched to a route template)."""
    return template_path(re.sub(r"/\d+(?=/|$)", "/{id}", path or ""))


def sample_path(template: str, app_map: Optional[dict]) -> str:
    """A concrete URL path for a template: the crawl's sample (/products/7) or 1 for each placeholder."""
    for s in (app_map or {}).get("states") or []:
        if template_path(s.get("url_template") or "") == template and s.get("url"):
            from urllib.parse import urlsplit
            return urlsplit(s["url"]).path
    return re.sub(r"\{[^}]+\}", "1", template)


def _rules_for(route: dict, rules: List[dict]) -> List[dict]:
    key = f"{route['method']} {route['path_template']}"
    return [r for r in rules if key in (r.get("routes") or [])]


def _fields(route: dict, rules: List[dict]) -> List[str]:
    p = route.get("params") or {}
    names = list(p.get("form") or [])
    for r in rules:
        if r["field"] not in names:
            names.append(r["field"])
    return names


def _valid_value(field: str, rules: List[dict]) -> Tuple[Optional[str], bool]:
    """(TS expression of a valid value, known) — known=False when no rule says what is valid."""
    mine: Dict[str, Dict[str, Any]] = {}
    for r in rules:                                   # every rule of the field, merged (min from one, max from another)
        if r["field"] == field:
            mine.setdefault(r["kind"], {}).update(r["value"])
    if not mine and re.search(r"(^|_)id$", field):
        return json.dumps("1"), True              # a reference to an existing record (the seed's first one)
    if "options" in mine and mine["options"].get("values"):
        return json.dumps(str(mine["options"]["values"][0])), True
    if "range" in mine:
        rng = mine["range"]
        lo = rng.get("min", 1)
        v = lo if rng.get("integer") else max(lo, 0) + 9.99 if "max" not in rng else lo
        return json.dumps(str(int(v)) if rng.get("integer") else f"{float(v):.2f}"), True
    if "pattern" in mine:
        return None, False
    if "length" in mine or "required" in mine:
        mx = (mine.get("length") or {}).get("max", 40)
        mn = (mine.get("length") or {}).get("min", 1)
        return f"nfrUniq({json.dumps(field[:3])}, {int(max(mn, min(mx, 24)))})", True
    return None, False


def _bad_cases(rule: dict, error: str) -> List[Tuple[str, str, str]]:
    """[(label, TS value expression or None-for-missing, expected)] — rejected inputs, and accepted boundaries."""
    k, v, f = rule["kind"], rule["value"], rule["field"]
    out: List[Tuple[str, str, str]] = []
    if k == "required":
        out.append((f"{f} missing", "MISSING", error))
        out.append((f"{f} empty", '""', error))
    elif k == "length":
        if "max" in v:
            out.append((f"{f} at max length {v['max']}", f"sized({int(v['max'])})", "ACCEPT"))
            out.append((f"{f} over max length {v['max'] + 1}", f"sized({int(v['max']) + 1})", error))
        if v.get("min", 0) > 0:
            out.append((f"{f} under min length {v['min'] - 1}", f"sized({int(v['min']) - 1})", error))
    elif k == "range":
        integer = v.get("integer")
        step = 1 if integer else 0.01
        fmt = (lambda x: json.dumps(str(int(x)))) if integer else (lambda x: json.dumps(f"{x:.2f}"))
        if "min" in v:
            out.append((f"{f} at min {v['min']}", fmt(v["min"]), "ACCEPT"))
            out.append((f"{f} below min ({v['min'] - step:g})", fmt(v["min"] - step), error))
        if "max" in v:
            out.append((f"{f} at max {v['max']}", fmt(v["max"]), "ACCEPT"))
            out.append((f"{f} above max ({v['max'] + step:g})", fmt(v["max"] + step), error))
    elif k == "options":
        out.append((f"{f} not one of the options", json.dumps("Zz-not-an-option"), error))
    elif k == "pattern":
        out.append((f"{f} in the wrong format", json.dumps("not-valid-%"), error))
    return out


def _ac_links(requirements, route: dict, kind: str) -> List[str]:
    """API acceptance criteria: one naming this path, or the "all API endpoints need a session" kind of rule."""
    reqs = requirements.get("requirements", []) if isinstance(requirements, dict) else requirements or []
    out = []
    for r in reqs:
        for ac in r.get("acceptance_criteria", []):
            text = ac.get("statement", "")
            if ac.get("testability") not in (None, "api") and "/api" not in text:
                continue
            paths = {template_path(p) for p in re.findall(r"(/[\w/{}.-]+)", text)}
            if route["path_template"] in paths and (kind != "auth" or "401" in text or "sign" in text):
                out.append(ac["id"])
            elif kind == "auth" and route.get("auth") == "api_401" and re.search(r"all api endpoints", text, re.I):
                out.append(ac["id"])
    return out


def _tags(kind: str, acs: List[str]) -> str:
    return " ".join(["@api", f"@api-{kind}"] + ([f"@{a}" for a in acs] if acs else []))


class _Spec:
    def __init__(self):
        self.blocks: Dict[str, List[str]] = {}     # use-key -> test lines

    def add(self, use: str, lines: List[str]):
        self.blocks.setdefault(use, []).extend(lines)


def _req(method: str, path: str, route: dict, body_ts: Optional[str] = None, redirects0: bool = True) -> str:
    opts = []
    if body_ts is not None:
        opts.append(("data: " if (route.get("params") or {}).get("json_body") else "form: ") + body_ts)
    if redirects0:
        opts.append("maxRedirects: 0")
    return f"await api.fetch({json.dumps(path)}, {{ method: {json.dumps(method)}{(', ' + ', '.join(opts)) if opts else ''} }})"


def generate(project_dir: Path, out_dir: Optional[Path] = None, only_routes: Optional[set] = None,
             prefix: str = "api", force: bool = False) -> Tuple[List[Path], Dict[str, Any]]:
    """only_routes: {"POST /x/{id}", ...} — just these endpoints (the coverage gap round writes them as prefix "gap").
    force: generate even when test_types.api is off (the gap round)."""
    project_dir = Path(project_dir)
    raw = yaml.safe_load((project_dir / "project.yaml").read_text(encoding="utf-8")) or {}
    if not force and not ((raw.get("test_types") or {}).get("api")):
        return [], {}
    from tools.safety.policy import SafetyPolicy
    policy = SafetyPolicy.from_project_config(raw)
    comp = project_dir / "test_comprehension"
    code = _load(comp / "code_rules.json", {})
    inv = _load(comp / "api_inventory.json", {})
    app_map = _load(comp / "app_map.json", {})
    reqs = _load(comp / "requirements.json", [])
    cfg = raw.get("api_tests") if isinstance(raw.get("api_tests"), dict) else {}
    roles = list(((raw.get("auth") or {}).get("roles") or {}).keys())
    signed = [r for r in roles if not (((raw.get("auth") or {}).get("roles") or {}).get(r) or {}).get("anonymous")]
    default_role = (cfg.get("roles") or {}).get("default") or ("user" if "user" in signed else (signed[0] if signed else None))
    eps = endpoints(code, inv)
    if only_routes is not None:
        eps = [e for e in eps if f"{e['method']} {e['path_template']}" in only_routes]
    rules = code.get("rules") or []
    out_dir = out_dir or project_dir / "test_creation" / "test_scripts" / "api"
    out_dir.mkdir(parents=True, exist_ok=True)
    groups: Dict[str, _Spec] = {}
    covered = set()

    def spec_for(route) -> _Spec:
        seg = (route["path_template"].strip("/").split("/") or [""])[0] or "root"
        if seg == "api":
            parts = route["path_template"].strip("/").split("/")
            seg = "api_" + (parts[1] if len(parts) > 1 else "root")
        return groups.setdefault(re.sub(r"\W+", "_", seg), _Spec())

    def use_role(role: Optional[str]) -> str:
        return ANON if role is None else f"{{ role: {json.dumps(role)} }}"

    for ep in eps:
        m, tmpl = ep["method"], ep["path_template"]
        path = sample_path(tmpl, app_map)
        name = f"{m} {tmpl}"
        spec = spec_for(ep)
        cite = f" ({ep['citation']})" if ep.get("citation") else ""
        mine = _rules_for(ep, rules)
        error = str(ep["error_status"]) if ep.get("error_status") else "4xx"

        def test(title, kind, body, role, acs=(), skip=None):
            t = f"{name} — {title} {_tags(kind, list(acs))}"
            head = f"  test{'.skip' if skip else ''}({json.dumps(t, ensure_ascii=False)}, async ({{ api }}, testInfo) => {{"
            lines = [head] + ([f"    // skipped: {skip}"] if skip else []) + [f"    {b}" for b in body] + ["  });"]
            spec.add(use_role(role), lines)
            covered.add(name)

        # auth
        if ep.get("auth") == "api_401":
            test("signed out -> 401", "auth", [f"const res = {_req(m, path, ep)};",
                                               f"await expectStatus(res, 401, {json.dumps(name + ' signed out' + cite)});"],
                 None, _ac_links(reqs, ep, "auth"))
        elif ep.get("auth") == "session_redirect":
            # with a valid body when one is known — a framework may reject a bodiless POST before the session check
            fields_ = _fields(ep, mine) if m in MUTATING else []
            vals_ = {f: _valid_value(f, mine) for f in fields_}
            body_ = ("{ " + ", ".join(f"{json.dumps(f)}: {v}" for f, (v, _) in vals_.items()) + " }"
                     if fields_ and all(k for _, k in vals_.values()) else None)
            test("signed out -> not allowed", "auth", [f"const res = {_req(m, path, ep, body_)};",
                                                       f"expectNotAllowed(res, {json.dumps(name + ' signed out' + cite)});"],
                 None, _ac_links(reqs, ep, "auth"))
        # roles
        for allowed in ep.get("roles") or []:
            for other in [r for r in signed if r != allowed]:
                test(f"as {other} (needs {allowed}) -> 403", "role",
                     [f"const res = {_req(m, path, ep)};",
                      f"await expectStatus(res, [403, 404], {json.dumps(name + ' as ' + other + cite)});"], other)
        # ownership (config)
        for own in cfg.get("ownership") or []:
            if concrete_template(own.get("path", "")) == tmpl and m == "GET":
                test(f"{own['path']} as {own.get('other')} (owned by {own.get('owner')}) -> denied", "ownership",
                     [f"const res = {_req('GET', own['path'], ep)};",
                      f"await expectStatus(res, [403, 404], {json.dumps(own['path'] + ' as ' + str(own.get('other')))});"],
                     own.get("other"))
        # wrong method
        if ep.get("origin") == "code":
            defined = {e["method"] for e in eps if e["path_template"] == tmpl}
            wrong = next(x for x in ("PUT", "PATCH", "DELETE", "POST") if x not in defined)
            if ep is next(e for e in eps if e["path_template"] == tmpl):
                test(f"{wrong} is not allowed -> 405", "method",
                     [f"const res = await api.fetch({json.dumps(path)}, {{ method: {json.dumps(wrong)}, maxRedirects: 0 }});",
                      f"await expectStatus(res, 405, {json.dumps(wrong + ' ' + tmpl)});"], default_role)
        role = (ep.get("roles") or [default_role])[0] if ep.get("auth") or ep.get("roles") else default_role
        owned = next((o for o in cfg.get("ownership") or [] if concrete_template(o.get("path", "")) == tmpl), None)
        if owned:                                   # a resource that belongs to someone: ask for it as its owner
            path, role = owned["path"], owned.get("owner") or role
        # valid request
        if m == "GET":
            succ = [s for s in ep.get("statuses") or [] if s < 400]
            expect = "'success'" if not succ or 200 in succ or not ep.get("statuses") else str(succ[0])
            body = [f"const res = {_req('GET', path, ep)};", f"await expectStatus(res, {expect}, {json.dumps(name)});"]
            if ep.get("response_keys"):
                body.append(f"await expectJsonKeys(res, {json.dumps(ep['response_keys'])}, {json.dumps(name)});")
            test("valid request", "valid", body, role)
        if m in MUTATING and mine:
            fields = _fields(ep, mine)
            values = {f: _valid_value(f, mine) for f in fields}
            if all(known for _, known in values.values()):
                base = "{ " + ", ".join(f"{json.dumps(f)}: {v}" for f, (v, _) in values.items()) + " }"
                skip = None if policy.destructive_allowed else "changes data — set safety.allow_destructive in a non-prod environment"
                if ep.get("preconditions"):
                    skip = "needs stored state first: " + "; ".join(ep["preconditions"])
                test("valid request is accepted", "valid",
                     [f"const res = {_req(m, path, ep, base)};", f"await expectStatus(res, 'success', {json.dumps(name)});"],
                     role, skip=skip)
                for rule in mine:
                    for label, val, exp in _bad_cases(rule, error):
                        body_ts = ("(() => { const b: Record<string, string> = " + base + "; delete b["
                                   + json.dumps(rule["field"]) + "]; return b; })()") if val == "MISSING" else \
                            "{ ...(" + base + "), " + json.dumps(rule["field"]) + ": " + val + " }"
                        exp_ts = "'success'" if exp == "ACCEPT" else (exp if exp.isdigit() else "'4xx'")
                        stateful = exp == "ACCEPT" and rule["field"] in (ep.get("stateful_fields") or [])
                        case_skip = ("the accepted limit depends on stored state (the handler adds what is already "
                                     "stored) — the rejection side is tested") if stateful else (
                            skip if exp == "ACCEPT" else None)
                        if ep.get("preconditions"):      # a rejection would come from the missing state, not the rule
                            case_skip = "needs stored state first: " + "; ".join(ep["preconditions"])
                        guard = f" — {'; '.join(rule['guards'])}" if rule.get("guards") else ""
                        test(f"{label} -> {'accepted' if exp == 'ACCEPT' else 'rejected'} [{rule['citation']}]",
                             "rule", [f"// rule {rule['kind']} {json.dumps(rule['value'])} at {rule['citation']}{guard}",
                                      f"const res = {_req(m, path, ep, body_ts)};",
                                      f"await expectStatus(res, {exp_ts}, {json.dumps(name + ': ' + label)});"],
                             role, skip=case_skip)
        # pagination
        if "page" in ((ep.get("params") or {}).get("query") or []) and m == "GET":
            body = ["for (const page of ['1', '999999', '0', '-1', 'abc']) {",
                    f"  const res = await api.fetch({json.dumps(path)} + '?page=' + page, {{ method: 'GET', maxRedirects: 0 }});",
                    f"  await expectStatus(res, '<500', {json.dumps(name)} + ' page=' + page);", "}"]
            test("pagination edges never 5xx", "pagination", body, role)
        # query parameters (EP: unusual values) — the server answers, never with a 5xx
        qparams = [q for q in ((ep.get("params") or {}).get("query") or []) if q != "page"]
        if m == "GET" and qparams:
            body = [f"for (const name of {json.dumps(qparams)}) {{",
                    "  for (const value of ['%', '100%', \"'\", '<>', 'x'.repeat(300), '-1']) {",
                    f"    const res = await api.fetch({json.dumps(path)} + '?' + name + '=' + encodeURIComponent(value), "
                    "{ method: 'GET', maxRedirects: 0 });",
                    f"    await expectStatus(res, '<500', {json.dumps(name)} + ' ' + name + '=' + value.slice(0, 12));",
                    "  }", "}"]
            test("unusual query values never 5xx", "query", body, role)
        # idempotency
        if m in ("PUT", "DELETE"):
            skip = None if policy.destructive_allowed else "changes data — set safety.allow_destructive in a non-prod environment"
            body = [f"const a = {_req(m, path, ep)};", f"const b = {_req(m, path, ep)};",
                    "expect([a.status(), 404, 410]).toContain(b.status());"]
            test("idempotent: twice -> same result", "idempotent", body, role, skip=skip)

    # consistent error format across JSON API endpoints (warning, not failure)
    api_eps = [e for e in eps if e.get("auth") == "api_401"]
    if len(api_eps) >= 2 and only_routes is None:
        calls = [f"shapes.push(`{e['method']} {e['path_template']}: ` + await errorShape({_req(e['method'], sample_path(e['path_template'], app_map), e)}));"
                 for e in api_eps]
        spec = groups.setdefault("api_errors", _Spec())
        spec.add(ANON, ["  test(\"API error bodies share one format @api @api-errors\", async ({ api }, testInfo) => {",
                        "    const shapes: string[] = [];"] + [f"    {c}" for c in calls] + [
                        "    const kinds = new Set(shapes.map((s) => s.split(': ')[1]));",
                        "    if (kinds.size > 1) testInfo.annotations.push({ type: 'api-warning', description: `error bodies differ: ${shapes.join(' | ')}` });",
                        "    expect(shapes.length).toBeGreaterThan(0);", "  });"])

    written = []
    for group, spec in sorted(groups.items()):
        lines = [f"import {{ test, expect }} from '{FIXTURE_IMPORT}';",
                 f"import {{ errorShape, expectJsonKeys, expectLoginRedirect, expectNotAllowed, expectStatus, sized, uniq as nfrUniq }} from '{CHECKS_IMPORT}';",
                 "", "// Generated by tools/whitebox/api_tests.py (Phase 8.1) — do not edit; regenerate instead.",
                 "// Requests go straight to the server, past any browser-side validation.", ""]
        for use, tests in spec.blocks.items():
            lines += [f"test.describe({json.dumps('api ' + group + ' ' + use)}, () => {{", f"  test.use({use});"] + tests + ["});", ""]
        p = out_dir / f"{prefix}_{group}.spec.ts"
        p.write_text("\n".join(lines), encoding="utf-8")
        written.append(p)
    keep = {p.name for p in written}
    for old in out_dir.glob(f"{prefix}_*.spec.ts"):
        if old.name not in keep:
            old.unlink()
    total = {f"{e['method']} {e['path_template']}" for e in eps}
    stats = {"endpoints": len(total), "covered": len(covered & total),
             "endpoint_coverage_pct": round(100.0 * len(covered & total) / len(total), 1) if total else None,
             "uncovered": sorted(total - covered)}
    return written, stats


def register(project_dir: Path, written: List[Path]) -> Dict[str, int]:
    """test_suite.json (generation_mode "api") + test_plans.json (a tc_id per test) — same as the NFR specs."""
    from contracts.artifacts import load_payload, save_artifact
    tc = Path(project_dir) / "test_creation"
    counts: Dict[str, int] = {}
    suite = load_payload("test_suite", str(tc / "test_suite.json"), {}) or {}
    plans = load_payload("test_plans", str(tc / "test_plans.json"), {}) or {}
    from tools.nonfunctional.generate import spec_tests
    specs = [s for s in suite.get("specs") or [] if s.get("generation_mode") != "api"]
    plans = {k: v for k, v in plans.items() if not str(k).startswith("API_")}
    for p in written:
        sid = "API_" + p.name.replace(".spec.ts", "").replace("api_", "", 1).upper()
        tests = spec_tests(p.read_text(encoding="utf-8"))
        specs.append({"spec_id": sid, "file": f"api/{p.name}", "module_id": "api", "status": "new",
                      "generation_mode": "api", "last_result": None})
        plans[sid] = {"generation_mode": "api", "tests": [
            {"name": t["title"], "title": t["title"], "type": "api", "tc_id": f"{sid.replace('_', '-')}-{i:03d}",
             "ac_ids": t["ac_ids"], "ac_link": "direct" if t["ac_ids"] else None} for i, t in enumerate(tests, start=1)]}
        counts[sid] = len(tests)
    suite["specs"] = specs
    suite.setdefault("project", Path(project_dir).name)
    save_artifact("test_suite", str(tc / "test_suite.json"), suite)
    save_artifact("test_plans", str(tc / "test_plans.json"), plans)
    return counts


if __name__ == "__main__":
    files, stats = generate(Path(sys.argv[1]))
    for f in files:
        print(f)
    print(json.dumps(stats, indent=2))
