"""End-to-end test of the runtime chain on a local fixture app: discover → classify → plan → execute.

Needs Playwright's Chromium (skipped otherwise). The fixture server runs on 127.0.0.1 only.
"""

import http.server
import threading
from functools import partial

import pytest

pytest.importorskip("playwright.sync_api")

from engines.runtime.actions import generate_action_plan  # noqa: E402
from engines.runtime.classification import classify  # noqa: E402
from engines.runtime.discovery import discover  # noqa: E402
from engines.runtime.executor import execute_plans  # noqa: E402

LOGIN = """<!doctype html><title>Login</title><h1>Sign in</h1>
<form id=f><label>Email <input type=email name=email required></label>
<label>Password <input type=password name=password required></label><button type=submit>Log in</button></form>
<p class=error></p>
<script>document.getElementById('f').onsubmit = e => { e.preventDefault();
  const ok = e.target.email.value === 'qa@example.com' && e.target.password.value === 'pw-123';
  if (ok) { localStorage.setItem('session', '1'); location.href = '/new'; }
  else document.querySelector('.error').textContent = 'Invalid credentials'; };</script>"""

NEW = """<!doctype html><title>New document</title>
<script>if (!localStorage.getItem('session')) location.replace('/login');</script>
<h1>Create a BRD</h1>
<div class=panel>
  <label>Project name <input name=project required></label>
  <label>Problem statement <textarea name=problem required></textarea></label>
  <label>Audience <select name=audience required><option>Select…</option><option>Executives</option><option>Engineers</option></select></label>
  <button id=gen>Generate documents</button>
  <div id=out></div>
</div>
<script>
document.getElementById('gen').onclick = () => {
  const p = document.querySelector('[name=problem]').value, n = document.querySelector('[name=project]').value;
  const out = document.getElementById('out');
  if (!p || !n) { out.innerHTML = '<p role=alert>Please fill all required fields</p>'; return; }
  out.innerHTML = '<div class=spinner>Generating…</div>';
  setTimeout(() => {
    const blob = new Blob(['BRD for ' + n + '\\n\\nProblem: ' + p], {type: 'text/plain'});
    out.innerHTML = '<h2>Your BRD is ready</h2><p>Problem: ' + p + '</p><a id=dl download="brd.txt">Download BRD</a>';
    document.getElementById('dl').href = URL.createObjectURL(blob);
  }, 2500);
};
</script>"""

SHOP = """<!doctype html><title>Shop</title>
<script>if (!localStorage.getItem('session')) location.replace('/login');</script>
<h1>Products</h1><span id=badge></span>
<ul>
  <li class=item><b>Backpack</b> carry everything <button>Add to cart</button></li>
  <li class=item><b>Bike light</b> see at night <button>Add to cart</button></li>
</ul>
<script>let n = 0; document.querySelectorAll('li button').forEach(b => b.onclick = () => {
  n++; document.getElementById('badge').textContent = 'Cart: ' + n + ' (' + b.parentElement.querySelector('b').textContent + ')'; });</script>"""

# BRD_Agent-like: a marketing landing page with a "Log in" link, and a login form drawn ~4 s after load (hydration)
LANDING = """<!doctype html><title>Suite</title><h1>Welcome</h1><a href="/late-login">Log in</a> <a href="/x">Get started</a>"""
LATE_LOGIN = """<!doctype html><title>Login</title><div id=root>Loading…</div>
<script>setTimeout(() => { document.getElementById('root').innerHTML = `""" + LOGIN.split("<h1>", 1)[1].split("<script>")[0] + """`;
  document.getElementById('f').onsubmit = e => { e.preventDefault();
    if (e.target.email.value === 'qa@example.com' && e.target.password.value === 'pw-123') {
      localStorage.setItem('session', '1'); location.replace('/'); }
    else document.querySelector('.error').textContent = 'Invalid email or password'; }; }, 4000);</script>"""

