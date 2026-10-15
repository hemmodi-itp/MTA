import json

from tools.nonfunctional.generate import TYPES, generate, pick_states, register, spec_tests


def _state(sid, tmpl, roles, access="reachable", status=200):
    return {"state_id": sid, "url": f"http://127.0.0.1:8765{tmpl}", "url_template": tmpl, "roles": roles,
            "access": access, "status": status}


def _project(tmp_path, flags, role_auth=False, extra=""):
    d = tmp_path / "p"
    (d / "test_comprehension").mkdir(parents=True)
    (d / "project.yaml").write_text(
        "test_types:\n" + "".join(f"  {k}: {v}\n" for k, v in flags.items()) +
        "auth:\n  roles:\n    user:\n      steps:\n        - goto: http://127.0.0.1:8765/login\n"
        "        - click: '#go'\n        - wait: 500\n" +
        (f"execution:\n  role_auth: true\n" if role_auth else "") + extra, encoding="utf-8")
    states = [_state("a", "/login", ["guest", "user"]), _state("b", "/cart", ["user"]),
              _state("c", "/cart", ["admin"]), _state("d", "/admin", ["user"], "blocked", 403),
              _state("e", "/products", ["user"])]
    comp = d / "test_comprehension"
    (comp / "app_map.json").write_text(json.dumps({"states": states}), encoding="utf-8")
    (comp / "requirements.json").write_text(json.dumps([{"acceptance_criteria": [
        {"id": "AC-9.1", "statement": "The page meets WCAG 2.1 AA accessibility."}]}]), encoding="utf-8")
    (comp / "form_model.json").write_text(json.dumps({"forms": [
        {"url_template": "/products", "dom_id": "search-form", "method": "get",
         "fields": [{"name": "q", "type": "search"}], "submit": {"text": "Search"}},
        {"url_template": "/cart", "dom_id": "discount-form", "method": "post", "action": "/cart/discount",
         "fields": [{"name": "code", "type": "text", "constraints": {"effective_required": True}}],
         "submit": {"text": "Apply"}},
        {"url_template": "/cart", "dom_id": "clear-form", "method": "post", "action": "/cart/clear",
         "fields": [{"name": "why", "type": "text", "constraints": {"required": True}}],
         "submit": {"text": "Delete all", "destructive": True}},
        {"url_template": "/cart", "dom_id": "note-form", "method": "post", "action": "/cart/note",
         "fields": [{"name": "note", "type": "text"}], "submit": {"text": "Save"}}]}), encoding="utf-8")
    (comp / "baseline.json").write_text(json.dumps({"states": {"S1": {
        "url": "http://127.0.0.1:8765/products", "timing": {"ttfb_ms": 40, "load_ms": 300}}}}), encoding="utf-8")
    return d


def test_pick_states_dedups_and_skips_blocked():
    s = [_state("a", "/x", ["admin"]), _state("b", "/x", ["user"]), _state("c", "/y", ["user"], "blocked", 403)]
    assert [x["state_id"] for x in pick_states({"states": s})] == ["b"]


def test_a11y_and_security_specs(tmp_path):
    files = generate(_project(tmp_path, {"accessibility": "true", "security_passive": "true"}))
    assert [f.name for f in files] == ["nfr_a11y.spec.ts", "nfr_security_127_0_0_1_8765.spec.ts"]
    a11y, sec = (f.read_text(encoding="utf-8") for f in files)
    titles = [t["title"] for t in spec_tests(a11y)]
    assert len([t for t in titles if "announces errors" not in t]) == 3
    assert any("discount-form announces errors" in t for t in titles)
    assert not any("clear-form" in t or "note-form" in t for t in titles)   # destructive / nothing required
    assert "@a11y @AC-9.1" in a11y and "wcag22aa" in a11y and "keyboardWalk" in a11y
    assert '"#go"' in a11y and "waitForTimeout" not in a11y       # login steps inline, waits are load-state waits
    assert len(spec_tests(sec)) == 3 and "@security @nfr" in sec and "checkStackTrace" in sec


