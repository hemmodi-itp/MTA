"""Phase 2 task 2.1 / 2.2 — deep element capture on fixture pages (real Chromium, 127.0.0.1).

Covers the plan's required fixtures: custom widgets, shadow DOM, iframes, duplicate buttons inside
different dialogs (container-scoped locators), and constraint extraction.
"""

import os
import sys

import pytest

pytest.importorskip("playwright.sync_api")

sys.path.insert(0, os.path.dirname(__file__))
from _deep_fixture_server import FixtureServer  # noqa: E402

from tools.discovery.deep.config import DiscoveryConfig  # noqa: E402
from tools.discovery.deep.extract import extract_page  # noqa: E402
from tools.test_creation.script_generator.build_dom_locator_map import _best_locator_entry  # noqa: E402
from tools.test_creation.script_generator.locator_resolve import entry_resolves, resolve_entry  # noqa: E402


@pytest.fixture(scope="module")
def server():
    srv = FixtureServer().start()
    yield srv
    srv.stop()


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


def _extract(browser, url, **cfg):
    page = browser.new_page()
    page.goto(url)
    page.wait_for_load_state("networkidle")
    out = extract_page(page, DiscoveryConfig(deep=True, **cfg))
    return page, out


def _by_id(elements, element_id):
    return next(e for e in elements if (e["attribute_locators"] or {}).get("id") == element_id)


# ── custom widgets ───────────────────────────────────────────────────────

def test_custom_widgets_are_captured_with_a_reason(server, browser):
    page, out = _extract(browser, server.url("/widgets.html"))
    els = out["elements"]
    reasons = {(e["attribute_locators"] or {}).get("id"): e["capture_reason"] for e in els}
    assert reasons["div-button"] == "role:button"
    assert reasons["span-link"] == "role:link"
    assert reasons["tab-a"] == "role:tab" and reasons["tab-b"] == "role:tab"
    assert reasons["mi-1"] == "role:menuitem" and reasons["mi-2"] == "role:menuitemcheckbox"
    assert reasons["sw"] == "role:switch" and reasons["sl"] == "role:slider" and reasons["spin"] == "role:spinbutton"
    assert reasons["cb"] == "role:checkbox" and reasons["ti"] == "role:treeitem" and reasons["opt-red"] == "role:option"
    assert reasons["sb"] == "role:searchbox"
    assert reasons["editor"] == "contenteditable"
    assert reasons["onclick-div"] == "onclick"
    assert reasons["focus-span"] == "tabindex"
    assert reasons["card"] == "cursor_pointer"          # outermost pointer element only
    assert reasons["sum"] == "summary" and reasons["det"] == "details"
    for typed, kind in (("d", "date"), ("dt", "datetime-local"), ("t", "time"), ("r", "range"), ("c", "color"), ("f", "file")):
        assert reasons[typed] == f"input:{kind}"
    # descendants of the pointer card are not captured separately
    assert not any((e.get("display_text") or "") == "Click anywhere" for e in els)
    page.close()


def test_widget_role_locators_resolve_to_exactly_one_element(server, browser):
    page, out = _extract(browser, server.url("/widgets.html"))
    for element_id in ("div-button", "tab-b", "sw", "cb"):
        entry = _best_locator_entry(_by_id(out["elements"], element_id))
        assert entry and entry_resolves(page, entry), (element_id, entry)
        assert resolve_entry(page, entry).get_attribute("id") == element_id
    page.close()


def test_aria_widget_constraints_come_from_aria(server, browser):
    page, out = _extract(browser, server.url("/widgets.html"))
    spin = _by_id(out["elements"], "spin")["constraints"]
    assert spin["source"] == "aria" and spin["min"] == "1" and spin["max"] == "5"
    assert spin["aria_required"] is True and spin["effective_required"] is True
    date = _by_id(out["elements"], "d")["constraints"]
    assert (date["type"], date["min"], date["max"]) == ("date", "2026-01-01", "2026-12-31")
    rng = _by_id(out["elements"], "r")["constraints"]
    assert (rng["min"], rng["max"], rng["step"]) == ("0", "100", "5")
    f = _by_id(out["elements"], "f")["constraints"]
    assert f["accept"] == ".png,.jpg" and f["multiple"] is True
    page.close()


# ── shadow DOM ───────────────────────────────────────────────────────────

