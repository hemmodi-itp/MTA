"""Phase 2 tasks 2.3–2.7 end to end on a local fixture site (real Chromium, 127.0.0.1, no LLM).

The site has: a home page, two item pages (/items/1, /items/2 — one URL template), a page with tabs,
an accordion, a dialog trigger and a destructive "Delete everything" toggle, three forms (native
validation, JS validation with role=alert errors, server validation), a JSON API called by fetch(),
a page that logs a console error, a login + a role-gated /admin page, plus links the crawler must
never follow (logout, delete, an off-host URL). Every request is counted by the server, so the tests
can assert what discovery did *not* do.
"""

import json
import os
import sys
import urllib.parse

import pytest

pytest.importorskip("playwright.sync_api")

sys.path.insert(0, os.path.dirname(__file__))
from _deep_fixture_server import FixtureServer, html  # noqa: E402

from tools.discovery.deep.config import DiscoveryConfig, RoleConfig  # noqa: E402
from tools.discovery.deep.crawl import DeepDiscovery  # noqa: E402
from tools.safety.policy import SafetyPolicy  # noqa: E402

NAV = ("<nav aria-label='Main'><a href='/'>Home</a> <a href='/items/1'>Item one</a> <a href='/items/2'>Item two</a> "
       "<a href='/widgets'>Widgets</a> <a href='/forms/native'>Native form</a> <a href='/forms/js'>JS form</a> "
       "<a href='/forms/server'>Server form</a> <a href='/admin'>Admin</a> <a href='/logout'>Log out</a> "
       "<a href='/items/2/delete'>Delete item</a> <a href='https://elsewhere.invalid/x'>Elsewhere</a></nav>")


def _role(headers):
    cookie = headers.get("cookie", "")
    return "admin" if "role=admin" in cookie else ("user" if "role=user" in cookie else None)


def _page(body, title="Fixture"):
    return 200, {"Content-Type": "text/html; charset=utf-8"}, html(NAV + body, title)


def home(m, p, q, b, h):
    return _page("<h1>Home</h1><p>Welcome</p>", "Home")


def item(m, p, q, b, h):
    n = p.rsplit("/", 1)[-1]
    return _page(f"<h1>Item {n}</h1><button id='fav'>Favourite</button>", f"Item {n}")


def widgets(m, p, q, b, h):
    return _page("""
<h1>Widgets</h1>
<div role="tablist"><button role="tab" id="t1" aria-selected="true" aria-controls="p1">Overview</button>
<button role="tab" id="t2" aria-selected="false" aria-controls="p2">Specs</button></div>
<div role="tabpanel" id="p1">Overview text</div>
<div role="tabpanel" id="p2" hidden><label for="spec-q">Spec filter</label><input id="spec-q" name="spec_q"></div>
<button id="acc" aria-expanded="false" aria-controls="acc-body">More options</button>
<div id="acc-body" hidden><label for="opt">Option</label><input id="opt" name="opt" required>
  <button id="acc-save">Save option</button></div>
<button id="open-dlg" aria-haspopup="dialog">Open dialog</button>
<dialog id="dlg" aria-label="Quick edit"><form method="dialog"><label for="dlg-name">Dialog name</label>
  <input id="dlg-name" name="dlg_name" maxlength="10" required><button id="dlg-ok">OK</button></form></dialog>
<button id="nuke" aria-expanded="false" onclick="fetch('/nuked', {method: 'POST'})">Delete everything</button>
<script>
  for (const t of document.querySelectorAll('[role=tab]')) t.onclick = () => {
    for (const x of document.querySelectorAll('[role=tabpanel]')) x.hidden = x.id !== t.getAttribute('aria-controls');
    for (const x of document.querySelectorAll('[role=tab]')) x.setAttribute('aria-selected', String(x === t));
  };
  document.getElementById('acc').onclick = (e) => {
    const body = document.getElementById('acc-body'); body.hidden = !body.hidden;
    e.target.setAttribute('aria-expanded', String(!body.hidden));
  };
  document.getElementById('open-dlg').onclick = () => document.getElementById('dlg').showModal();
  fetch('/api/items?page=1').then(r => r.json());
  console.error('widget init warning: legacy plugin missing');
</script>""", "Widgets")


def native_form(m, p, q, b, h):
    return _page("""
<h1>Native</h1>
<form id="native" method="post" action="/forms/native">
  <label for="email">Email</label><input id="email" name="email" type="email" required>
  <label for="nick">Nickname</label><input id="nick" name="nick" maxlength="8">
  <label for="qty">Quantity</label><input id="qty" name="qty" type="number" min="1" max="5">
  <button>Check it</button>
</form>""", "Native")


