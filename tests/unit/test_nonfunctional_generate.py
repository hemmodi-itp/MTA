import json

from tools.nonfunctional.generate import generate, pick_states


def _state(sid, tmpl, roles, access="reachable", status=200):
    return {"state_id": sid, "url": f"http://127.0.0.1:8765{tmpl}", "url_template": tmpl, "roles": roles,
            "access": access, "status": status}


def _project(tmp_path, flags):
    d = tmp_path / "p"
    (d / "test_comprehension").mkdir(parents=True)
    (d / "project.yaml").write_text(
        "test_types:\n" + "".join(f"  {k}: {v}\n" for k, v in flags.items()) +
        "auth:\n  roles:\n    user:\n      steps:\n        - goto: http://127.0.0.1:8765/login\n"
        "        - click: '#go'\n", encoding="utf-8")
    states = [_state("a", "/login", ["guest", "user"]), _state("b", "/cart", ["user"]),
              _state("c", "/cart", ["admin"]), _state("d", "/admin", ["user"], "blocked", 403)]
    (d / "test_comprehension" / "app_map.json").write_text(json.dumps({"states": states}), encoding="utf-8")
    (d / "test_comprehension" / "requirements.json").write_text(json.dumps([{"acceptance_criteria": [
        {"id": "AC-9.1", "statement": "The page meets WCAG 2.1 AA accessibility."}]}]), encoding="utf-8")
    return d


def test_pick_states_dedups_and_skips_blocked():
    s = [_state("a", "/x", ["admin"]), _state("b", "/x", ["user"]), _state("c", "/y", ["user"], "blocked", 403)]
    assert [x["state_id"] for x in pick_states({"states": s})] == ["b"]


def test_generates_both_specs_for_two_pages(tmp_path):
    files = generate(_project(tmp_path, {"accessibility": "true", "security_passive": "true"}))
    assert [f.name for f in files] == ["nfr_a11y.spec.ts", "nfr_security_127_0_0_1_8765.spec.ts"]
    a11y, sec = (f.read_text(encoding="utf-8") for f in files)
    assert a11y.count("\ntest(") == 2 and "@a11y @AC-9.1" in a11y and "wcag21aa" in a11y
    assert '"#go"' in a11y and sec.count("\ntest(") == 2 and "@security @nfr" in sec
    assert 'page.goto("http://127.0.0.1:8765/cart")' in sec


def test_flags_off_generates_nothing(tmp_path):
    assert generate(_project(tmp_path, {"accessibility": "false"})) == []
