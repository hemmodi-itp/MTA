"""Phase 2 deep discovery — pure-function tests (no browser).

URL templating, state-hash dedup, JSON-schema inference, the permission-matrix diff, network
aggregation + write guard, deterministic form-probe planning, role/visit classification and config.
"""

import pytest

from tools.discovery.deep import forms as F
from tools.discovery.deep.config import (DiscoveryConfig, RoleConfig, config_hash, resolve_discovery_config,
                                         resolve_roles)
from tools.discovery.deep.crawl import is_expander, norm_url
from tools.discovery.deep.json_schema import infer, infer_many, merge
from tools.discovery.deep.network import InflightTracker, WriteGuard, aggregate, request_fields
from tools.discovery.deep.permission import action_keys, build_matrix
from tools.discovery.deep.roles import classify_visit, default_role, redirected_to_login
from tools.discovery.deep.state_hash import element_signature, state_id, structural_hash
from tools.discovery.web.urls import normalise_route, same_url, template_path, template_url


# ── URL templating ──────────────────────────────────────────────────────

@pytest.mark.parametrize("path,expected", [
    ("/products/3", "/products/{id}"),
    ("/products/42/edit", "/products/{id}/edit"),
    ("/orders/550e8400-e29b-41d4-a716-446655440000", "/orders/{id}"),
    ("/runs/20261002-095607-907774", "/runs/{id}"),
    ("/files/9f86d081884c7d65", "/files/{id}"),
    ("/products/new", "/products/new"),
    ("/api/v2/items", "/api/v2/items"),
    ("/", "/"),
    ("/products/", "/products"),
    ("", "/"),
])
def test_template_path(path, expected):
    assert template_path(path) == expected
    assert template_path(template_path(path)) == template_path(path)   # idempotent


def test_agent_eval_route_rule_is_unchanged():
    # the moved Agent-Eval rule keeps its own semantics (short numeric ids stay literal there)
    assert normalise_route("/runs/20261002-095607-907774") == "/runs/{id}"
    assert normalise_route("/products/3") == "/products/3"
    assert normalise_route("/new") == "/new"


def test_template_url_keeps_query_names_only():
    assert template_url("http://h/products?page=2&q=pen") == "/products?page&q"
    assert template_url("http://h/products?q=x&page=9") == "/products?page&q"
    assert template_url("http://h/products") == "/products"
    assert template_url("http://h/items/7#top") == "/items/{id}"


def test_same_url_ignores_fragment_and_trailing_slash():
    assert same_url("http://h/a/#x", "http://h/a")
    assert not same_url("http://h/a?x=1", "http://h/a?x=2")
    assert norm_url("http://h/a/#frag") == "http://h/a"


def test_agent_eval_reexports_are_the_moved_objects():
    import engines.runtime.discovery as d
    from tools.discovery.web import login, ready, urls, links
    assert d._normalise is urls.normalise_route and d._log_in is login.log_in
    assert d._SKIP_LINK is links.SKIP_LINK and d._READY_JS is ready.READY_JS and d.NAV_TIMEOUT_MS == 45_000


# ── state hash ──────────────────────────────────────────────────────────

def _el(tag="input", role="textbox", name="q", id_="q", type_="text", visible=True, text="Hello", frame=None):
    el = {"tag_name": tag, "aria_role": role, "attribute_locators": {"name": name, "id": id_, "type": type_},
          "quality": {"visible": visible}, "display_text": text}
    if frame:
        el["frame"] = {"path": frame}
    return el


def test_same_structure_with_different_text_values_and_record_ids_hashes_equal():
    a = [_el(id_="qty-3", text="Mouse"), _el(tag="button", role="button", name="", id_="", text="Buy")]
    b = [_el(tag="button", role="button", name="", id_="", text="Kaufen"), _el(id_="qty-42", text="Lamp")]
    assert structural_hash(a, {"h1": 1}) == structural_hash(b, {"h1": 1})


def test_structure_changes_change_the_hash():
    base = [_el()]
    assert structural_hash(base) != structural_hash(base + [_el(name="extra", id_="extra")])
    assert structural_hash(base) != structural_hash([_el(visible=False)])          # an expander revealed it
    assert structural_hash(base, {"dialog[open]": 0}) != structural_hash(base, {"dialog[open]": 1})
    assert structural_hash(base) != structural_hash([_el(frame=["#pay"])])