def js_form(m, p, q, b, h):
    if m == "POST":
        return 303, {"Location": "/forms/js?ok=1"}, b""
    return _page("""
<h1>JS form</h1>
<div id="errs" role="alert" hidden></div>
<form id="jsf" method="post" action="/forms/js" novalidate>
  <label for="title">Title</label><input id="title" name="title" required>
  <label for="amount">Amount</label><input id="amount" name="amount" inputmode="decimal">
  <button id="jsf-save">Save entry</button>
</form>
<script>
document.getElementById('jsf').addEventListener('submit', (ev) => {
  const f = ev.target, errs = [];
  if (!f.title.value.trim()) errs.push('Title is required');
  else if (f.title.value.length > 30) errs.push('Title must be at most 30 characters');
  if (f.amount.value && !/^\\d+(\\.\\d+)?$/.test(f.amount.value)) errs.push('Amount must be a number');
  if (errs.length) { ev.preventDefault(); const box = document.getElementById('errs');
    box.innerHTML = '<ul>' + errs.map(e => '<li>' + e + '</li>').join('') + '</ul>'; box.hidden = false; }
});
</script>""", "JS form")


def server_form(m, p, q, b, h):
    err = ""
    if m == "POST":
        data = urllib.parse.parse_qs(b.decode())
        code = (data.get("code") or [""])[0]
        if code != "OK123":
            err = "<p id='code-err' class='error' role='alert'>Unknown code</p>"
        else:
            return 303, {"Location": "/forms/server?done=1"}, b""
    status = 400 if err else 200
    s, hdr, body = _page(f"""<h1>Server form</h1>{err}
<form id="srv" method="post" action="/forms/server"><label for="code">Code</label>
<input id="code" name="code"><button>Redeem</button></form>""", "Server form")
    return status, hdr, body


def api_items(m, p, q, b, h):
    return 200, {"Content-Type": "application/json"}, json.dumps(
        {"items": [{"id": 1, "name": "A", "price": 1.5}], "page": 1, "total": 1}).encode()


def admin(m, p, q, b, h):
    if _role(h) != "admin":
        return 403, {"Content-Type": "text/html"}, html("<p role='alert'>Access denied</p>", "Forbidden")
    return _page("<h1>Admin</h1><button id='purge-cache'>Refresh stats</button>", "Admin")


def login(m, p, q, b, h):
    if m == "POST":
        data = urllib.parse.parse_qs(b.decode())
        role = (data.get("u") or [""])[0]
        return 303, {"Location": "/", "Set-Cookie": f"role={role}; Path=/"}, b""
    return _page("<form method='post' action='/login'><label for='u'>User</label><input id='u' name='u'>"
                 "<label for='pw'>Password</label><input id='pw' name='pw' type='password'><button id='go'>Log in</button></form>",
                 "Login")


def trap(m, p, q, b, h):
    return 200, {"Content-Type": "text/html"}, html("<p>should never be visited</p>")


ROUTES = {"/": home, "/items/*": item, "/widgets": widgets, "/forms/native": native_form, "/forms/js": js_form,
          "/forms/server": server_form, "/api/items": api_items, "/admin": admin, "/login": login,
          "/logout": trap, "/nuked": trap}
# /items/2/delete matches "/items/*" too — but the crawler must refuse it before any request.


@pytest.fixture()
def site():
    srv = FixtureServer(routes=ROUTES).start()
    yield srv
    srv.stop()


def _policy(env="local"):
    return SafetyPolicy(environment=env, environment_declared=True, allow_destructive=False,
                        allowed_hosts=["127.0.0.1"], allowed_hosts_source="explicit")


def _run(site, roles=None, env="local", **cfg):
    config = DiscoveryConfig(deep=True, **{"max_minutes": 4, **cfg})
    roles = roles or [RoleConfig(name="default", strategy="anonymous")]
    seeds = [{"url": site.url("/"), "module_id": None, "setup_steps": []}]
    return DeepDiscovery("fixture", config, roles, seeds, _policy(env), log=lambda m: None, config_hash="h").run()


@pytest.fixture(scope="module")
def docs():
    """One full crawl (forms + network + baseline) shared by the read-only assertions below."""
    srv = FixtureServer(routes=ROUTES).start()
    try:
        yield srv, _run(srv)
    finally:
        srv.stop()


# ── 2.4 crawl + state model ─────────────────────────────────────────────