# BRD_Agent-like repeater: the "Objectives" list starts with no rows; "+ Add" creates one; every field must have a point
REPEATER = """<!doctype html><title>Plan</title>
<script>if (!localStorage.getItem('session')) location.replace('/login');</script>
<div class=form>
  <label>Project <input name=project></label>
  <div class=field><span>Objectives</span><div id=rows></div>
    <button type=button id=add>+ Add</button></div>
  <div class=field><span>Risks</span><div id=rows2></div>
    <button type=button id=add2>+ Add</button></div>
  <button type=button id=go>Generate plan</button><div id=out></div>
</div>
<script>
const mk = (id, ph) => () => { const i = document.createElement('input'); i.placeholder = ph; document.getElementById(id).appendChild(i); };
document.getElementById('add').onclick = mk('rows', 'Objective');
document.getElementById('add2').onclick = mk('rows2', 'Risk');
document.getElementById('go').onclick = () => {
  const p = document.querySelector('[name=project]').value;
  const o = [...document.querySelectorAll('#rows input')].map(i => i.value).filter(Boolean);
  const r = [...document.querySelectorAll('#rows2 input')].map(i => i.value).filter(Boolean);
  document.getElementById('out').textContent = (!p || !o.length || !r.length)
    ? 'Please add at least one point to every field before generating'
    : 'Plan ready for ' + p + ': ' + o.join(', ') + ' / risks: ' + r.join(', ');
};
</script>"""

# BRD_Agent-like backend failure: Generate shows the app's own error banner and no download ever appears
BROKEN = """<!doctype html><title>New</title>
<script>if (!localStorage.getItem('session')) location.replace('/login');</script>
<h1>New request</h1><button id=gen>Generate Documents</button><div id=out></div>
<script>document.getElementById('gen').onclick = () => {
  document.getElementById('out').innerHTML = '<p class="text-red-600 error-banner">Request failed (500)</p>'; };</script>"""

# BRD_Agent-like intake: every field carries its own "Not applicable" box (same label each time), and Generate demands
# a point in every field not marked "Not applicable", naming the ones missing
INTAKE = """<!doctype html><title>Intake</title>
<script>if (!localStorage.getItem('session')) location.replace('/login');</script>
<div class=form>
  <div class=field data-name="Problem Statement"><div class=head><label for=p>Problem Statement (required)</label></div><textarea id=p></textarea></div>
  <div class=field data-name="Constraints"><div class=head><span>Constraints</span>
    <label><input type=checkbox class=na> Not applicable — omit this section</label></div>
    <textarea placeholder="One item per line"></textarea></div>
  <div class=field data-name="Dependencies"><div class=head><span>Dependencies</span>
    <label><input type=checkbox class=na> Not applicable — omit this section</label></div>
    <textarea placeholder="What this depends on"></textarea></div>
  <button type=button id=go>Generate Documents</button><div id=out></div>
</div>
<script>
document.getElementById('go').onclick = () => {
  const blocks = [...document.querySelectorAll('.field')];
  const name = b => b.dataset.name;
  const na = b => b.querySelector('.na') && b.querySelector('.na').checked;
  const missing = blocks.filter(b => !na(b) && !b.querySelector('textarea').value.trim()).map(name);
  document.getElementById('out').innerHTML = missing.length
    ? '<p class=error>Please add at least one point to every field before generating (or mark it "Not applicable" if it genuinely doesn&#39;t apply):' + missing.join(', ') + '.</p>'
    : '<h2>Documents ready</h2><p>omitted: ' + (blocks.filter(na).map(name).join(', ') || 'none') + '</p>';
};
</script>"""

PAGES = {"/": LOGIN, "/intake": INTAKE, "/login": LOGIN, "/new": NEW, "/shop": SHOP, "/landing": LANDING, "/late-login": LATE_LOGIN,
         "/plan": REPEATER, "/broken": BROKEN, "/flaky": "<!doctype html><title>Flaky</title><h1>Back again</h1>"}
_HITS: dict = {}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        _HITS[path] = _HITS.get(path, 0) + 1
        if path == "/flaky" and _HITS[path] == 1:  # the first visit drops the connection: a brief outage
            self.close_connection = True
            self.connection.close()
            return
        body = PAGES.get(path)
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write((body or "not found").encode())

    def log_message(self, *a):
        pass


@pytest.fixture(autouse=True)
def _local_fixture_server_allowed(monkeypatch):
    """The fixture app runs on 127.0.0.1, which the SSRF guard blocks unless local targets are explicitly allowed."""
    monkeypatch.setenv("AQP_ALLOW_PRIVATE_TARGETS", "1")


@pytest.fixture(scope="module")
def app_url():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/"
    srv.shutdown()


CREDS = {"username": "qa@example.com", "password": "pw-123"}