def test_state_id_is_deterministic_and_template_scoped():
    h = structural_hash([_el()])
    assert state_id("/a", h) == state_id("/a", h) and state_id("/a", h) != state_id("/b", h)
    assert state_id("/a", h).startswith("S-") and len(state_id("/a", h)) == 12
    assert element_signature(_el(id_="row-12")) == element_signature(_el(id_="row-7"))


# ── JSON schema inference ───────────────────────────────────────────────

def test_infer_and_merge():
    s = infer({"id": 1, "tags": ["a"], "price": 1.5, "owner": None, "ok": True})
    assert s["properties"]["id"] == {"type": "integer"} and s["properties"]["tags"]["items"] == {"type": "string"}
    assert s["properties"]["owner"] == {"type": "null"} and s["required"] == ["id", "ok", "owner", "price", "tags"]
    m = infer_many([{"id": 1, "a": 1}, {"id": 2.5}])
    assert m["required"] == ["id"] and m["properties"]["id"] == {"type": "number"}
    assert merge({"type": "string"}, {"type": "integer"}) == {"type": ["integer", "string"]}
    assert infer_many([]) is None
    arr = infer([{"x": 1}, {"x": 2, "y": "z"}])
    assert arr["items"]["required"] == ["x"]


def test_infer_depth_is_capped():
    deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": 1}}}}}}}
    s = infer(deep)
    node = s
    for k in "abcdef":
        node = node["properties"][k]
    assert node == {"type": "object"}


# ── network ─────────────────────────────────────────────────────────────

def test_request_fields_never_keep_values():
    assert request_fields("application/json", '{"name": "secret", "n": 2}') == (
        ["n", "name"], {"type": "object", "properties": {"n": {"type": "integer"}, "name": {"type": "string"}},
                        "required": ["n", "name"]})
    assert request_fields("application/x-www-form-urlencoded", "user=bob&pw=hunter2") == (["pw", "user"], None)
    mp = 'Content-Disposition: form-data; name="file"; filename="evil.exe"\r\n\r\nX\r\nContent-Disposition: form-data; name="note"'
    assert request_fields("multipart/form-data; boundary=x", mp) == (["file", "note"], None)
    assert request_fields("text/plain", "abc") == ([], None)
    assert request_fields("application/json", "{not json") == ([], None)


def _rec(method="GET", path="/a", kind="page", status=200, role="user", trigger="navigate /a", aborted=False, **kw):
    r = {"method": method, "path_template": path, "query_params": [], "kind": kind, "host": "h:1",
         "auth_header": False, "cookie": True, "request_content_type": None, "request_fields": [],
         "request_schema": None, "trigger": trigger, "state_id": "S-1", "role": role, "status": status,
         "aborted": aborted, "response_content_type": "text/html", "response_schema": None}
    r.update(kw)
    return r


def test_aggregate_groups_counts_and_sorts():
    recs = [_rec(path="/b"), _rec(path="/a"), _rec(path="/a", status=404, role="guest"),
            _rec(method="POST", path="/a", kind="form_submit", status=None, aborted=True, request_fields=["x"]),
            _rec(method="POST", path="/a", kind="form_submit", status=400, request_fields=["y"])]
    eps = aggregate(recs)
    assert [(e["method"], e["path_template"]) for e in eps] == [("GET", "/a"), ("GET", "/b"), ("POST", "/a")]
    get_a = eps[0]
    assert get_a["statuses"] == {"200": 1, "404": 1} and get_a["roles"] == ["guest", "user"] and get_a["samples"] == 2
    post = eps[2]
    assert post["aborted"] == 1 and post["statuses"] == {"400": 1} and post["request"]["fields"] == ["x", "y"]


def test_aggregate_caps_triggers():
    eps = aggregate([_rec(trigger=f"navigate /a{i}") for i in range(25)])
    assert len(eps[0]["triggers"]) == 10


class _Route:
    def __init__(self):
        self.calls = []

    def continue_(self):
        self.calls.append("continue")

    def abort(self):
        self.calls.append("abort")