def test_crawl_visits_every_page_template_once(docs):
    site, d = docs
    templates = {s["url_template"] for s in d["app_map"]["states"] if s["kind"] == "page"}
    assert {"/", "/items/{id}", "/widgets", "/forms/native", "/forms/js", "/forms/server", "/admin"} <= templates
    # one sample per URL template: /items/1 visited, /items/2 not
    assert site.hits["GET /items/1"] >= 1 and site.hits["GET /items/2"] == 0
    item_transitions = [t for t in d["app_map"]["transitions"] if (t["element"] or {}).get("name") == "Item two"]
    assert item_transitions and all(t["to_state"] and t["resolved_by_template"] for t in item_transitions)
    assert d["app_map"]["stopped_by"] == {"default": "queue_empty"}


def test_crawl_never_follows_logout_delete_or_offhost_links(docs):
    site, d = docs
    assert site.hits["GET /logout"] == 0
    assert site.hits["GET /items/2/delete"] == 0
    reasons = {(s.get("url") or "").split("/", 3)[-1]: s["reason"] for s in d["app_map"]["skipped"] if s.get("url")}
    assert reasons.get("logout") == "skip_link"
    assert reasons.get("items/2/delete") == "skip_link"
    assert "host_not_allowed" in {s["reason"] for s in d["app_map"]["skipped"]}
    unresolved = {t["element"]["name"]: t["unresolved_reason"] for t in d["app_map"]["transitions"] if not t["to_state"]}
    assert unresolved.get("Log out") == "skip_link" and unresolved.get("Elsewhere") == "host_not_allowed"


def test_expanders_reveal_hidden_states_and_destructive_ones_are_never_clicked(docs):
    site, d = docs
    revealed = [s for s in d["app_map"]["states"] if s["kind"] == "revealed"]
    names = {s["revealed_by"]["element"]["name"] for s in revealed}
    assert {"Specs", "More options", "Open dialog"} <= names
    for s in revealed:
        assert s["revealed_by"]["from_state"] in {x["state_id"] for x in d["app_map"]["states"]}
        assert any(t["action"] == "expand" and t["to_state"] == s["state_id"] for t in d["app_map"]["transitions"])
    assert site.hits["POST /nuked"] == 0
    assert any(s.get("reason") == "destructive" and "Delete everything" in (s.get("element") or "")
               for s in d["app_map"]["skipped"])


def test_state_ids_are_stable_across_runs(site, docs):
    a = _run(site, validation={"enabled": False})
    b = docs[1]
    assert sorted(s["state_id"] for s in a["app_map"]["states"]) == sorted(s["state_id"] for s in b["app_map"]["states"])


def test_bounds_stop_the_crawl(site):
    d = _run(site, max_pages=2, validation={"enabled": False})
    assert d["app_map"]["stopped_by"]["default"] == "max_pages"
    assert len([s for s in d["app_map"]["states"] if s["kind"] == "page"]) <= 2
    d = _run(site, max_depth=0, validation={"enabled": False})
    assert {s["url_template"] for s in d["app_map"]["states"] if s["kind"] == "page"} == {"/"}


# ── 2.3 observed validation oracle ──────────────────────────────────────

def _form(d, template):
    return next(f for f in d["form_model"]["forms"] if f["url_template"] == template and f["probes"])


def _obs(form, field):
    return next(x for x in form["fields"] if x["name"] == field)["observed_messages"]


def test_native_validation_is_recorded_without_reaching_the_server(docs):
    site, d = docs
    f = _form(d, "/forms/native")
    empty = next(p for p in f["probes"] if p["probe"] == "empty")
    assert empty["native"]["blocked"] is True and empty["native"]["messages"]["email"]
    assert _obs(f, "email")["required_missing"]["source"] == "native"
    assert _obs(f, "email")["wrong_type"]["source"] == "native"
    assert _obs(f, "qty")["above_max"]["source"] == "native"
    too_long = next(p for p in f["probes"] if p["probe"] == "too_long" and p["field"] == "nick")
    assert too_long["value_rule"] == "len=maxlength+1=9"


def test_js_validation_errors_are_read_and_attributed(docs):
    _, d = docs
    f = _form(d, "/forms/js")
    assert _obs(f, "title")["required_missing"]["text"] == "Title is required"
    assert _obs(f, "title")["required_missing"]["source"] == "client"
    assert _obs(f, "title")["too_long"]["text"] == "Title must be at most 30 characters"
    assert _obs(f, "amount")["wrong_type"]["text"] == "Amount must be a number"


def test_server_validation_errors_and_acceptance_are_recorded(docs):
    site, d = docs
    f = _form(d, "/forms/server")
    obs = _obs(f, "code")
    assert obs["too_long"]["text"] == "Unknown code" and obs["too_long"]["source"] == "server"
    probe = next(p for p in f["probes"] if p["probe"] == "too_long")
    assert probe["network"][0]["method"] == "POST" and probe["network"][0]["status"] == 400
    assert probe["accepted"] is False


