"""Phase 7: deterministic non-functional Playwright spec generator (no LLM).

Input:  test_comprehension/app_map.json (+ form_model.json, baseline.json, requirements.json) and project.yaml.
Output: test_creation/test_scripts/nfr/nfr_<type>.spec.ts, one file per enabled type:

    test_types:            # each one on its own; absent = off
      accessibility        axe (WCAG 2.0/2.1/2.2 A+AA), accepted-issues baseline, keyboard walk, form-error announcement
      visual               full-page screenshot per state x viewport; the first run writes the baseline, never fails
      performance          TTFB / FCP / LCP / load / bytes / requests vs budgets and the Phase 2 baseline timings
      security_passive     headers, cookie flags, tokens/PII in URL or storage, stack-trace leaks, mixed content,
                           target=_blank without noopener — reads responses only, never sends an attack payload
      compatibility        viewports (320..1440): no horizontal overflow; touch targets and clipped text warn
      resilience           offline, slow network, unusual characters in GET (search) forms: no 5xx, no blank page,
                           no stack trace, no uncaught page error
      i18n                 locale x timezone matrix, RTL, +40% text expansion: no overflow; clipping warns

    nfr:                   # optional tuning per type
      accessibility: {accepted: [{rule, url_template?, reason}], keyboard: true, form_errors: true}
      visual:        {viewports: [1280], mask: ["[data-dynamic]"], max_diff_pixel_ratio: 0.01}
      performance:   {budget: {ttfb_ms: 1500, lcp_ms: 2500, load_ms: 3000}, regression_pct: 50, regression: warn}
      compatibility: {viewports: [320, 375, 768, 1024, 1440]}
      i18n:          {locales: [en-US, de-DE, ar-EG], timezones: [UTC, Asia/Kolkata]}

A state that needs a role starts with `test.use({ role })` when execution.role_auth is on (Phase 4 storage state),
else with the role's login steps. CLI: python -m tools.nonfunctional.generate <project_dir>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List
from urllib.parse import urlsplit

import yaml

from tools.requirements.classify import heuristic_testability

FIXTURE_IMPORT = "../../../../../_shared/runtime/fixtures/testFixture"
RULES_IMPORT = "../../../../../_shared/runtime/fixtures/securityRules"
NFR_IMPORT = "../../../../../_shared/runtime/fixtures/nfr"
ROLE_PREF = ("guest", "user")
TYPES = ("accessibility", "visual", "performance", "security_passive", "compatibility", "resilience", "i18n")
TAG = {"accessibility": "a11y", "visual": "visual", "performance": "perf", "security_passive": "security",
       "compatibility": "responsive", "resilience": "resilience", "i18n": "i18n"}
DEFAULTS = {
    "accessibility": {"accepted": [], "keyboard": True, "form_errors": True},
    "visual": {"viewports": [1280], "mask": ["[data-dynamic]", "time"], "max_diff_pixel_ratio": 0.01},
    "performance": {"budget": {"ttfb_ms": 1500, "lcp_ms": 2500, "load_ms": 3000}, "regression_pct": 50,
                    "regression": "warn"},
    "compatibility": {"viewports": [320, 375, 768, 1024, 1440]},
    "i18n": {"locales": ["en-US", "de-DE", "ar-EG"], "timezones": ["UTC", "Asia/Kolkata"]},
}
# unusual but legitimate input for search fields: the app must answer with a page, not an error
UNUSUAL_INPUT = ["100%", "a&b", "x" * 300, "naïve café", "🙂"]


def flags(project: dict) -> Dict[str, bool]:
    tt = project.get("test_types") or {}
    return {t: bool(tt.get(t)) for t in TYPES}


def options(project: dict, kind: str) -> dict:
    return {**DEFAULTS.get(kind, {}), **(((project.get("nfr") or {}).get(kind)) or {})}


def pick_states(app_map: dict) -> list[dict]:
    """One reachable state per url_template, preferring the least-privileged role."""
    best: dict[str, tuple[int, dict]] = {}
    for s in app_map.get("states", []):
        if s.get("access") == "blocked" or int(s.get("status") or 200) >= 400:
            continue
        roles = s.get("roles") or []
        rank = min((ROLE_PREF.index(r) for r in roles if r in ROLE_PREF), default=len(ROLE_PREF))
        key = s.get("url_template") or s["url"]
        if key not in best or rank < best[key][0]:
            best[key] = (rank, s)
    return [v[1] for v in best.values()]


def role_of(state: dict) -> str:
    roles = state.get("roles") or []
    for r in ROLE_PREF:
        if r in roles:
            return r
    return roles[0] if roles else "guest"


def nfr_ac_ids(requirements: dict | list, kind: str) -> list[str]:
    """AC ids whose text is non-functional and matches `kind`."""
    pats = {
        "accessibility": r"accessib|WCAG|screen reader|contrast|keyboard",
        "security_passive": r"\bHSTS\b|\bCSP\b|\bcookie|\bHTTPS\b|security header|\btoken",
        "performance": r"\bload(s|ed)? (with)?in\b|\bseconds?\b.*\b(load|respond)|response time|performance",
        "compatibility": r"mobile|responsive|viewport|tablet|browser",
        "visual": r"\blayout\b|visual|look and feel",
        "resilience": r"offline|network (error|failure)|unavailable|retry|error message",
        "i18n": r"locale|language|translat|currency|time ?zone|right-to-left|\bRTL\b",
    }
    pat = re.compile(pats.get(kind, r"$^"), re.I)
    reqs = requirements.get("requirements", []) if isinstance(requirements, dict) else requirements
    ids = []
    for r in reqs:
        for ac in r.get("acceptance_criteria", []):
            text = ac.get("statement", "")
            if pat.search(text) and (kind in ("security_passive",) or heuristic_testability(text)[0] == "non_functional"):
                ids.append(ac["id"])
    return ids


def _tags(kind: str, ac_ids: list[str]) -> str:
    return " ".join([f"@{TAG[kind]}"] + ([f"@{a}" for a in ac_ids] if ac_ids else ["@nfr"]))


def _login(project: dict, role: str) -> str:
    """The role's login steps inline (when execution.role_auth is off). Waits are load-state waits, not sleeps."""
    steps = (((project.get("auth") or {}).get("roles") or {}).get(role) or {}).get("steps") or []
    lines = []
    for st in steps:
        if "goto" in st:
            lines.append(f"    await page.goto({json.dumps(st['goto'])});")
        elif "fill" in st:
            lines.append(f"    await page.locator({json.dumps(st['fill']['selector'])}).fill({json.dumps(st['fill']['value'])});")
        elif "click" in st:
            lines.append(f"    await page.locator({json.dumps(st['click'])}).click();")
        elif "wait" in st:
            lines.append("    await page.waitForLoadState('load');")
    return "\n".join(lines)