def _plan(prof, tests):
    return generate_action_plan(classify(prof), prof, tests, has_credentials=True)


def test_document_generator_end_to_end(app_url, tmp_path):
    prof = discover(app_url, known_pages=["/new"], credentials=CREDS, max_pages=3)
    assert prof["login"]["succeeded"] and prof["downloads"] is False  # the download link only appears after generating
    tests = [
        {"id": "t1", "code": "TC-001", "title": "BRD generated from the problem statement", "variant_type": "positive",
         "input": "Clinic patients cannot book appointments online", "expected_behavior": "A BRD is produced",
         "criterion_code": "AC-01.1"},
        {"id": "t2", "code": "TC-002", "title": "Required fields are enforced", "variant_type": "negative", "input": "",
         "expected_behavior": "The app asks for the missing fields", "criterion_code": "AC-01.2"},
    ]
    plan = _plan(prof, tests)
    run = execute_plans(app_url, plan, tmp_path, credentials=CREDS)
    by = {r["test_code"]: r for r in run["results"]}
    assert run["login"]["succeeded"]

    ok = by["TC-001"]
    assert ok["status"] == "completed", ok
    fills = [s for s in ok["steps"] if s["action"] in ("fill", "select")]
    assert fills and all(s["status"] == "passed" and s["locator"] == "discovery-match" for s in fills)
    assert "Clinic patients cannot book appointments online" in ok["captures"]["dom_excerpt"]
    assert (tmp_path / ok["captures"]["screenshot"]).stat().st_size > 1000
    assert ok["expectations"][0]["expectation"] == "A BRD is produced"
    assert next(s for s in ok["steps"] if s["action"] == "assert")["status"] == "deferred"

    neg = by["TC-002"]
    assert neg["status"] == "completed" and "Please fill all required fields" in neg["captures"]["dom_excerpt"]
    assert not any(s.get("synthetic") for s in plan["plans"][1]["steps"])


def test_download_and_repeated_button_context(app_url, tmp_path):
    shop_plan = {"plans": [{
        "plan_id": "AP-TC-010", "test_code": "TC-010", "status": "ready", "scored": True, "steps": [
            {"n": 1, "action": "login"}, {"n": 2, "action": "goto", "url": "/shop"},
            {"n": 3, "action": "click", "target": {"kind": "button", "page": "/shop", "text": "Add to cart", "nth": 1,
                                                    "context": "Bike light see at night"}},
            {"n": 4, "action": "capture", "what": ["dom_text"]}]},
        {"plan_id": "AP-TC-011", "test_code": "TC-011", "status": "ready", "scored": True, "steps": [
            {"n": 1, "action": "login"}, {"n": 2, "action": "goto", "url": "/new"},
            {"n": 3, "action": "fill", "target": {"kind": "field", "label": "Project name", "name": "project"}, "value": "Clinic"},
            {"n": 4, "action": "fill", "target": {"kind": "field", "label": "Problem statement", "name": "problem"}, "value": "No online booking"},
            {"n": 5, "action": "click", "target": {"kind": "button", "text": "Generate documents"}},
            {"n": 6, "action": "wait_for", "kind": "settled", "timeout_ms": 30_000},
            {"n": 7, "action": "expect_download", "target": {"kind": "link", "text": "Download BRD", "label": "Download BRD",
                                                              "href": app_url + "never-matches"}},
            {"n": 8, "action": "capture", "what": ["screenshot", "download"]}]},
        {"plan_id": "AP-TC-012", "test_code": "TC-012", "status": "ready", "scored": True, "steps": [
            {"n": 1, "action": "login"}, {"n": 2, "action": "goto", "url": "/new"},
            {"n": 3, "action": "click", "target": {"kind": "button", "text": "Does not exist"}},
            {"n": 4, "action": "fill", "target": {"kind": "field", "label": "Project name"}, "value": "x"},
            {"n": 5, "action": "capture", "what": ["screenshot"]}]},
    ]}
    run = execute_plans(app_url, shop_plan, tmp_path, credentials=CREDS)
    by = {r["test_code"]: r for r in run["results"]}
    assert "Cart: 1 (Bike light)" in by["TC-010"]["captures"]["dom_excerpt"]  # the second "Add to cart", by context

    dl = by["TC-011"]
    assert dl["status"] == "failed" and dl["failed_step"] == 7  # link target with a wrong href is not guessed
    assert "Your BRD is ready" in dl["captures"]["dom_excerpt"]   # evidence captured even after the failure

    bad = by["TC-012"]
    assert bad["status"] == "failed" and bad["failed_step"] == 3 and "Does not exist" in bad["error"]
    assert [s["status"] for s in bad["steps"]][3:] == ["skipped", "passed"]  # later actions skipped, capture still runs
    assert (tmp_path / "AP-TC-012" / "failure-step3.png").exists()
    assert run["counts"] == {**run["counts"], "plans": 3, "completed": 1, "failed": 2}