def test_open_shadow_roots_are_walked_and_closed_ones_reported(server, browser):
    page, out = _extract(browser, server.url("/shadow.html"))
    els = out["elements"]
    q = _by_id(els, "q")
    assert q.get("shadow") is True and q["technical_locators"]["xpath"] is None
    assert q["constraints"]["required"] is True and q["constraints"]["maxlength"] == 40
    nested = _by_id(els, "nested")
    assert nested.get("shadow") is True
    assert not any((e["attribute_locators"] or {}).get("id") == "hidden-from-scripts" for e in els)
    assert out["scan"]["shadow_roots"] == 2
    assert any("closed shadow" in lim for lim in out["scan"]["limitations"])
    # the host-prefixed CSS fallback pierces the shadow root and is unique
    assert page.locator(q["technical_locators"]["css"]).count() == 1
    assert page.locator(nested["technical_locators"]["css"]).count() == 1
    # and the semantic entry resolves (Playwright's getBy* pierce open roots)
    assert entry_resolves(page, _best_locator_entry(q))
    page.close()


# ── frames ───────────────────────────────────────────────────────────────

def test_all_frames_are_extracted_with_a_frame_path(server, browser):
    page, out = _extract(browser, server.url("/frames.html"))
    els = out["elements"]
    card = _by_id(els, "card")
    assert card["frame"]["path"] == ["#payment"] and card["frame"]["url"].endswith("/frame_child.html")
    assert card["constraints"]["maxlength"] == 19 and card["constraints"]["inputmode"] == "numeric"
    deep = _by_id(els, "deep-confirm")
    assert deep["frame"]["path"] == ["#payment", "#nested-frame"]
    inline = _by_id(els, "srcdoc-btn")
    assert inline["frame"]["path"] == ['iframe[name="inline"]']
    assert "frame" not in _by_id(els, "top-pay")
    assert out["scan"]["frames_scanned"] == 4
    for el in (card, deep, inline):
        entry = _best_locator_entry(el)
        assert entry["frame"] == el["frame"]["path"]
        assert entry_resolves(page, entry)
        assert resolve_entry(page, entry).get_attribute("id") == (el["attribute_locators"] or {})["id"]
    page.close()


def test_frames_on_hosts_outside_the_allow_list_are_skipped(server, browser):
    page, out = _extract(browser, server.url("/frames.html"))
    page.close()
    page = browser.new_page()
    page.goto(server.url("/frames.html"))
    page.wait_for_load_state("networkidle")
    blocked = extract_page(page, DiscoveryConfig(deep=True), url_allowed=lambda u: "frame_child" not in u)
    assert {s["reason"] for s in blocked["scan"]["frames_skipped"]} == {"host_not_allowed"}
    assert not any((e["attribute_locators"] or {}).get("id") == "card" for e in blocked["elements"])
    page.close()


def test_frames_can_be_switched_off(server, browser):
    page, out = _extract(browser, server.url("/frames.html"), capture={"frames": False})
    assert out["scan"]["frames_scanned"] == 1
    assert not any(e.get("frame") for e in out["elements"])
    page.close()


# ── duplicate names → container-scoped locators ─────────────────────────

def test_duplicate_buttons_in_different_dialogs_get_verified_scoped_locators(server, browser):
    page, out = _extract(browser, server.url("/dialogs.html"))
    els = out["elements"]
    for element_id, container in (("save-edit", ("dialog", "Edit user")), ("save-create", ("dialog", "Create user")),
                                  ("sub-1", ("form", "Newsletter")), ("sub-2", ("form", "Feedback"))):
        el = _by_id(els, element_id)
        scoped = next(c for c in el["locator_candidates"] if c["type"] == "scoped_role")
        assert (scoped["value"]["container"]["role"], scoped["value"]["container"]["name"]) == container
        # a unique id (140) still outranks the scoped candidate (105) as the *recommended* locator …
        assert el["recommended_locator"]["type"] == "id"
        # … but the locator_map entry (role-first chain) uses the verified scope instead of the bare role
        entry = _best_locator_entry(el)
        assert entry["scope"]["locator"] == container[0] and entry["scope"]["name"] == container[1]
        assert entry_resolves(page, entry)                                  # count() == 1
        assert resolve_entry(page, entry).get_attribute("id") == element_id  # and it is the right element
    assert out["scan"]["scoped_verified"] >= 6
    page.close()


