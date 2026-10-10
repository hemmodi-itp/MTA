"""
Unit tests for the Buggy Shop benchmark app (benchmarks/apps/buggy_shop).

For each of the 22 seeded bugs: correct behaviour with the flag off, buggy
behaviour with the flag on. Plus ground-truth consistency (bugs.yaml <-> bugs.py
<-> brd.md) and the MTA project template.
"""

import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

import benchmarks.apps.buggy_shop.app as shop
from benchmarks.apps.buggy_shop.bugs import ALL_BUGS, enabled_bugs, is_on

pytestmark = pytest.mark.mta  # no legacy agent stack needed

SHOP_DIR = Path(shop.__file__).resolve().parent
PASSWORDS = {"alice": "alice-pass-1", "admin": "admin-pass-1"}
ON_OFF = pytest.mark.parametrize("on", [False, True], ids=["off", "on"])


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    for b in ALL_BUGS:
        monkeypatch.delenv(b, raising=False)
    monkeypatch.delenv("BUGS", raising=False)


def _flag(monkeypatch, bug_id: str, on: bool) -> None:
    if on:
        monkeypatch.setenv(bug_id, "1")
    else:
        monkeypatch.delenv(bug_id, raising=False)


def _client(user: str | None = "alice") -> TestClient:
    c = TestClient(shop.create_app(), raise_server_exceptions=False)
    if user:
        r = c.post("/login", data={"username": user, "password": PASSWORDS[user]})
        assert r.status_code == 200 and r.url.path == "/products"
    return c


def _store(c: TestClient):
    return c.app.state.store


def _new_product(c, **kw):
    data = {"name": "Test Item", "price": "5.00", "category": "Books", "description": ""}
    data.update(kw)
    return c.post("/products", data=data, follow_redirects=False)


def _cart_total(html: str) -> str:
    m = re.search(r'id="cart-total"[^>]*>\$(-?[\d.]+)<', html)
    assert m, "cart total not found"
    return m.group(1)


# ── flag registry ────────────────────────────────────────────────────────────

def test_all_bugs_off_by_default():
    assert enabled_bugs() == []
    assert not any(is_on(b) for b in ALL_BUGS)


def test_flag_forms(monkeypatch):
    monkeypatch.setenv("BUG_07", "1")
    assert enabled_bugs() == ["BUG_07"]
    monkeypatch.delenv("BUG_07")
    monkeypatch.setenv("BUGS", "BUG_01, bug_07")
    assert enabled_bugs() == ["BUG_01", "BUG_07"]
    monkeypatch.setenv("BUGS", "all")
    assert enabled_bugs() == list(ALL_BUGS) and len(ALL_BUGS) == 22


# ── baseline correct behaviour ───────────────────────────────────────────────