class _Req:
    def __init__(self, method):
        self.method = method
        self.resource_type = "fetch"
        self.url = "http://h/x"
        self.headers = {}
        self.post_data = None


def test_write_guard_aborts_writes_outside_a_probe_window():
    guard = WriteGuard()
    for method, expected in (("GET", "continue"), ("HEAD", "continue"), ("POST", "abort"), ("DELETE", "abort"),
                             ("PUT", "abort")):
        r = _Route()
        guard._handle(r, _Req(method))
        assert r.calls == [expected], method
    guard.allow_writes = True
    r = _Route()
    guard._handle(r, _Req("POST"))
    assert r.calls == ["continue"] and guard.aborted == 3


def test_inflight_tracker_counts_and_waits_for_quiet():
    t = InflightTracker()
    t._up(None), t._up(None), t._down(None)
    assert t.inflight == 1
    t._down(None), t._down(None)
    assert t.inflight == 0

    class _P:
        def __init__(self):
            self.n = 0

        def wait_for_timeout(self, ms):
            self.n += 1

    p = _P()
    assert t.wait_quiet(p) is True and p.n == 3          # 3 × 50 ms of quiet
    t._up(None)
    assert t.wait_quiet(_P(), max_ms=200) is False


# ── permission matrix ───────────────────────────────────────────────────

def test_permission_matrix_diff():
    results = [
        {"role": "admin", "pages": {
            "/admin": {"sample_url": "u/admin", "access": "reachable", "via": "crawl", "status": 200,
                       "actions": [("button", "Purge"), ("link", "Home")]},
            "/p": {"sample_url": "u/p", "access": "reachable", "via": "crawl", "actions": [("link", "Admin"), ("link", "Home")]}}},
        {"role": "user", "pages": {
            "/admin": {"sample_url": "u/admin", "access": "blocked", "via": "deep_link", "status": 403, "actions": []},
            "/p": {"sample_url": "u/p", "access": "reachable", "via": "crawl", "actions": [("link", "Home")]}}},
        {"role": "guest", "pages": {
            "/p": {"sample_url": "u/p", "access": "reachable", "via": "deep_link", "actions": [("link", "Home")]}}},
    ]
    m = build_matrix(results)
    states = {s["url_template"]: s for s in m["states"]}
    assert states["/admin"]["access"] == {"admin": "reachable", "user": "blocked", "guest": "unknown"}
    assert states["/p"]["access"]["guest"] == "reachable_unlinked"
    assert states["/admin"]["evidence"]["user"]["status"] == 403
    acts = {(a["url_template"], a["element"]["name"]): a for a in m["actions"]}
    assert acts[("/p", "Admin")]["visibility"] == {"admin": "visible", "user": "hidden", "guest": "hidden"}
    assert acts[("/p", "Admin")]["differs"] is True
    assert acts[("/p", "Home")]["differs"] is False
    assert acts[("/admin", "Purge")]["visibility"] == {"admin": "visible", "user": "blocked", "guest": "unknown"}
    assert acts[("/admin", "Purge")]["differs"] is False      # page-level blocking is reported in `states`


def test_action_keys_use_visible_named_elements_only():
    els = [{"aria_role": "button", "display_text": "Save\n changes", "quality": {"visible": True}},
           {"aria_role": "button", "display_text": "Hidden", "quality": {"visible": False}},
           {"aria_role": "link", "display_text": "", "quality": {"visible": True}}]
    assert action_keys(els) == [("button", "Save changes")]


# ── visits and roles ────────────────────────────────────────────────────

@pytest.mark.parametrize("req,final,status,expected", [
    ("http://h/admin", "http://h/admin", 200, "reachable"),
    ("http://h/admin", "http://h/admin", 403, "blocked"),
    ("http://h/admin", "http://h/admin", 401, "blocked"),
    ("http://h/admin", "http://h/login?next=/admin", 200, "blocked"),
    ("http://h/login", "http://h/login", 200, "reachable"),
    ("http://h/x", "http://h/x", 404, "not_found"),
    ("http://h/x", "http://h/x", 500, "error"),
    ("http://h/x", "http://h/x", None, "reachable"),
])
def test_classify_visit(req, final, status, expected):
    assert classify_visit(req, final, status) == expected


