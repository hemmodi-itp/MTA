"""Phase 2 design R1/R4 — the batched deep extractor reproduces the legacy scanner's fields.

For every element the legacy scanner finds (classic selectors, light DOM), the deep extractor must
produce the same legacy fields (display_text, semantic/attribute/playwright/technical locators,
recommended locator, candidates, quality, intent hints) and the same `tag`, so the element keeps its
identity — and therefore its LOC- id — when a project turns `discovery.deep` on.

Runs on the classic fixture page and on the real buggy_shop pages (bug-free, started locally).
"""

import os
import socket
import sys

import pytest

pytest.importorskip("playwright.sync_api")

sys.path.insert(0, os.path.dirname(__file__))
from _deep_fixture_server import FixtureServer  # noqa: E402

from tools.discovery.deep.config import DiscoveryConfig  # noqa: E402
from tools.discovery.dom_scan import _MERGE_COMPARE_FIELDS, _identity_parts_with_frame  # noqa: E402
from tools.playwright_scanner import PlaywrightScanner  # noqa: E402

DEEP = DiscoveryConfig(deep=True).model_dump()


def _without_scoped(el):
    """Deep-only scoped candidates removed (they exist only for duplicated role names)."""
    el = dict(el)
    cands = [c for c in el.get("locator_candidates") or [] if c.get("type") != "scoped_role"]
    el["locator_candidates"] = cands
    if (el.get("recommended_locator") or {}).get("type") == "scoped_role":
        el["recommended_locator"] = cands[0] if cands else el["recommended_locator"]
    return el


def _compare(url, setup=None):
    legacy = PlaywrightScanner().scan_page(url, setup_steps=setup)["elements"]
    deep = PlaywrightScanner().scan_page(url, setup_steps=setup, deep_config=DEEP)["elements"]
    deep_by_css = {e["technical_locators"]["css"]: e for e in deep if not e.get("frame") and not e.get("shadow")}
    assert legacy, "legacy scan found nothing"
    diffs = []
    for old in legacy:
        css = old["technical_locators"]["css"]
        new = deep_by_css.get(css)
        if new is None:
            diffs.append((css, "missing in deep scan"))
            continue
        new = _without_scoped(new)
        assert new["capture_reason"] == "classic" or new["capture_reason"].startswith("input:")
        for field in ("tag",) + _MERGE_COMPARE_FIELDS:
            if old.get(field) != new.get(field):
                diffs.append((css, field, old.get(field), new.get(field)))
        if _identity_parts_with_frame(old) != _identity_parts_with_frame(new):
            diffs.append((css, "identity"))
    return legacy, deep, diffs


@pytest.fixture(scope="module")
def fixture_server():
    srv = FixtureServer().start()
    yield srv
    srv.stop()


def test_classic_fixture_page_parity(fixture_server):
    legacy, deep, diffs = _compare(fixture_server.url("/classic.html"))
    assert diffs == []
    # the deep scan finds everything the legacy one did, plus the wider set
    assert len(deep) >= len(legacy)
    assert {e["capture_reason"] for e in deep if e["capture_reason"] not in ("classic",)} >= {"summary", "details"}


def test_classic_fixture_visibility_and_enabled_match_playwright(fixture_server):
    legacy, _, _ = _compare(fixture_server.url("/classic.html"))
    q = {(e["attribute_locators"] or {}).get("id") or e["technical_locators"]["css"]: e["quality"] for e in legacy}
    # sanity: the fixture really exercises the tricky cases
    assert q["gone"] == {"visible": False, "enabled": True}
    assert q["ghost"]["visible"] is False
    assert q["in-disabled-fieldset"]["enabled"] is False
    assert q["legend-btn"]["enabled"] is True          # inside the legend: not disabled by the fieldset
    assert q["aria-off"]["enabled"] is False           # aria-disabled


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def buggy_shop():
    pytest.importorskip("fastapi")
    from tools.benchmark.app_server import AppServer
    from tools.benchmark.apps import APPS

    srv = AppServer(APPS["buggy_shop"], port=_free_port()).start()
    yield srv.base_url
    srv.stop()


def _login(base, user="alice", password="alice-pass-1"):
    return [{"goto": f"{base}/login"}, {"fill": {"selector": "#username", "value": user}},
            {"fill": {"selector": "#password", "value": password}}, {"click": "#login-button"}, {"wait": 300}]


@pytest.mark.parametrize("path,who", [
    ("/login", None), ("/products", "alice"), ("/products/new", "alice"), ("/products/1", "alice"),
    ("/cart", "alice"), ("/upload", "alice"), ("/admin", "admin"),
])
def test_buggy_shop_page_parity(buggy_shop, path, who):
    setup = None
    if who == "alice":
        setup = _login(buggy_shop)
    elif who == "admin":
        setup = _login(buggy_shop, "admin", "admin-pass-1")
    _, _, diffs = _compare(buggy_shop + path, setup)
    assert diffs == []