def test_login_required_redirects_with_next():
    c = _client(None)
    r = c.get("/products?category=Books", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login?next=%2Fproducts%3Fcategory%3DBooks"
    assert c.get("/api/products").status_code == 401
    assert c.get("/help").status_code == 200
    assert c.get("/api/health").json()["status"] == "ok"
    assert c.get("/", follow_redirects=False).headers["location"] == "/products"


def test_login_next_redirect_and_pagination():
    c = _client(None)
    r = c.post("/login", data={"username": "alice", "password": "alice-pass-1", "next": "/cart"})
    assert r.url.path == "/cart"
    html = c.get("/products").text
    assert html.count('data-testid="product-item"') == 5
    assert "Page 1 of 5" in html and 'id="prev-page"' not in html
    last = c.get("/products?page=5").text
    assert last.count('data-testid="product-item"') == 3 and 'id="next-page"' not in last


def test_seed_is_deterministic():
    a, b = _store(_client(None)), _store(_client(None))
    assert len(a.products) == 23
    assert [(p.name, p.price) for p in a.products.values()] == [(p.name, p.price) for p in b.products.values()]
    assert {p.category for p in a.products.values()} == {"Books", "Electronics", "Home"}
    assert a.orders[1].owner == "admin" and a.orders[2].owner == "alice"


def test_checkout_happy_path_creates_order():
    c = _client()
    c.post("/cart/add", data={"product_id": 4, "quantity": "2"})
    r = c.post("/checkout")
    assert r.url.path == "/orders/3"
    assert "Thank you! Your order #3 has been placed." in r.text
    assert "$19.98" in r.text
    assert "Your cart is empty" in c.get("/cart").text


def test_edit_product_validates_and_updates():
    c = _client()
    r = c.post("/products/1/edit", data={"name": "", "price": "1", "category": "Books"})
    assert r.status_code == 400 and "Name is required" in r.text
    r = c.post("/products/1/edit", data={"name": "Renamed", "price": "1.50", "category": "Home"})
    assert r.url.path == "/products/1" and "Renamed" in r.text and "Product updated" in r.text


# ── the 22 seeded bugs ───────────────────────────────────────────────────────

@ON_OFF
def test_bug01_name_exactly_50(monkeypatch, on):
    _flag(monkeypatch, "BUG_01", on)
    c = _client()
    r = _new_product(c, name="N" * 50)
    if on:
        assert r.status_code == 400 and "Name must be at most 50 characters" in r.text
    else:
        assert r.status_code == 303
    assert ("NAME_STRICT = true" if on else "NAME_STRICT = false") in c.get("/products/new").text
    r51 = _new_product(c, name="M" * 51)
    assert r51.status_code == 400 and "Name must be at most 50 characters" in r51.text


@ON_OFF
def test_bug02_negative_price_server_side(monkeypatch, on):
    _flag(monkeypatch, "BUG_02", on)
    c = _client()
    r = c.post("/api/products", json={"name": "Neg", "price": -1, "category": "Books"})
    if on:
        assert r.status_code == 201 and r.json()["price"] == -1.0
    else:
        assert r.status_code == 422 and "Price must be zero or more" in r.json()["errors"]
    # client-side JS rejects negatives either way
    assert "parseFloat(price) < 0" in c.get("/products/new").text


@ON_OFF
def test_bug03_total_rounding(monkeypatch, on):
    _flag(monkeypatch, "BUG_03", on)
    c = _client()
    c.post("/cart/add", data={"product_id": 5, "quantity": "1"})  # Gel Pen 1.005
    assert _cart_total(c.get("/cart").text) == ("1.00" if on else "1.01")

    c2 = _client()
    c2.post("/cart/add", data={"product_id": 3, "quantity": "1"})  # Atlas 19.95
    c2.post("/cart/discount", data={"code": "SAVE10"})
    assert _cart_total(c2.get("/cart").text) == ("17.95" if on else "17.96")


@ON_OFF
def test_bug04_order_ownership(monkeypatch, on):
    _flag(monkeypatch, "BUG_04", on)
    c = _client("alice")
    page, api = c.get("/orders/1"), c.get("/api/orders/1")
    if on:
        assert page.status_code == 200 and "Order #1" in page.text
        assert api.status_code == 200 and api.json()["owner"] == "admin"
    else:
        assert page.status_code == 403 and "Access denied" in page.text
        assert api.status_code == 403 and api.json()["detail"] == "Access denied"
    assert c.get("/orders/2").status_code == 200  # own order always visible
    assert _client("admin").get("/orders/2").status_code == 200  # admin sees all


@ON_OFF
def test_bug05_stored_xss(monkeypatch, on):
    _flag(monkeypatch, "BUG_05", on)
    c = _client()
    payload = "<script>alert('xss')</script>"
    r = _new_product(c, name="XSS Probe", description=payload)
    html = c.get(r.headers["location"]).text
    if on:
        assert payload in html
    else:
        assert payload not in html
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html


@ON_OFF
def test_bug06_footer_help_link(monkeypatch, on):
    _flag(monkeypatch, "BUG_06", on)
    c = _client()
    m = re.search(r'id="footer-help-link"[^>]*href="([^"]+)"', c.get("/products").text)
    assert m and m.group(1) == ("/helpp" if on else "/help")
    assert c.get(m.group(1)).status_code == (404 if on else 200)


@ON_OFF
def test_bug07_percent_search(monkeypatch, on):
    _flag(monkeypatch, "BUG_07", on)
    c = _client()
    page, api = c.get("/products", params={"q": "50%"}), c.get("/api/products", params={"q": "%"})
    if on:
        assert page.status_code == 500 and api.status_code == 500
    else:
        assert page.status_code == 200 and "No products found" in page.text
        assert api.status_code == 200 and api.json()["total"] == 0
    assert c.get("/products", params={"q": "pen"}).status_code == 200


@ON_OFF
def test_bug08_password_label(monkeypatch, on):
    _flag(monkeypatch, "BUG_08", on)
    html = _client(None).get("/login").text
    assert '<label for="username">Username</label>' in html
    assert ('<label for="password">' in html) is (not on)
    assert 'id="password"' in html


@ON_OFF
def test_bug09_slow_product_list(monkeypatch, on):
    _flag(monkeypatch, "BUG_09", on)
    calls = []
    monkeypatch.setattr(shop, "_sleep", lambda s: calls.append(s))
    c = _client()  # login lands on /products, which also hits the delay
    calls.clear()
    assert c.get("/products").status_code == 200
    assert c.get("/api/products").status_code == 200
    assert calls == ([3.5, 3.5] if on else [])


@ON_OFF
def test_bug10_checkout_empty_cart(monkeypatch, on):
    _flag(monkeypatch, "BUG_10", on)
    c = _client()
    before = len(_store(c).orders)
    r = c.post("/checkout", follow_redirects=False)
    get_html = c.get("/checkout").text
    if on:
        assert r.status_code == 303 and r.headers["location"] == "/orders/3"
        assert len(_store(c).orders) == before + 1
        assert 'id="place-order"' in get_html
    else:
        assert r.status_code == 400 and "Your cart is empty" in r.text
        assert len(_store(c).orders) == before
        assert "Your cart is empty" in get_html and 'id="place-order"' not in get_html


@ON_OFF
def test_bug11_logout_invalidates_session(monkeypatch, on):
    _flag(monkeypatch, "BUG_11", on)
    c = _client()
    old_sid = c.cookies.get("sid")
    r = c.get("/logout", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert c.cookies.get("sid") is None  # cookie cleared client-side either way
    c.cookies.set("sid", old_sid)
    r = c.get("/products", follow_redirects=False)
    if on:
        assert r.status_code == 200
    else:
        assert r.status_code == 303 and r.headers["location"].startswith("/login")


@ON_OFF
def test_bug12_double_submit(monkeypatch, on):
    _flag(monkeypatch, "BUG_12", on)
    c = _client()
    _new_product(c, name="Twice", price="7.00")
    _new_product(c, name="Twice", price="7.00")
    count = sum(1 for p in _store(c).products.values() if p.name == "Twice")
    assert count == (2 if on else 1)
    a = c.post("/api/products", json={"name": "ApiTwice", "price": "3.00", "category": "Home"})
    b = c.post("/api/products", json={"name": "ApiTwice", "price": "3.00", "category": "Home"})
    assert a.status_code == 201
    if on:
        assert b.status_code == 201 and b.json()["id"] != a.json()["id"]
    else:
        assert b.status_code == 200 and b.json()["id"] == a.json()["id"]
    assert ("DISABLE_ON_SUBMIT = false" if on else "DISABLE_ON_SUBMIT = true") in c.get("/products/new").text


@ON_OFF
def test_bug13_wrong_password_message(monkeypatch, on):
    _flag(monkeypatch, "BUG_13", on)
    c = _client(None)
    r = c.post("/login", data={"username": "alice", "password": "nope"})
    assert r.status_code == 401
    if on:
        assert "Unknown user" in r.text and "Invalid username or password" not in r.text
    else:
        assert "Invalid username or password" in r.text and "Unknown user" not in r.text
    r2 = c.post("/login", data={"username": "nobody", "password": "x"})
    assert "Invalid username or password" in r2.text


@ON_OFF
def test_bug14_price_sort_stability(monkeypatch, on):
    _flag(monkeypatch, "BUG_14", on)
    c = _client()
    asc = [p["id"] for p in c.get("/api/products", params={"sort": "price_asc"}).json()["items"]]
    assert asc == ([5, 19, 20, 14, 9] if on else [5, 19, 4, 9, 14])
    html = c.get("/products", params={"sort": "price_asc"}).text
    ids = [int(x) for x in re.findall(r'data-product-id="(\d+)"', html)]
    assert ids == asc


@ON_OFF
def test_bug15_pagination_keeps_filter(monkeypatch, on):
    _flag(monkeypatch, "BUG_15", on)
    c = _client()
    html = c.get("/products", params={"category": "Electronics"}).text
    m = re.search(r'id="next-page"[^>]*href="([^"]+)"', html)
    assert m
    assert ("category=Electronics" in m.group(1)) is (not on)
    page2 = c.get(m.group(1).replace("&amp;", "&")).text
    ids = [int(x) for x in re.findall(r'data-product-id="(\d+)"', page2)]
    cats = {_store(c).products[i].category for i in ids}
    assert (cats == {"Electronics"}) is (not on)


@ON_OFF
def test_bug16_admin_role(monkeypatch, on):
    _flag(monkeypatch, "BUG_16", on)
    r = _client("alice").get("/admin")
    if on:
        assert r.status_code == 200 and 'id="user-table"' in r.text
    else:
        assert r.status_code == 403 and "Access denied" in r.text
    assert _client("admin").get("/admin").status_code == 200


@ON_OFF
def test_bug17_exe_upload(monkeypatch, on):
    _flag(monkeypatch, "BUG_17", on)
    c = _client()
    r = c.post("/upload", files={"file": ("evil.exe", b"MZ\x90\x00", "application/octet-stream")})
    if on:
        assert r.status_code == 200 and "Uploaded evil.exe" in r.text
    else:
        assert r.status_code == 400 and "Only CSV or PNG files are allowed" in r.text
    ok = c.post("/upload", files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")})
    assert ok.status_code == 200 and "Uploaded data.csv" in ok.text
    txt = c.post("/upload", files={"file": ("notes.txt", b"hi", "text/plain")})
    assert txt.status_code == 400 and "Only CSV or PNG files are allowed" in txt.text
    big = c.post("/upload", files={"file": ("big.png", b"0" * (1024 * 1024 + 1), "image/png")})
    assert big.status_code == 400 and "File must be 1 MB or smaller" in big.text
    edge = c.post("/upload", files={"file": ("edge.png", b"0" * (1024 * 1024), "image/png")})
    assert edge.status_code == 200 and "Uploaded edge.png" in edge.text
    assert 'accept=".csv,.png"' in c.get("/upload").text


@ON_OFF
def test_bug18_empty_name(monkeypatch, on):
    _flag(monkeypatch, "BUG_18", on)
    c = _client()
    r = _new_product(c, name="   ")
    if on:
        assert r.status_code == 303
    else:
        assert r.status_code == 400 and "Name is required" in r.text
    form = c.get("/products/new").text
    assert ("REQUIRE_NAME = false" if on else "REQUIRE_NAME = true") in form
    assert ('id="name" data-testid="name" name="name" type="text" value="" required' in form) is (not on)


@ON_OFF
def test_bug19_case_insensitive_search(monkeypatch, on):
    _flag(monkeypatch, "BUG_19", on)
    c = _client()
    ids = [p["id"] for p in c.get("/api/products", params={"q": "mouse"}).json()["items"]]
    assert ids == ([] if on else [8])
    assert [p["id"] for p in c.get("/api/products", params={"q": "Mouse"}).json()["items"]] == [8]
    assert ("No products found" in c.get("/products", params={"q": "DATA"}).text) is on


@ON_OFF
def test_bug20_delete_persists(monkeypatch, on):
    _flag(monkeypatch, "BUG_20", on)
    c = _client()
    r = c.post("/products/3/delete")
    assert r.url.path == "/products" and "Product deleted" in r.text
    detail = c.get("/products/3")
    if on:
        assert detail.status_code == 200
    else:
        assert detail.status_code == 404 and "Product not found" in detail.text


@ON_OFF
def test_bug21_quantity_bounds(monkeypatch, on):
    _flag(monkeypatch, "BUG_21", on)
    c = _client()
    r = c.post("/cart/add", data={"product_id": 4, "quantity": "0"}, follow_redirects=False)
    if on:
        assert r.status_code == 303
        assert _cart_total(c.get("/cart").text) == "0.00"
        c.post("/cart/update", data={"product_id": 4, "quantity": "-2"})
        assert _cart_total(c.get("/cart").text) == "-19.98"
    else:
        assert r.status_code == 400 and "Quantity must be between 1 and 99" in r.text
        c.post("/cart/add", data={"product_id": 4, "quantity": "1"})
        up = c.post("/cart/update", data={"product_id": 4, "quantity": "-2"})
        assert up.status_code == 400 and "Quantity must be between 1 and 99" in up.text
        assert _cart_total(c.get("/cart").text) == "9.99"
    hi = c.post("/cart/add", data={"product_id": 9, "quantity": "100"})
    assert hi.status_code == 400 and "Quantity must be between 1 and 99" in hi.text


@ON_OFF
def test_bug22_discount_twice(monkeypatch, on):
    _flag(monkeypatch, "BUG_22", on)
    c = _client()
    c.post("/cart/add", data={"product_id": 16, "quantity": "1"})  # 45.00
    first = c.post("/cart/discount", data={"code": "SAVE10"})
    assert "Discount applied" in first.text and _cart_total(first.text) == "40.50"
    second = c.post("/cart/discount", data={"code": "SAVE10"})
    if on:
        assert second.status_code == 200 and _cart_total(second.text) == "36.00"
    else:
        assert second.status_code == 400 and "Discount already applied" in second.text
        assert _cart_total(second.text) == "40.50"
    bad = c.post("/cart/discount", data={"code": "BOGUS"})
    assert "Invalid discount code" in bad.text


def test_all_bugs_on_together(monkeypatch):
    """Smoke: with BUGS=all every page still renders (no bug breaks another)."""
    monkeypatch.setenv("BUGS", "all")
    monkeypatch.setattr(shop, "_sleep", lambda s: None)
    c = _client()
    for path in ("/products", "/products/new", "/products/1", "/cart", "/checkout", "/upload", "/admin",
                 "/orders/1", "/help", "/api/products"):
        assert c.get(path).status_code == 200, path


# ── ground truth + manifest consistency ─────────────────────────────────────

def _bugs_yaml() -> list[dict]:
    return yaml.safe_load((SHOP_DIR / "bugs.yaml").read_text(encoding="utf-8"))["bugs"]


def test_bugs_yaml_matches_registry():
    bugs = _bugs_yaml()
    ids = [b["id"] for b in bugs]
    assert len(ids) == 22 and len(set(ids)) == 22
    assert set(ids) == set(ALL_BUGS)
    for b in bugs:
        assert b["flag"] == b["id"]
        assert b["severity"] in {"critical", "high", "medium", "low"}
        for key in ("title", "category", "affected_ac", "how_detectable"):
            assert b.get(key), (b["id"], key)


def test_every_affected_ac_is_in_brd():
    brd = (SHOP_DIR / "brd.md").read_text(encoding="utf-8")
    defined = set(re.findall(r"^- (AC-\d{2}\.\d+):", brd, flags=re.MULTILINE))
    for b in _bugs_yaml():
        assert b["affected_ac"] in defined, b["id"]
    assert re.search(r"^### REQ-01 ", brd, flags=re.MULTILINE)


def test_brd_messages_match_app():
    brd = (SHOP_DIR / "brd.md").read_text(encoding="utf-8")
    for msg in (shop.MSG_INVALID_LOGIN, shop.MSG_NAME_REQUIRED, shop.MSG_NAME_TOO_LONG, shop.MSG_PRICE_NEGATIVE,
                shop.MSG_UPLOAD_TYPE, shop.MSG_QUANTITY, shop.MSG_DISCOUNT_ALREADY, shop.MSG_CART_EMPTY,
                shop.MSG_ACCESS_DENIED, shop.MSG_PRODUCT_DELETED, shop.MSG_UPLOAD_SIZE):
        assert f'"{msg}"' in brd, msg


def test_project_template_renders():
    tmpl = (SHOP_DIR / "mta_project" / "project.yaml.tmpl").read_text(encoding="utf-8")
    rendered = tmpl.replace("{{BASE_URL}}", "http://127.0.0.1:8765").replace("{{PROJECT_NAME}}", "bench_shop")
    assert "{{" not in rendered
    cfg = yaml.safe_load(rendered)
    assert cfg["project"]["name"] == "bench_shop"
    assert cfg["project"]["application_name"] == "Buggy Shop"
    assert cfg["project"]["headless"] is True and cfg["project"]["discovery_timeout_s"] == 180
    assert cfg["input"]["brd_dir"] == "application_assets/projects/bench_shop/inputs"
    assert cfg["environment"] == "local"
    assert cfg["safety"] == {"allow_destructive": True, "allow_security_probes": True,
                             "allowed_hosts": ["127.0.0.1", "localhost"]}
    assert cfg["contracts"] == {"enforce": "block"}
    assert cfg["test_execution"]["suite"] == "bench_shop"
    mods = {m["id"]: m for m in cfg["modules"]}
    assert list(mods) == ["M01", "M02", "M03", "M04", "M05", "M06"]
    assert mods["M01"]["url"] == "http://127.0.0.1:8765/login" and "setup" not in mods["M01"]
    # one BRD per module, split from brd.md by tools/benchmark/materialize.py
    assert all(m["brd_file"] == f"brd_{mid}.md" for mid, m in mods.items())
    for mid, user in (("M02", "alice"), ("M03", "alice"), ("M04", "alice"), ("M05", "alice"), ("M06", "admin")):
        steps = mods[mid]["setup"]
        assert steps[0] == {"goto": "http://127.0.0.1:8765/login"}
        assert steps[1] == {"fill": {"selector": "#username", "value": user}}
        assert steps[2] == {"fill": {"selector": "#password", "value": PASSWORDS[user]}}
        assert steps[3] == {"click": "#login-button"} and steps[4] == {"wait": 500}


def test_setup_steps_work_against_app():
    """The ids used by the template's setup steps exist on the login page."""
    html = _client(None).get("/login").text
    for sel in ('id="username"', 'id="password"', 'id="login-button"'):
        assert sel in html