def test_redirected_to_login():
    assert redirected_to_login("http://h/cart", "http://h/sign-in")
    assert not redirected_to_login("http://h/login", "http://h/login")
    assert not redirected_to_login("http://h/cart", "http://h/cart")


def test_default_role_follows_the_project_auth():
    assert default_role({}).strategy == "anonymous"
    assert default_role({"auth_storage_state": ".auth/a.json"}).storage_state_path == ".auth/a.json"
    live = default_role({"auth_config": {"strategy": "live_login", "login_url": "http://h/login", "username_env": "U"}})
    assert live.strategy == "credentials" and live.login_url == "http://h/login" and live.username_env == "U"


# ── config ──────────────────────────────────────────────────────────────

def test_discovery_config_defaults_and_validation():
    cfg = resolve_discovery_config({})
    assert cfg["deep"] is False and cfg["max_pages"] == 25 and cfg["max_depth"] == 4 and cfg["max_minutes"] == 10
    assert cfg["validation"] == {"enabled": True, "max_probes_per_form": 20, "long_text_length": 1000}
    on = resolve_discovery_config({"discovery": {"deep": True, "max_pages": 5, "validation": {"enabled": False}}})
    assert on["deep"] is True and on["max_pages"] == 5 and on["validation"]["enabled"] is False
    bad = resolve_discovery_config({"discovery": {"deep": True, "max_pages": -3}})
    assert bad["deep"] is True and bad["max_pages"] == 25          # invalid -> defaults, switch kept


def test_roles_are_read_even_when_auth_is_disabled():
    raw = {"auth": {"enabled": False, "roles": {
        "guest": {"anonymous": True},
        "admin": {"strategy": "setup", "steps": [{"goto": "http://h/login"}, "junk"]},
        "broken": {"strategy": "magic"},
    }}}
    roles = {r["name"]: r for r in resolve_roles(raw)}
    assert set(roles) == {"guest", "admin"}
    assert roles["guest"]["strategy"] == "anonymous" and roles["admin"]["steps"] == [{"goto": "http://h/login"}]
    assert RoleConfig(**roles["admin"]).public() == {"name": "admin", "strategy": "setup"}


def test_config_hash_tracks_everything_that_shapes_the_crawl():
    cfg, roles = DiscoveryConfig(deep=True), [RoleConfig(name="a")]
    base = config_hash(cfg, roles, ["http://h/"], {"environment": "local", "allowed_hosts": ["h"]})
    assert base == config_hash(cfg, roles, ["http://h/"], {"environment": "local", "allowed_hosts": ["h"]})
    assert base != config_hash(cfg, roles, ["http://h/x"], {"environment": "local", "allowed_hosts": ["h"]})
    assert base != config_hash(DiscoveryConfig(deep=True, max_pages=3), roles, ["http://h/"], {"environment": "local", "allowed_hosts": ["h"]})
    assert base != config_hash(cfg, roles + [RoleConfig(name="b")], ["http://h/"], {"environment": "local", "allowed_hosts": ["h"]})
    assert base != config_hash(cfg, roles, ["http://h/"], {"environment": "prod", "allowed_hosts": ["h"]})


# ── expanders ───────────────────────────────────────────────────────────

def _x(tag="button", role="button", hints=None, href=None, visible=True, enabled=True):
    el = {"tag_name": tag, "aria_role": role, "state_hints": hints or {}, "quality": {"visible": visible, "enabled": enabled}}
    if href:
        el["href"] = href
    return el


def test_expander_detection():
    assert is_expander(_x(tag="summary", role=None))
    assert is_expander(_x(tag="div", role="tab"))
    assert is_expander(_x(hints={"expanded": "false"}))
    assert is_expander(_x(hints={"haspopup": "menu"}))
    assert is_expander(_x(hints={"toggle": "modal"}))
    assert is_expander(_x(hints={"type": "button", "controls": "panel"}))
    assert not is_expander(_x(hints={"haspopup": "false"}))
    assert not is_expander(_x(hints={"type": "submit", "controls": "x"}))
    assert not is_expander(_x(hints={"expanded": "false"}, visible=False))
    assert not is_expander(_x(hints={"expanded": "false"}, enabled=False))
    assert not is_expander(_x(tag="a", role="link", hints={"expanded": "false"}, href="http://h/other"))