def _role_auth(project: dict) -> bool:
    return bool((project.get("execution") or {}).get("role_auth"))


def _groups(states: list[dict]) -> Dict[str, list[dict]]:
    out: Dict[str, list[dict]] = {}
    for s in states:
        out.setdefault(role_of(s), []).append(s)
    return out


def _header(extra_imports: str = "") -> List[str]:
    return [f"import {{ test, expect }} from '{FIXTURE_IMPORT}';",
            f"import * as nfr from '{NFR_IMPORT}';"] + ([extra_imports] if extra_imports else []) + [
            "", "// Generated by tools/nonfunctional/generate.py (Phase 7) — do not edit; regenerate instead.", ""]


def _file(kind: str, states: list[dict], project: dict, ac_ids: list[str], body: Callable[[dict, str], List[str]],
          extra_imports: str = "", preamble: List[str] = ()) -> str:
    """One describe block per role; `body(state, title_prefix)` returns the test(s) for a state (indented 2)."""
    out = _header(extra_imports) + list(preamble)
    roles = (project.get("auth") or {}).get("roles") or {}
    for role, sts in _groups(states).items():
        out.append(f"test.describe({json.dumps(f'{kind} ({role})')}, () => {{")
        use_role = _role_auth(project) and role in roles
        if use_role:
            out.append(f"  test.use({{ role: {json.dumps(role)} }});")
        for s in sts:
            login = "" if use_role or role == "guest" else _login(project, role)
            out += [line.replace("__LOGIN__", login) for line in body(s, f"{TAG[kind]}: {s['url_template']} ({role})")]
        out += ["});", ""]
    return "\n".join(line for line in out if line != "    " and line is not None)