def test_nav_and_footer_links_with_the_same_name_are_scoped_by_landmark(server, browser):
    page, out = _extract(browser, server.url("/dialogs.html"))
    homes = [e for e in out["elements"] if e.get("display_text") == "Home"]
    assert len(homes) == 2
    roles = sorted(next(c for c in e["locator_candidates"] if c["type"] == "scoped_role")["value"]["container"]["role"]
                   for e in homes)
    assert roles == ["contentinfo", "navigation"]
    for e in homes:
        assert entry_resolves(page, _best_locator_entry(e))
    page.close()


def test_duplicates_without_a_named_container_fall_back_to_a_non_role_locator(server, browser):
    page, out = _extract(browser, server.url("/dialogs.html"))
    for element_id in ("unnamed-1", "unnamed-2"):
        el = _by_id(out["elements"], element_id)
        assert not any(c["type"] == "scoped_role" for c in el["locator_candidates"])
        role = next(c for c in el["locator_candidates"] if c["type"] == "role")
        assert role["unique"] is False                     # the legacy demotion still applies
        entry = _best_locator_entry(el)
        assert entry["type"] != "role" and entry_resolves(page, entry)
        assert resolve_entry(page, entry).get_attribute("id") == element_id
    page.close()


# ── constraints (2.2) ────────────────────────────────────────────────────

def test_every_declared_constraint_is_captured(server, browser):
    page, out = _extract(browser, server.url("/constraints.html"))
    els = out["elements"]
    email = _by_id(els, "email")["constraints"]
    assert (email["type"], email["required"], email["autocomplete"], email["aria_invalid"]) == ("email", True, "email", "false")
    assert [d["id"] for d in email["error_container"]["describedby"]] == ["email-help", "email-err"]
    assert email["error_container"]["describedby"][0]["text"] == "We never share it."
    assert email["form"] == {"id": "signup", "name": None, "novalidate": True, "method": "post", "action": "/signup"}
    user = _by_id(els, "username")["constraints"]
    assert (user["minlength"], user["maxlength"], user["pattern"], user["default_value"]) == (3, 20, "[a-z0-9_]+", "guest")
    assert user["error_container"]["errormessage"]["text"] == "Lower-case letters, digits and _ only"
    age = _by_id(els, "age")["constraints"]
    assert (age["type"], age["min"], age["max"], age["step"], age["inputmode"]) == ("number", "18", "120", "1", "numeric")
    price = _by_id(els, "price")["constraints"]
    assert price["readonly"] is True and price["inputmode"] == "decimal" and price["default_value"] == "9.99"
    assert _by_id(els, "code")["constraints"]["disabled"] is True
    avatar = _by_id(els, "avatar")["constraints"]
    assert (avatar["accept"], avatar["multiple"]) == ("image/png,.jpg", True)
    country = _by_id(els, "country")["constraints"]
    assert country["required"] is True and country["default_value"] == "fr"
    assert country["options"] == [
        {"value": "", "text": "Choose", "disabled": False, "selected": False},
        {"value": "de", "text": "Germany", "disabled": True, "selected": False},
        {"value": "fr", "text": "France", "disabled": False, "selected": True},
        {"value": "it", "text": "Italy", "disabled": False, "selected": False},
    ]
    city = _by_id(els, "city")["constraints"]
    assert [o["value"] for o in city["options"]] == ["Paris", "Rome"]
    radios = [e for e in els if (e["attribute_locators"] or {}).get("name") == "size"]
    group = radios[0]["constraints"]["radio_group"]
    assert group["name"] == "size" and [m["value"] for m in group["members"]] == ["s", "m"]
    assert [m["checked"] for m in group["members"]] == [False, True]
    terms = _by_id(els, "terms")["constraints"]
    assert terms["required"] is True and terms["default_checked"] is False
    bio = _by_id(els, "bio")["constraints"]
    assert (bio["type"], bio["maxlength"], bio["default_value"]) == ("textarea", 500, "Hello")
    # non-controls carry no constraints
    assert "constraints" not in next(e for e in els if e.get("display_text") == "Create account")
    page.close()


def test_extraction_is_one_batched_call_and_fast(server, browser):
    page, out = _extract(browser, server.url("/widgets.html"))
    assert out["scan"]["duration_s"] < 2.0
    assert out["scan"]["element_count"] == len(out["elements"]) > 20
    page.close()