# ── form probe planning (deterministic) ─────────────────────────────────

def _f(key, type_="text", **kw):
    return {"key": key, "type": type_, "visible": True, "name": kw.pop("name", key), **kw}


FORM = {"index": 0, "kind": "form", "id": "signup", "method": "post", "action": "/s", "submit": {"key": "f0", "text": "Create"},
        "fields": [_f("f0-0", "email", required=True), _f("f0-1", "text", maxlength=8, name="nick"),
                   _f("f0-2", "number", min="1", max="5", name="qty"), _f("f0-3", "select", required=True, name="plan",
                   options=[{"value": "", "text": "-", "disabled": False}, {"value": "pro", "text": "Pro", "disabled": False}]),
                   _f("f0-4", "file", accept=".csv,.png", name="doc"), _f("f0-5", "text", readonly=True, name="ro"),
                   _f("f0-6", "text", inputmode="decimal", name="price")]}


def test_plan_probes_is_deterministic_and_complete():
    cfg = DiscoveryConfig(deep=True)
    a, skipped = F.plan_probes(FORM, cfg)
    b, _ = F.plan_probes(FORM, cfg)
    assert a == b and skipped == []
    kinds = [(p["probe"], p["field"]) for p in a]
    assert kinds == [("empty", None),
                     ("required_missing", "f0-0"), ("too_long", "f0-0"), ("wrong_type", "f0-0"),
                     ("too_long", "f0-1"),
                     ("below_min", "f0-2"), ("above_max", "f0-2"), ("non_integer", "f0-2"),
                     ("required_missing", "f0-3"),
                     ("wrong_accept", "f0-4"),
                     ("too_long", "f0-6"), ("wrong_type", "f0-6")]
    assert "f0-5" not in a[0]["fills"]                       # readonly field is never touched
    nick = next(p for p in a if p["field"] == "f0-1")
    assert nick["fills"]["f0-1"] == ("fill", "a" * 9) and nick["value_rule"] == "len=maxlength+1=9"
    # every other field holds its valid value
    assert nick["fills"]["f0-0"] == ("fill", "qa@example.com") and nick["fills"]["f0-3"] == ("select", "pro")
    assert nick["fills"]["f0-2"] == ("fill", "1") and nick["fills"]["f0-6"] == ("fill", "10")
    assert next(p for p in a if p["probe"] == "above_max")["fills"]["f0-2"] == ("fill", "6")
    assert next(p for p in a if p["probe"] == "non_integer")["fills"]["f0-2"] == ("fill", "1.5")
    bad = next(p for p in a if p["probe"] == "wrong_accept")["fills"]["f0-4"]
    assert bad[0] == "file" and bad[1]["name"] == "mta_probe.txt"


def test_plan_probes_respects_the_budget_and_long_text_default():
    cfg = DiscoveryConfig(deep=True, validation={"max_probes_per_form": 3, "long_text_length": 40})
    probes, skipped = F.plan_probes(FORM, cfg)
    assert len(probes) == 3 and len(skipped) == 9 and all(s["reason"] == "budget" for s in skipped)
    email_long = next(p for p in probes if p["probe"] == "too_long")
    assert email_long["fills"]["f0-0"] == ("fill", "a" * 28 + "@example.com")
    assert email_long["value_rule"] == "len=40 (default; no maxlength)"


@pytest.mark.parametrize("field,expected", [
    (_f("k", "date", min="2026-02-01"), [("below_min", ("fill", "2026-01-31"))]),
    (_f("k", "date", max="2024-02-28"), [("above_max", ("fill", "2024-02-29"))]),       # leap year
    (_f("k", "number", min="0", max="10", step="0.5"), [("below_min", ("fill", "-0.5")), ("above_max", ("fill", "10.5"))]),
    (_f("k", "url"), [("too_long", None), ("wrong_type", ("fill", "not a url"))]),
    (_f("k", "text", pattern="[a-z]+"), [("too_long", None), ("wrong_type", ("fill", "!!!"))]),
    (_f("k", "text", minlength=3, maxlength=5), [("too_long", ("fill", "aaaaaa")), ("too_short", ("fill", "aa"))]),
    (_f("k", "checkbox", required=True), [("required_missing", ("check", False))]),
])
def test_invalid_probes_per_type(field, expected):
    got = [(k, a) for k, a, _ in F.invalid_probes(field, DiscoveryConfig(deep=True))]
    assert [k for k, _ in got] == [k for k, _ in expected]
    for (k, a), (_, want) in zip(got, expected):
        if want is not None:
            assert a == want, k