# ── per-type bodies ──────────────────────────────────────────────────────────

_TEXTLIKE = {"text", "email", "password", "number", "tel", "url", "search", "textarea", None}


def _error_checkable(form: dict) -> bool:
    """An empty submit must produce an error only when the form has a required text-like field; never submit a
    destructive form (delete, pay, ...)."""
    if (form.get("method") or "").lower() != "post" or not form.get("submit") or (form.get("submit") or {}).get("destructive"):
        return False
    return any((f.get("type") in _TEXTLIKE) and ((f.get("constraints") or {}).get("effective_required")
                                                  or (f.get("constraints") or {}).get("required") or f.get("required"))
               for f in form.get("fields") or [])


def gen_a11y_spec(states: list[dict], project: dict, ac_ids: list[str], forms: list[dict] = ()) -> str:
    opt = options(project, "accessibility")
    tags = _tags("accessibility", ac_ids)
    forms_by_url = {}
    for fm in forms or []:
        if _error_checkable(fm):
            forms_by_url.setdefault(fm.get("url_template"), []).append(fm)

    def body(s, title):
        out = [f"  test({json.dumps(f'{title} {tags}')}, async ({{ page, a11y }}, testInfo) => {{", "__LOGIN__",
               f"    await page.goto({json.dumps(s['url'])});",
               "    const results = await a11y.scan({ tags: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] });",
               f"    const findings = nfr.a11yFindings(results.violations ?? [], {json.dumps(s['url_template'])}, ACCEPTED);"]
        if opt.get("keyboard", True):
            out.append("    findings.push(...nfr.keyboardFindings(await nfr.keyboardWalk(page)));")
        out += ["    await nfr.attachFindings(testInfo, 'a11y-findings.json', findings);",
                "    expect(nfr.split(findings, testInfo.annotations, 'a11y'), 'accessibility findings').toEqual([]);",
                "  });"]
        if opt.get("form_errors", True):
            for fm in forms_by_url.get(s["url_template"], []):
                sel = f"#{fm['dom_id']}" if fm.get("dom_id") else f"form[action=\"{fm.get('action', '')}\"]"
                ftitle = f"{title} form {fm.get('dom_id') or fm.get('action')} announces errors {tags}"
                out += [f"  test({json.dumps(ftitle)}, async ({{ page }}, testInfo) => {{", "__LOGIN__",
                        f"    await page.goto({json.dumps(s['url'])});",
                        f"    const form = page.locator({json.dumps(sel)});",
                        "    await form.locator('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]), textarea').evaluateAll((els) => els.forEach((e) => { (e as HTMLInputElement).value = ''; }));",
                        "    await form.locator('[type=submit]').first().click();",
                        "    await page.waitForLoadState('load');",
                        f"    const findings = nfr.formErrorFindings(await nfr.formErrorState(page), {json.dumps(sel)});",
                        "    expect(nfr.split(findings, testInfo.annotations, 'a11y'), 'form error findings').toEqual([]);",
                        "  });"]
        return out
    return _file("accessibility", states, project, ac_ids, body,
                 preamble=[f"const ACCEPTED: nfr.AcceptedIssue[] = {json.dumps(opt.get('accepted') or [])};", ""])