def test_prod_runs_client_only_probes_and_no_write_reaches_the_server(site):
    d = _run(site, env="prod")
    assert d["form_model"]["probe_mode"] == "client_only"
    assert site.hits["POST /forms/server"] == 0 and site.hits["POST /forms/js"] == 0
    probe = next(p for p in _form(d, "/forms/server")["probes"] if p["probe"] == "too_long")
    assert probe["network"] and all(n["aborted"] for n in probe["network"] if n["method"] == "POST")


def test_unspecified_environment_is_gated_like_prod():
    # the crawler's probe mode is `policy.non_prod`; an undeclared environment is never non-prod
    assert _policy("unspecified").non_prod is False and _policy("prod").non_prod is False
    assert _policy("local").non_prod is True


def test_forms_in_revealed_states_are_probed_by_replaying_the_expander(docs):
    _, d = docs
    dlg = next(f for f in d["form_model"]["forms"] if any(x["name"] == "dlg_name" for x in f["fields"]))
    assert dlg["probes"] and not any(p.get("error") for p in dlg["probes"])


def test_validation_can_be_switched_off(site):
    d = _run(site, validation={"enabled": False})
    assert d["form_model"]["probe_mode"] == "disabled"
    assert all(not f["probes"] for f in d["form_model"]["forms"])
    assert site.hits["POST /forms/server"] == 0


# ── 2.5 network inventory ───────────────────────────────────────────────

def test_network_inventory_templates_paths_and_infers_schemas(docs):
    _, d = docs
    eps = {(e["method"], e["path_template"], e["kind"]): e for e in d["api_inventory"]["endpoints"]}
    api = eps[("GET", "/api/items", "fetch")]
    assert api["request"]["query_params"] == ["page"]
    schema = api["response"]["json_schema"]
    assert schema["type"] == "object" and schema["required"] == ["items", "page", "total"]
    assert schema["properties"]["items"]["items"]["properties"]["price"]["type"] == "number"
    assert ("GET", "/items/{id}", "page") in eps
    post = eps[("POST", "/forms/server", "form_submit")]
    assert post["request"]["fields"] == ["code"] and post["statuses"].get("400", 0) >= 1
    assert any(t["action"].startswith("probe ") for t in post["triggers"])
    # values are never stored
    assert "OK123" not in json.dumps(d["api_inventory"])


# ── 2.7 baseline ────────────────────────────────────────────────────────

def test_baseline_records_console_errors_and_timing_per_state(docs):
    _, d = docs
    widgets_state = next(s for s in d["app_map"]["states"] if s["url_template"] == "/widgets" and s["kind"] == "page")
    base = d["baseline"]["states"][widgets_state["state_id"]]
    assert any("legacy plugin missing" in c["text"] for c in base["console_errors"])
    assert set(base["timing"]) >= {"ttfb_ms", "dcl_ms", "load_ms", "requests"}
    home_state = next(s for s in d["app_map"]["states"] if s["url_template"] == "/")
    assert d["baseline"]["states"][home_state["state_id"]]["console_errors"] == []


# ── 2.6 roles + permission matrix ───────────────────────────────────────

def test_roles_are_crawled_separately_and_diffed(site):
    admin_steps = [{"goto": site.url("/login")}, {"fill": {"selector": "#u", "value": "admin"}},
                   {"fill": {"selector": "#pw", "value": "x"}}, {"click": "#go"}]
    roles = [RoleConfig(name="admin", strategy="setup", steps=admin_steps), RoleConfig(name="guest", strategy="anonymous")]
    d = _run(site, roles=roles, validation={"enabled": False})
    states = {s["url_template"]: s["access"] for s in d["permission_matrix"]["states"]}
    assert states["/admin"] == {"admin": "reachable", "guest": "blocked"}
    assert d["permission_matrix"]["roles"] == ["admin", "guest"]
    refresh = next(a for a in d["permission_matrix"]["actions"] if a["element"]["name"] == "Refresh stats")
    assert refresh["visibility"] == {"admin": "visible", "guest": "blocked"}
    assert d["app_map"]["roles"] == [{"name": "admin", "strategy": "setup"}, {"name": "guest", "strategy": "anonymous"}]
    assert "x" not in json.dumps(d["app_map"]["roles"])


def test_a_failed_login_is_reported_not_raised(site):
    roles = [RoleConfig(name="ghost", strategy="storageState", storage_state_path="does/not/exist.json")]
    d = _run(site, roles=roles, validation={"enabled": False})
    assert d["app_map"]["stopped_by"]["ghost"].startswith("login_failed")
    assert d["app_map"]["states"] == []