@pytest.mark.parametrize("field,expected", [
    (_f("k", "select", options=[{"value": "", "disabled": False}, {"value": "x", "disabled": True}, {"value": "y", "disabled": False}]), ("select", "y")),
    (_f("k", "checkbox"), None),
    (_f("k", "radio"), ("check", True)),
    (_f("k", "number", min="3", max="2"), ("fill", "2")),
    (_f("k", "date", min="2026-06-01"), ("fill", "2026-06-01")),
    (_f("k", "text", pattern="[0-9]+"), ("fill", "12345")),
    (_f("k", "text", minlength=6), ("fill", "TTTTTT")),
    (_f("k", "text", maxlength=2), ("fill", "Te")),
    (_f("k", "tel"), ("fill", "5551234567")),
    (_f("k", "text", name="unit_price"), ("fill", "10")),
])
def test_valid_values(field, expected):
    assert F.valid_action(field)[0] == expected


def test_skip_reasons():
    ok = F.skip_reason(FORM, destructive_submit=False, destructive_allowed=False)
    assert ok is None
    assert F.skip_reason({**FORM, "fields": []}, False, False) == "no_fillable_fields"
    assert F.skip_reason(FORM, destructive_submit=True, destructive_allowed=False) == "destructive_submit"
    assert F.skip_reason(FORM, destructive_submit=True, destructive_allowed=True) is None
    search = {"kind": "form", "method": "get", "submit": {"text": "Search"}, "fields": [_f("s", "search")]}
    assert F.skip_reason(search, False, False) == "get_form_no_constraints"
    assert F.skip_reason({**search, "fields": [_f("s", "search", maxlength=20)]}, False, False) is None
    virtual = {"kind": "virtual", "submit": None, "fields": [_f("v")]}
    assert F.skip_reason(virtual, False, False) == "no_submit_control"


def test_form_fingerprint_is_stable_and_specific():
    fp = F.form_fingerprint("/s", FORM)
    assert fp == F.form_fingerprint("/s", dict(FORM)) and fp.startswith("F-")
    assert fp != F.form_fingerprint("/t", FORM)
    assert fp != F.form_fingerprint("/s", {**FORM, "fields": FORM["fields"][:2]})


def _probe(kind, field=None, errors=(), native=None, net=(), accepted=False, error=None):
    return {"probe": kind, "field": field, "visible_errors": list(errors), "native": {"messages": native or {}},
            "network": list(net), "accepted": accepted, "error": error}


def test_observed_messages_precedence():
    probes = [
        _probe("empty", errors=[{"text": "Name is required", "field": "name"}], native={"name": "Please fill"}),
        _probe("too_long", "name", errors=[{"text": "Too long", "field": None}],
               net=[{"method": "POST", "path": "/s", "status": 400, "aborted": False}]),
        _probe("wrong_type", "name", native={"name": "Bad"}),
        _probe("below_min", "name", accepted=True, net=[{"method": "POST", "path": "/s", "status": 200, "aborted": False}]),
        _probe("above_max", "name", error="could not restore"),
    ]
    obs = F.observed_messages("name", probes)
    assert obs["required_missing"] == {"text": "Name is required", "source": "client", "attribution": None, "probe": "empty"}
    assert obs["too_long"]["text"] == "Too long" and obs["too_long"]["source"] == "server"
    assert obs["too_long"]["attribution"] == "only_error"
    assert obs["wrong_type"] == {"text": "Bad", "source": "native", "attribution": "validity", "probe": "wrong_type"}
    assert obs["below_min"]["source"] == "accepted" and obs["below_min"]["text"] is None
    assert "above_max" not in obs