def test_wrong_password_blocks_every_plan(app_url, tmp_path):
    plan = {"plans": [{"plan_id": "AP-1", "status": "ready", "steps": [{"n": 1, "action": "login"}]}]}
    run = execute_plans(app_url, plan, tmp_path, credentials={"username": "qa@example.com", "password": "nope"})
    assert run["status"] == "blocked" and run["results"][0]["status"] == "blocked"
    assert "nope" not in str(run)  # the password never appears in results


def test_generated_download_found_at_runtime_and_collected_as_evidence(app_url, tmp_path):
    from engines.runtime.evidence import collect_evidence

    prof = discover(app_url, known_pages=["/new"], credentials=CREDS, max_pages=3)
    test = {"id": "t1", "code": "TC-001", "title": "BRD generated from the problem statement", "variant_type": "positive",
            "input": "Clinic patients cannot book appointments online", "expected_behavior": "A BRD is produced",
            "criterion_code": "AC-01.1"}
    # the code graph would say Document Generator; the download link only exists after generating
    plan = generate_action_plan({"app_type": "Document Generator", "components": []}, prof, [test], has_credentials=True)
    dl_step = next(s for s in plan["plans"][0]["steps"] if s["action"] == "expect_download")
    assert dl_step["target"]["kind"] == "auto"
    run = execute_plans(app_url, plan, tmp_path, credentials=CREDS)
    r = next(x for x in run["results"] if x["test_code"] == "TC-001")
    assert r["status"] == "completed", r["steps"]
    assert r["captures"]["downloads"][0]["name"] == "brd.txt"

    col = collect_evidence(run, plan, [test], tmp_path)
    b = next(x for x in col["bundles"] if x["test_code"] == "TC-001")
    assert "Your BRD is ready" in b["observed"]["ui_output"] and "Create a BRD" not in b["observed"]["ui_output"]
    doc = b["observed"]["documents"][0]
    assert doc["readable"] and "Problem: Clinic patients cannot book appointments online" in doc["text_excerpt"]
    assert b["completeness"] == {"output_captured": True, "expected_output": "document", "missing": []}


def test_login_follows_landing_link_and_waits_for_late_form(app_url):
    from playwright.sync_api import sync_playwright
    from engines.runtime.discovery import _log_in

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ok = _log_in(browser.new_page(), app_url + "landing", CREDS, lambda m: None)
            assert ok["succeeded"], ok
            assert ok["login_url"].endswith("/late-login")
            bad = _log_in(browser.new_page(), app_url + "landing", {"username": "qa@example.com", "password": "wrong"},
                          lambda m: None)
            assert not bad["succeeded"] and bad["error"] == "Invalid email or password"
        finally:
            browser.close()


def test_list_rows_behind_add_buttons_are_discovered_and_filled(app_url, tmp_path):
    from engines.runtime.actions import build_inventory

    prof = discover(app_url, known_pages=["/plan"], credentials=CREDS, max_pages=3)
    inv = build_inventory(prof)
    fields = {e["label"]: e for e in inv["elements"].values() if e["kind"] == "field"}
    assert {"Project", "Objective", "Risk"} <= set(fields)                 # row inputs exist only after "+ Add"
    assert fields["Objective"]["revealed_by"]["text"] == "+ Add" and fields["Risk"]["revealed_by"]["nth"] == 1
    test = {"id": "t9", "code": "TC-009", "title": "Plan generated", "variant_type": "positive", "input": "Clinic booking",
            "expected_behavior": "A plan is generated"}
    proposal = {"TC-009": {"applicable": True, "steps": [
        {"action": "fill", "element_id": fields["Project"]["id"], "value": "Clinic booking"},
        {"action": "fill", "element_id": fields["Objective"]["id"], "value": "Online booking"},
        {"action": "fill", "element_id": fields["Risk"]["id"], "value": "Low adoption"}]}}
    plan = generate_action_plan({"app_type": "Form Application", "components": []}, prof, [test], proposals=proposal,
                                has_credentials=True)
    acts = [(s["action"], (s.get("target") or {}).get("text") or (s.get("target") or {}).get("label")) for s in plan["plans"][0]["steps"]]
    assert acts.index(("click", "+ Add")) < acts.index(("fill", "Objective"))
    run = execute_plans(app_url, {"plans": [plan["plans"][0]]}, tmp_path, credentials=CREDS)
    r = run["results"][0]
    assert r["status"] == "completed", r["steps"]
    assert "Plan ready for Clinic booking: Online booking / risks: Low adoption" in r["captures"]["dom_excerpt"]