def test_passive_security_never_submits_anything(tmp_path):
    sec = generate(_project(tmp_path, {"security_passive": "true"}))[0].read_text(encoding="utf-8")
    for forbidden in (".fill(", ".click(", ".type(", "<script", "' OR ", "mockRoute", "page.request"):
        assert forbidden not in sec.replace("page.locator(\"#go\").click()", "")


def test_role_auth_uses_storage_state_instead_of_login_steps(tmp_path):
    a11y = generate(_project(tmp_path, {"accessibility": "true"}, role_auth=True))[0].read_text(encoding="utf-8")
    assert 'test.use({ role: "user" });' in a11y and '"#go"' not in a11y


def test_every_type_generates_and_registers(tmp_path):
    d = _project(tmp_path, {t: "true" for t in TYPES},
                 extra="nfr:\n  compatibility: {viewports: [320, 1280]}\n  i18n: {locales: [en-US, ar-EG], timezones: [UTC]}\n")
    files = generate(d)
    names = [f.name for f in files]
    assert names == ["nfr_a11y.spec.ts", "nfr_visual.spec.ts", "nfr_perf.spec.ts", "nfr_security_127_0_0_1_8765.spec.ts",
                     "nfr_responsive.spec.ts", "nfr_resilience.spec.ts", "nfr_i18n.spec.ts", "nfr_links.spec.ts"]
    text = {f.name: f.read_text(encoding="utf-8") for f in files}
    assert "toHaveScreenshot" in text["nfr_visual.spec.ts"] and "visual-baseline" in text["nfr_visual.spec.ts"]
    perf = text["nfr_perf.spec.ts"]
    assert '{"ttfb_ms": 40, "load_ms": 300}' in perf and '"ttfb_ms": 1500' in perf      # baseline + default budget
    assert len(spec_tests(text["nfr_responsive.spec.ts"])) == 3 * 2 and "landscape" in text["nfr_responsive.spec.ts"]
    res = text["nfr_resilience.spec.ts"]
    assert "setOffline(true)" in res and "emulateNetworkConditions" in res and "search-form handles unusual input" in res
    assert len(spec_tests(text["nfr_i18n.spec.ts"])) == 3 * 2 and '"locale": "ar-EG"' in text["nfr_i18n.spec.ts"]
    links = text["nfr_links.spec.ts"]
    assert "nfr.brokenLinks(page)" in links and "@links" in links
    assert ".click(" not in links.replace("page.locator(\"#go\").click()", "")      # GETs only, besides the login
    counts = register(d, files)
    assert counts["NFR_A11Y"] == 4 and counts["NFR_I18N"] == 6 and counts["NFR_LINKS"] == 3
    plans = json.loads((d / "test_creation" / "test_plans.json").read_text(encoding="utf-8"))
    plans = plans.get("plans", plans)
    t0 = plans["NFR_A11Y"]["tests"][0]
    assert t0["tc_id"] == "NFR-A11Y-001" and t0["ac_ids"] == ["AC-9.1"]
    suite = json.loads((d / "test_creation" / "test_suite.json").read_text(encoding="utf-8"))
    assert {s["file"] for s in suite["specs"] if s["generation_mode"] == "nfr"} == {f"nfr/{n}" for n in names}


def test_switching_a_type_off_removes_its_spec_and_registration(tmp_path):
    d = _project(tmp_path, {"accessibility": "true", "performance": "true"})
    register(d, generate(d))
    (d / "project.yaml").write_text((d / "project.yaml").read_text(encoding="utf-8").replace("performance: true",
                                                                                            "performance: false"))
    files = generate(d)
    register(d, files)
    assert not (d / "test_creation" / "test_scripts" / "nfr" / "nfr_perf.spec.ts").exists()
    plans = json.loads((d / "test_creation" / "test_plans.json").read_text(encoding="utf-8"))
    assert "NFR_PERF" not in plans.get("plans", plans)


def test_flags_off_generates_nothing(tmp_path):
    assert generate(_project(tmp_path, {"accessibility": "false"})) == []