def gen_visual_spec(states: list[dict], project: dict, ac_ids: list[str]) -> str:
    opt = options(project, "visual")
    tags = _tags("visual", ac_ids)

    def body(s, title):
        out = []
        for vw in opt["viewports"]:
            slug = re.sub(r"[^\w]+", "_", s["url_template"]).strip("_") or "root"
            name = f"{slug}-{vw}.png"
            out += [f"  test({json.dumps(f'{title} @{vw}px {tags}')}, async ({{ page }}, testInfo) => {{", "__LOGIN__",
                    f"    await page.setViewportSize({{ width: {int(vw)}, height: 900 }});",
                    f"    await page.goto({json.dumps(s['url'])});",
                    "    await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {});",
                    "    const mask = MASK.map((m) => page.locator(m));",
                    f"    const snap = testInfo.snapshotPath({json.dumps(name)}, {{ kind: 'screenshot' }});",
                    "    if (!fs.existsSync(snap)) {",
                    "      // first run: record the baseline and say so — a visual test never fails without one",
                    "      fs.mkdirSync(path.dirname(snap), { recursive: true });",
                    "      await page.screenshot({ path: snap, fullPage: true, mask, animations: 'disabled' });",
                    f"      testInfo.annotations.push({{ type: 'visual-baseline', description: `created {name} — review it; "
                    "approve later changes with python -m tools.nonfunctional.visual approve` });",
                    "      return;",
                    "    }",
                    f"    await expect(page).toHaveScreenshot({json.dumps(name)}, {{ fullPage: true, mask, animations: 'disabled', "
                    f"maxDiffPixelRatio: {float(opt['max_diff_pixel_ratio'])} }});",
                    "  });"]
        return out
    return _file("visual", states, project, ac_ids, body, extra_imports="import fs from 'fs';\nimport path from 'path';",
                 preamble=[f"const MASK: string[] = {json.dumps(opt['mask'])};", ""])


def gen_perf_spec(states: list[dict], project: dict, ac_ids: list[str], baseline: dict) -> str:
    opt = options(project, "performance")
    tags = _tags("performance", ac_ids)
    timing = {}
    for st in (baseline.get("states") or {}).values():
        if isinstance(st, dict) and st.get("timing") and st.get("url"):
            timing[urlsplit(st["url"]).path] = {k: v for k, v in st["timing"].items() if isinstance(v, (int, float))}

    def body(s, title):
        base = timing.get(urlsplit(s["url"]).path)
        return [f"  test({json.dumps(f'{title} {tags}')}, async ({{ page, perf, network }}, testInfo) => {{", "__LOGIN__",
                f"    await page.goto({json.dumps(s['url'])});",
                "    await page.waitForLoadState('load');",
                "    const metrics = await perf.attach();",
                "    const slowest = network.entries().filter((e) => e.duration_ms !== null)",
                "      .sort((a, b) => (b.duration_ms ?? 0) - (a.duration_ms ?? 0)).slice(0, 5)",
                "      .map((e) => `${e.method} ${e.url} ${e.duration_ms}ms`);",
                "    testInfo.annotations.push({ type: 'perf-slowest', description: slowest.join(' | ') });",
                f"    const findings = nfr.perfFindings(metrics as any, BUDGET, {json.dumps(base)}, {int(opt['regression_pct'])}, "
                f"{json.dumps('fail' if opt.get('regression') == 'fail' else 'warn')});",
                "    expect(nfr.split(findings, testInfo.annotations, 'perf'), 'performance findings').toEqual([]);",
                "  });"]
    return _file("performance", states, project, ac_ids, body,
                 preamble=[f"const BUDGET: nfr.PerfBudget = {json.dumps(opt['budget'])};", ""])