def _one(plan_id, steps):
    return {"plans": [{"plan_id": plan_id, "test_code": plan_id[3:], "status": "ready", "scored": True,
                       "steps": [{"n": 1, "action": "login"}] + steps}]}


def test_failure_names_the_error_the_app_showed(app_url, tmp_path):
    plan = _one("AP-TC-030", [{"n": 2, "action": "goto", "url": "/broken"},
                              {"n": 3, "action": "click", "target": {"kind": "button", "text": "Generate Documents"}},
                              {"n": 4, "action": "expect_download", "target": {"kind": "auto"}}])
    r = execute_plans(app_url, plan, tmp_path, credentials=CREDS)["results"][0]
    assert r["status"] == "failed" and r["failed_step"] == 4
    assert r["error"].startswith("no download was produced") and "the app showed: “Request failed (500)”" in r["error"]


def test_unreachable_app_pauses_then_reruns_the_plan(app_url, tmp_path):
    _HITS.pop("/flaky", None)
    run = execute_plans(app_url, _one("AP-TC-031", [{"n": 2, "action": "goto", "url": "/flaky"},
                                                    {"n": 3, "action": "capture", "what": ["dom_text"]}]),
                        tmp_path, credentials=CREDS)
    r = run["results"][0]
    assert len(run["results"]) == 1 and r["status"] == "completed", r
    assert "net::ERR_" in r["first_attempt_error"] and "Back again" in r["captures"]["dom_excerpt"]
    assert run["retried"] == ["AP-TC-031"] and run["app_outages"] == [{"recovered_after_s": 0}]


def test_same_labelled_boxes_resolve_by_field_and_rejected_input_is_completed(app_url, tmp_path):
    from engines.runtime.actions import build_inventory

    prof = discover(app_url, known_pages=["/intake"], credentials=CREDS, max_pages=3)
    inv = build_inventory(prof)
    boxes = [e for e in inv["elements"].values() if e["kind"] == "field" and e["type"] == "checkbox"]
    assert sorted(e.get("group") for e in boxes) == ["Constraints", "Dependencies"]   # which field each box belongs to
    problem = next(e for e in inv["elements"].values() if e.get("label", "").startswith("Problem Statement"))
    na_deps = next(e for e in boxes if e["group"] == "Dependencies")
    test = {"id": "t40", "code": "TC-040", "title": "Dependencies section omitted when marked not applicable",
            "variant_type": "positive", "input": "Problem Statement: Clinic booking is manual",
            "expected_behavior": "The Dependencies section is omitted"}
    proposal = {"TC-040": {"applicable": True, "steps": [
        {"action": "fill", "element_id": problem["id"], "value": "Clinic booking is manual"},
        {"action": "check", "element_id": na_deps["id"]}]}}
    plan = generate_action_plan({"app_type": "Document Generator", "components": []}, prof, [test], proposals=proposal,
                                has_credentials=True)
    steps = [s for s in plan["plans"][0]["steps"] if s["action"] != "expect_download"]  # the fixture offers no file
    run = execute_plans(app_url, {"plans": [{**plan["plans"][0], "steps": steps}]}, tmp_path, credentials=CREDS)
    r = run["results"][0]
    assert r["status"] == "completed", r["steps"]
    # the Dependencies box was ticked (not the first same-labelled one), and the field the app then asked for was filled
    assert "omitted: Dependencies" in r["captures"]["dom_excerpt"] and "Documents ready" in r["captures"]["dom_excerpt"]
    assert "the app asked for Constraints" in r["completed_input"] and "MTA filled Constraints" in r["completed_input"]