def origin_of(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def gen_security_spec(origin: str, states: list[dict], project: dict, ac_ids: list[str]) -> str:
    tags = _tags("security_passive", ac_ids)
    https = str(origin.startswith("https")).lower()

    def body(s, title):
        return [f"  test({json.dumps(f'{title} {tags}')}, async ({{ page, network }}, testInfo) => {{", "__LOGIN__",
                f"    const resp = await page.goto({json.dumps(s['url'])});",
                "    await page.waitForLoadState('load');",
                "    const findings = [",
                f"      ...checkHeaders(resp ? await resp.allHeaders() : {{}}, {{ https: {https} }}),",
                f"      ...checkCookies(await page.context().cookies(), {{ https: {https} }}),",
                "      ...checkUrl(page.url()),",
                "      ...checkStorage(await page.evaluate(() => ({ ...localStorage })), 'localStorage'),",
                "    ].map((x) => ({ ...x, level: 'fail' as const }));",
                "    findings.push(...nfr.checkStackTrace(resp ? await resp.text() : '', 'page'));",
                "    findings.push(...nfr.checkMixedContent(page.url(), network.entries().map((e) => e.url)));",
                "    findings.push(...nfr.checkBlankTargets(await nfr.collectLinks(page)));",
                "    await nfr.attachFindings(testInfo, 'security-findings.json', findings);",
                "    expect(nfr.split(findings, testInfo.annotations, 'security'), 'passive security findings').toEqual([]);",
                "  });"]
    return _file("security_passive", states, project, ac_ids, body,
                 extra_imports=f"import {{ checkHeaders, checkCookies, checkUrl, checkStorage }} from '{RULES_IMPORT}';")


def gen_responsive_spec(states: list[dict], project: dict, ac_ids: list[str]) -> str:
    opt = options(project, "compatibility")
    tags = _tags("compatibility", ac_ids)

    def body(s, title):
        out = []
        for vw in opt["viewports"]:
            h = 812 if vw < 768 else 1024 if vw < 1280 else 900
            out += [f"  test({json.dumps(f'{title} @{vw}px {tags}')}, async ({{ page }}, testInfo) => {{", "__LOGIN__",
                    f"    await page.setViewportSize({{ width: {int(vw)}, height: {h} }});",
                    f"    await page.goto({json.dumps(s['url'])});",
                    "    await page.waitForLoadState('load');",
                    f"    const findings = nfr.layoutFindings(await nfr.layoutProbe(page), {json.dumps(f'{s['url_template']} @{vw}px')});"]
            if vw < 768:     # orientation change on phones
                out += [f"    await page.setViewportSize({{ width: {h}, height: {int(vw)} }});",
                        f"    findings.push(...nfr.layoutFindings(await nfr.layoutProbe(page), {json.dumps(f'{s['url_template']} landscape')}));"]
            out += ["    expect(nfr.split(findings, testInfo.annotations, 'responsive'), 'layout findings').toEqual([]);",
                    "  });"]
        return out
    return _file("compatibility", states, project, ac_ids, body)


def gen_resilience_spec(states: list[dict], project: dict, ac_ids: list[str], forms: list[dict] = ()) -> str:
    tags = _tags("resilience", ac_ids)
    get_forms = {}
    for fm in forms or []:
        if (fm.get("method") or "get").lower() == "get":
            text = [x for x in fm.get("fields") or [] if (x.get("type") or "text") in ("text", "search")]
            if text:
                get_forms.setdefault(fm.get("url_template"), []).append((fm, text[0]))

    def body(s, title):
        out = [f"  test({json.dumps(f'{title} offline and slow network {tags}')}, async ({{ page, context, browserName }}, testInfo) => {{",
               "__LOGIN__",
               "    const pageErrors: string[] = [];",
               "    page.on('pageerror', (e) => pageErrors.push(e.message));",
               f"    await page.goto({json.dumps(s['url'])});",
               "    await context.setOffline(true);",
               "    await page.reload().catch(() => {});          // the browser's own offline page is acceptable",
               "    await context.setOffline(false);",
               f"    const back = await page.goto({json.dumps(s['url'])});",
               "    const findings = nfr.checkErrorPage(back?.status() ?? 0, await page.locator('body').innerText(), 'after reconnecting');",
               "    if (browserName === 'chromium') {        // slow 3G through CDP",
               "      const cdp = await context.newCDPSession(page);",
               "      await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 400, downloadThroughput: 50_000, uploadThroughput: 20_000 });",
               f"      const slow = await page.goto({json.dumps(s['url'])}, {{ timeout: 60_000 }});",
               "      findings.push(...nfr.checkErrorPage(slow?.status() ?? 0, await page.locator('body').innerText(), 'on a slow network'));",
               "      await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });",
               "    }",
               "    for (const e of pageErrors) findings.push({ rule: 'page-error', message: e.slice(0, 200), level: 'fail' });",
               "    expect(nfr.split(findings, testInfo.annotations, 'resilience'), 'resilience findings').toEqual([]);",
               "  });"]
        for fm, field in get_forms.get(s["url_template"], []):
            sel = f"#{fm['dom_id']}" if fm.get("dom_id") else "form[method=get]"
            field_sel = f'[name="{field.get("name")}"]'
            ftitle = f"{title} {sel} handles unusual input {tags}"
            out += [f"  test({json.dumps(ftitle)}, async ({{ page }}, testInfo) => {{", "__LOGIN__",
                    "    const findings: nfr.Finding[] = [];",
                    f"    for (const value of {json.dumps(UNUSUAL_INPUT, ensure_ascii=False)}) {{",
                    f"      await page.goto({json.dumps(s['url'])});",
                    f"      await page.locator({json.dumps(sel)}).locator({json.dumps(field_sel)}).fill(value);",
                    f"      const [resp] = await Promise.all([page.waitForResponse((r) => r.request().resourceType() === 'document'),"
                    f" page.locator({json.dumps(sel)}).locator('[type=submit]').first().click()]);",
                    "      findings.push(...nfr.checkErrorPage(resp.status(), await page.locator('body').innerText(), `input ${JSON.stringify(value.slice(0, 20))}`));",
                    "    }",
                    "    expect(nfr.split(findings, testInfo.annotations, 'resilience'), 'unusual-input findings').toEqual([]);",
                    "  });"]
        return out
    return _file("resilience", states, project, ac_ids, body)


def gen_i18n_spec(states: list[dict], project: dict, ac_ids: list[str]) -> str:
    opt = options(project, "i18n")
    tags = _tags("i18n", ac_ids)
    out = _header()
    roles = (project.get("auth") or {}).get("roles") or {}
    for locale in opt["locales"]:
        for tz in opt["timezones"]:
            for role, sts in _groups(states).items():
                out.append(f"test.describe({json.dumps(f'i18n {locale} {tz} ({role})')}, () => {{")
                use = {"locale": locale, "timezoneId": tz}
                if _role_auth(project) and role in roles:
                    use["role"] = role
                out.append(f"  test.use({json.dumps(use)});")
                login = "" if "role" in use or role == "guest" else _login(project, role)
                for s in sts:
                    t_title = f"i18n: {s['url_template']} {locale} {tz} ({role}) {tags}"
                    out += [f"  test({json.dumps(t_title)}, async ({{ page }}, testInfo) => {{"]
                    if login:
                        out.append(login)
                    out += [f"    await page.goto({json.dumps(s['url'])});",
                            "    await page.waitForLoadState('load');",
                            f"    const where = {json.dumps(s['url_template'] + ' ' + locale)};",
                            "    const findings = nfr.layoutFindings(await nfr.layoutProbe(page), where);",
                            "    if (/^(ar|he|fa|ur)\\b/.test(" + json.dumps(locale) + ")) {",
                            "      await nfr.setRtl(page);",
                            "      findings.push(...nfr.layoutFindings(await nfr.layoutProbe(page), `${where} rtl`));",
                            "    }",
                            "    await nfr.expandText(page);",
                            "    findings.push(...nfr.layoutFindings(await nfr.layoutProbe(page), `${where} +40% text`));",
                            "    expect(nfr.split(findings, testInfo.annotations, 'i18n'), 'i18n findings').toEqual([]);",
                            "  });"]
                out += ["});", ""]
    return "\n".join(out)


# ── driver ───────────────────────────────────────────────────────────────────

def _load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def generate(project_dir: Path, out_dir: Path | None = None) -> list[Path]:
    project_dir = Path(project_dir)
    project = yaml.safe_load((project_dir / "project.yaml").read_text(encoding="utf-8")) or {}
    f = flags(project)
    if not any(f.values()):
        return []
    comp = project_dir / "test_comprehension"
    app_map = _load(comp / "app_map.json", {"states": []})
    reqs = _load(comp / "requirements.json", [])
    forms = (_load(comp / "form_model.json", {}) or {}).get("forms") or []
    baseline = _load(comp / "baseline.json", {})
    out_dir = out_dir or project_dir / "test_creation" / "test_scripts" / "nfr"
    out_dir.mkdir(parents=True, exist_ok=True)
    states, written = pick_states(app_map), []

    def write(name: str, text: str):
        p = out_dir / name
        p.write_text(text, encoding="utf-8")
        written.append(p)

    if f["accessibility"]:
        write("nfr_a11y.spec.ts", gen_a11y_spec(states, project, nfr_ac_ids(reqs, "accessibility"), forms))
    if f["visual"]:
        write("nfr_visual.spec.ts", gen_visual_spec(states, project, nfr_ac_ids(reqs, "visual")))
    if f["performance"]:
        write("nfr_perf.spec.ts", gen_perf_spec(states, project, nfr_ac_ids(reqs, "performance"), baseline))
    if f["security_passive"]:
        ac = nfr_ac_ids(reqs, "security_passive")
        origins: dict[str, list[dict]] = {}
        for s in states:
            origins.setdefault(origin_of(s["url"]), []).append(s)
        for origin, sts in origins.items():
            slug = re.sub(r"\W+", "_", urlsplit(origin).netloc).strip("_")
            write(f"nfr_security_{slug}.spec.ts", gen_security_spec(origin, sts, project, ac))
    if f["compatibility"]:
        write("nfr_responsive.spec.ts", gen_responsive_spec(states, project, nfr_ac_ids(reqs, "compatibility")))
    if f["resilience"]:
        write("nfr_resilience.spec.ts", gen_resilience_spec(states, project, nfr_ac_ids(reqs, "resilience"), forms))
    if f["i18n"]:
        write("nfr_i18n.spec.ts", gen_i18n_spec(states, project, nfr_ac_ids(reqs, "i18n")))
    # a type switched off since the last run: its old spec goes too, so it no longer runs
    keep = {p.name for p in written}
    for old in out_dir.glob("nfr_*.spec.ts"):
        if old.name not in keep:
            old.unlink()
    return written


_TITLE_RE = re.compile(r'^\s*test(?:\.skip)?\(("(?:[^"\\\n]|\\.)*"), async', re.M)


def spec_tests(text: str) -> list[dict]:
    """The tests a generated NFR spec contains: title + the AC ids its tags link."""
    out = []
    for raw in _TITLE_RE.findall(text):
        title = json.loads(raw)
        out.append({"title": title, "ac_ids": re.findall(r"@(AC-[\w.-]+)", title)})
    return out


def register(project_dir: Path, written: list[Path]) -> Dict[str, int]:
    """Wire the NFR specs into the pipeline: one test_suite.json entry per file (generation_mode "nfr", so
    ui_execution and suites run it and rerender leaves it alone) and one test_plans.json entry with a tc_id per test,
    so traceability links its ACs and matches its results. Entries of NFR files that no longer exist are removed."""
    from contracts.artifacts import load_payload, save_artifact
    tc = Path(project_dir) / "test_creation"
    suite_path, plans_path = tc / "test_suite.json", tc / "test_plans.json"
    suite = load_payload("test_suite", str(suite_path), {}) or {}
    plans = load_payload("test_plans", str(plans_path), {}) or {}
    specs = [x for x in suite.get("specs") or [] if x.get("generation_mode") != "nfr"]
    plans = {k: v for k, v in plans.items() if not str(k).startswith("NFR_")}
    counts: Dict[str, int] = {}
    for path in written:
        sid = "NFR_" + path.stem.replace(".spec", "").replace("nfr_", "").upper()
        tests = spec_tests(path.read_text(encoding="utf-8"))
        specs.append({"spec_id": sid, "file": f"nfr/{path.name}", "module_id": "nfr", "status": "new",
                      "generation_mode": "nfr", "last_result": None})
        plans[sid] = {"generation_mode": "nfr", "tests": [
            {"name": t["title"], "title": t["title"], "type": "nfr", "tc_id": f"{sid.replace('_', '-')}-{i:03d}",
             "ac_ids": t["ac_ids"], "ac_link": "direct" if t["ac_ids"] else None}
            for i, t in enumerate(tests, start=1)]}
        counts[sid] = len(tests)
    suite["specs"] = specs
    suite.setdefault("project", Path(project_dir).name)
    save_artifact("test_suite", str(suite_path), suite)
    save_artifact("test_plans", str(plans_path), plans)
    return counts


if __name__ == "__main__":
    pdir = Path(sys.argv[1])
    files = generate(pdir)
    for w in files:
        print(w)
    if "--register" in sys.argv:
        print(register(pdir, files))
