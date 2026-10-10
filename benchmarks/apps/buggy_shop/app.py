"""
app.py — Buggy Shop: a small local web shop with 22 seeded, flag-controlled bugs.

Benchmark target for MTA (see docs/phases/phase-0-design.md §3.1). All bugs are
OFF by default; flags are read per request via bugs.is_on(), so tests can flip
them with monkeypatch.setenv without rebuilding the app.

    python -m benchmarks.apps.buggy_shop --port 8765
"""

import math
import os
import re
import time
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from benchmarks.apps.buggy_shop import templates as T
from benchmarks.apps.buggy_shop.bugs import is_on
from benchmarks.apps.buggy_shop.store import CATEGORIES, DISCOUNT_CODE, DISCOUNT_RATE, Product, Store

# ── exact user-facing messages (kept identical to brd.md) ───────────────────
MSG_INVALID_LOGIN = "Invalid username or password"
MSG_UNKNOWN_USER = "Unknown user"  # BUG_13 only
MSG_NAME_REQUIRED = "Name is required"
MSG_NAME_TOO_LONG = "Name must be at most 50 characters"
MSG_PRICE_REQUIRED = "Price is required"
MSG_PRICE_FORMAT = "Price must be a number with at most 2 decimals"
MSG_PRICE_NEGATIVE = "Price must be zero or more"
MSG_CATEGORY = "Please choose a category"
MSG_DESCRIPTION_TOO_LONG = "Description must be at most 500 characters"
MSG_QUANTITY = "Quantity must be between 1 and 99"
MSG_DISCOUNT_APPLIED = "Discount applied"
MSG_DISCOUNT_ALREADY = "Discount already applied"
MSG_DISCOUNT_INVALID = "Invalid discount code"
MSG_CART_EMPTY = "Your cart is empty"
MSG_ACCESS_DENIED = "Access denied"
MSG_UPLOAD_TYPE = "Only CSV or PNG files are allowed"
MSG_UPLOAD_SIZE = "File must be 1 MB or smaller"
MSG_UPLOAD_NONE = "Please choose a file"
MSG_PRODUCT_CREATED = "Product created"
MSG_PRODUCT_UPDATED = "Product updated"
MSG_PRODUCT_DELETED = "Product deleted"

NAME_MAX = 50
DESCRIPTION_MAX = 500
PAGE_SIZE = 5
DEDUP_WINDOW_S = 5.0
SLOW_DELAY_S = 3.5
UPLOAD_MAX_BYTES = 1024 * 1024
QTY_MIN, QTY_MAX = 1, 99
CENT = Decimal("0.01")
_PRICE_RE = re.compile(r"^-?\d+(\.\d{1,2})?$")


def _sleep(seconds: float) -> None:
    """Indirection so tests can patch the BUG_09 delay away."""
    time.sleep(seconds)


def _money(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_DOWN if is_on("BUG_03") else ROUND_HALF_UP)


# ── domain helpers ───────────────────────────────────────────────────────────

def validate_product(data: dict) -> tuple[dict, list[str]]:
    """Shared server-side validation for the HTML form and POST /api/products."""
    name = str(data.get("name") or "").strip()
    raw_price = data.get("price")
    price_s = "" if raw_price is None or isinstance(raw_price, bool) else str(raw_price).strip()
    category = str(data.get("category") or "").strip()
    description = str(data.get("description") or "")
    errors: list[str] = []

    if not name:
        if not is_on("BUG_18"):
            errors.append(MSG_NAME_REQUIRED)
    elif (len(name) >= NAME_MAX) if is_on("BUG_01") else (len(name) > NAME_MAX):
        errors.append(MSG_NAME_TOO_LONG)

    price: Optional[Decimal] = None
    if not price_s:
        errors.append(MSG_PRICE_REQUIRED)
    elif not _PRICE_RE.match(price_s):
        errors.append(MSG_PRICE_FORMAT)
    else:
        try:
            price = Decimal(price_s)
        except InvalidOperation:
            errors.append(MSG_PRICE_FORMAT)
        else:
            if price < 0 and not is_on("BUG_02"):
                errors.append(MSG_PRICE_NEGATIVE)

    if category not in CATEGORIES:
        errors.append(MSG_CATEGORY)
    if len(description) > DESCRIPTION_MAX:
        errors.append(MSG_DESCRIPTION_TOO_LONG)

    clean = {"name": name, "price": price, "category": category, "description": description}
    return clean, errors


def create_or_dedupe(store: Store, clean: dict) -> tuple[Product, bool]:
    """Returns (product, created). Identical name+price within 5 s is idempotent unless BUG_12."""
    if not is_on("BUG_12"):
        existing = store.find_recent_duplicate(clean["name"], clean["price"], DEDUP_WINDOW_S)
        if existing is not None:
            return existing, False
    p = store.add_product(clean["name"], clean["price"], clean["category"], clean["description"])
    return p, True


def query_products(store: Store, q: str, category: str, sort: str) -> list[Product]:
    if q and "%" in q and is_on("BUG_07"):
        # Simulates an unescaped SQL LIKE pattern blowing up.
        raise RuntimeError(f"malformed LIKE pattern near '%': {q!r}")
    items = sorted(store.products.values(), key=lambda p: p.id)
    if q:
        if is_on("BUG_19"):
            items = [p for p in items if q in p.name]
        else:
            ql = q.lower()
            items = [p for p in items if ql in p.name.lower()]
    if category:
        items = [p for p in items if p.category == category]
    unstable = is_on("BUG_14")
    if sort == "price_asc":
        items = sorted(items, key=(lambda p: (p.price, -p.id)) if unstable else (lambda p: p.price))
    elif sort == "price_desc":
        items = sorted(items, key=(lambda p: (-p.price, -p.id)) if unstable else (lambda p: -p.price))
    elif sort == "name":
        items = sorted(items, key=lambda p: (p.name.lower(), p.id))
    return items


def paginate(items: list, page_raw) -> tuple[list, int, int, int]:
    pages = max(1, math.ceil(len(items) / PAGE_SIZE))
    try:
        page = int(page_raw)
    except (TypeError, ValueError):
        page = 1
    page = min(max(page, 1), pages)
    start = (page - 1) * PAGE_SIZE
    return items[start:start + PAGE_SIZE], page, pages, start


def parse_quantity(raw) -> Optional[int]:
    """Returns the quantity or None if invalid. BUG_21 lets 0 / negatives through."""
    try:
        qty = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if qty > QTY_MAX:
        return None
    if qty < QTY_MIN and not is_on("BUG_21"):
        return None
    return qty


def cart_summary(store: Store, username: str) -> dict:
    cart = store.cart(username)
    lines = []
    subtotal_exact = Decimal("0")
    for pid, qty in cart["items"].items():
        product = store.products.get(pid)
        if product is None:
            continue
        exact = product.price * qty
        subtotal_exact += exact
        lines.append({"product": product, "quantity": qty, "line_total": _money(exact)})
    discounts = cart["discounts"]
    discount_exact = subtotal_exact * DISCOUNT_RATE * discounts
    return {
        "lines": lines,
        "discounts": discounts,
        "subtotal": _money(subtotal_exact),
        "discount": _money(discount_exact),
        "total": _money(subtotal_exact - discount_exact),
    }


def product_json(p: Product) -> dict:
    return {"id": p.id, "name": p.name, "price": float(p.price), "price_display": T.fmt_price(p.price),
            "category": p.category, "description": p.description}


def order_json(o) -> dict:
    return {
        "id": o.id, "owner": o.owner,
        "lines": [{"product_id": ln["product_id"], "name": ln["name"], "quantity": ln["quantity"],
                   "unit_price": float(ln["unit_price"]), "line_total": f"{ln['line_total']:.2f}"}
                  for ln in o.lines],
        "subtotal": f"{o.subtotal:.2f}", "discount": f"{o.discount:.2f}", "total": f"{o.total:.2f}",
    }


# ── app factory ──────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(title="Buggy Shop", docs_url=None, redoc_url=None, openapi_url=None)
    store = Store()
    app.state.store = store

    # -- small request helpers (closures over this app's store) --------------
    def session_of(request: Request) -> tuple[Optional[str], Optional[dict]]:
        sid = request.cookies.get("sid")
        return sid, store.get_session(sid)

    def current_user(request: Request) -> Optional[dict]:
        _, sess = session_of(request)
        if not sess:
            return None
        user = store.users.get(sess["username"])
        return {"username": user.username, "role": user.role} if user else None

    def pop_flash(request: Request) -> Optional[str]:
        _, sess = session_of(request)
        if not sess:
            return None
        msg, sess["flash"] = sess.get("flash"), None
        return msg

    def set_flash(request: Request, msg: str) -> None:
        _, sess = session_of(request)
        if sess is not None:
            sess["flash"] = msg

    def render(request: Request, title: str, body: str, status: int = 200,
               user: Optional[dict] = None) -> HTMLResponse:
        html = T.page(title, body, user=user, flash=pop_flash(request) if user else None,
                      help_href="/helpp" if is_on("BUG_06") else "/help")
        return HTMLResponse(html, status_code=status)

    def to_login(request: Request) -> RedirectResponse:
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(T.login_redirect_target(target), status_code=303)

    def denied(request: Request, user: Optional[dict]) -> HTMLResponse:
        return render(request, MSG_ACCESS_DENIED, T.error_body(MSG_ACCESS_DENIED, MSG_ACCESS_DENIED),
                      403, user)

    def not_found(request: Request, user: Optional[dict], what: str) -> HTMLResponse:
        return render(request, "Not found", T.error_body("Not found", f"{what} not found"), 404, user)

    def api_auth(request: Request) -> tuple[Optional[dict], Optional[JSONResponse]]:
        user = current_user(request)
        if user is None:
            return None, JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return user, None

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api/") or exc.status_code != 404:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        user = current_user(request)
        return HTMLResponse(
            T.page("Page not found", T.error_body("Page not found", "Page not found"), user=user),
            status_code=404,
        )

    # -- auth -----------------------------------------------------------------
    @app.get("/")
    def root():
        return RedirectResponse("/products", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request, next: str = ""):
        body = T.login_body(None, next, "", password_label=not is_on("BUG_08"))
        return render(request, "Log in", body)

    @app.post("/login")
    def login_submit(request: Request, username: str = Form(""), password: str = Form(""),
                     next: str = Form("")):
        user, reason = store.authenticate(username.strip(), password)
        if user is None:
            msg = MSG_UNKNOWN_USER if (reason == "bad_password" and is_on("BUG_13")) else MSG_INVALID_LOGIN
            body = T.login_body(msg, next, username, password_label=not is_on("BUG_08"))
            return render(request, "Log in", body, status=401)
        sid = store.create_session(user.username)
        dest = next if (next.startswith("/") and not next.startswith("//")) else "/products"
        resp = RedirectResponse(dest, status_code=303)
        resp.set_cookie("sid", sid, httponly=True, samesite="lax", path="/")
        return resp

    def _logout(request: Request):
        sid, _ = session_of(request)
        if not is_on("BUG_11"):
            store.destroy_session(sid)
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie("sid", path="/")
        return resp

    app.add_api_route("/logout", _logout, methods=["GET", "POST"])

    # -- products ---------------------------------------------------------------
    @app.get("/products", response_class=HTMLResponse)
    def products(request: Request, q: str = "", category: str = "", sort: str = "", page: str = "1"):
        user = current_user(request)
        if user is None:
            return to_login(request)
        if is_on("BUG_09"):
            _sleep(SLOW_DELAY_S)
        items = query_products(store, q, category, sort)
        page_items, page_no, pages, start = paginate(items, page)

        def href(n: int, keep_category: bool = True) -> str:
            params = {"q": q, "category": category if keep_category else "", "sort": sort, "page": n}
            return "/products?" + urlencode({k: v for k, v in params.items() if v not in ("", None)})

        prev_href = href(page_no - 1) if page_no > 1 else None
        next_href = href(page_no + 1, keep_category=not is_on("BUG_15")) if page_no < pages else None
        body = T.products_body(page_items, q, category, sort, CATEGORIES, page_no, pages, len(items),
                               start, prev_href, next_href)
        return render(request, "Products", body, user=user)

    def _form_page(request: Request, user: dict, action: str, heading: str, values: dict,
                   errors: list[str], status: int = 200) -> HTMLResponse:
        body = T.product_form_body(
            action, heading, values, errors, CATEGORIES, name_max=NAME_MAX,
            name_strict_less=is_on("BUG_01"), require_name=not is_on("BUG_18"),
            disable_on_submit=not is_on("BUG_12"),
        )
        return render(request, heading, body, status, user)

    @app.get("/products/new", response_class=HTMLResponse)
    def new_product_form(request: Request):
        user = current_user(request)
        if user is None:
            return to_login(request)
        return _form_page(request, user, "/products", "Add product", {}, [])

    @app.post("/products")
    def create_product(request: Request, name: str = Form(""), price: str = Form(""),
                       category: str = Form(""), description: str = Form("")):
        user = current_user(request)
        if user is None:
            return to_login(request)
        raw = {"name": name, "price": price, "category": category, "description": description}
        clean, errors = validate_product(raw)
        if errors:
            return _form_page(request, user, "/products", "Add product", raw, errors, 400)
        product, _ = create_or_dedupe(store, clean)
        set_flash(request, MSG_PRODUCT_CREATED)
        return RedirectResponse(f"/products/{product.id}", status_code=303)

    @app.get("/products/{pid}", response_class=HTMLResponse)
    def product_detail(request: Request, pid: int):
        user = current_user(request)
        if user is None:
            return to_login(request)
        p = store.products.get(pid)
        if p is None:
            return not_found(request, user, "Product")
        body = T.product_detail_body(p, raw_description=is_on("BUG_05"), cart_errors=[])
        return render(request, p.name, body, user=user)

    @app.get("/products/{pid}/edit", response_class=HTMLResponse)
    def edit_product_form(request: Request, pid: int):
        user = current_user(request)
        if user is None:
            return to_login(request)
        p = store.products.get(pid)
        if p is None:
            return not_found(request, user, "Product")
        values = {"name": p.name, "price": T.fmt_price(p.price), "category": p.category,
                  "description": p.description}
        return _form_page(request, user, f"/products/{pid}/edit", "Edit product", values, [])

    @app.post("/products/{pid}/edit")
    def edit_product(request: Request, pid: int, name: str = Form(""), price: str = Form(""),
                     category: str = Form(""), description: str = Form("")):
        user = current_user(request)
        if user is None:
            return to_login(request)
        p = store.products.get(pid)
        if p is None:
            return not_found(request, user, "Product")
        raw = {"name": name, "price": price, "category": category, "description": description}
        clean, errors = validate_product(raw)
        if errors:
            return _form_page(request, user, f"/products/{pid}/edit", "Edit product", raw, errors, 400)
        p.name, p.price, p.category, p.description = (clean["name"], clean["price"], clean["category"],
                                                      clean["description"])
        set_flash(request, MSG_PRODUCT_UPDATED)
        return RedirectResponse(f"/products/{pid}", status_code=303)

    @app.post("/products/{pid}/delete")
    def delete_product(request: Request, pid: int):
        user = current_user(request)
        if user is None:
            return to_login(request)
        if pid not in store.products:
            return not_found(request, user, "Product")
        if not is_on("BUG_20"):
            store.delete_product(pid)
        set_flash(request, MSG_PRODUCT_DELETED)
        return RedirectResponse("/products", status_code=303)

    # -- cart / checkout / orders ----------------------------------------------
    def _cart_page(request: Request, user: dict, errors: list[str], status: int = 200) -> HTMLResponse:
        body = T.cart_body(cart_summary(store, user["username"]), errors)
        return render(request, "Cart", body, status, user)

    @app.get("/cart", response_class=HTMLResponse)
    def cart(request: Request):
        user = current_user(request)
        if user is None:
            return to_login(request)
        return _cart_page(request, user, [])

    @app.post("/cart/add")
    def cart_add(request: Request, product_id: int = Form(...), quantity: str = Form("1")):
        user = current_user(request)
        if user is None:
            return to_login(request)
        p = store.products.get(product_id)
        if p is None:
            return not_found(request, user, "Product")
        qty = parse_quantity(quantity)
        items = store.cart(user["username"])["items"]
        new_qty = None if qty is None else items.get(product_id, 0) + qty
        if new_qty is None or new_qty > QTY_MAX:
            body = T.product_detail_body(p, raw_description=is_on("BUG_05"), cart_errors=[MSG_QUANTITY])
            return render(request, p.name, body, 400, user)
        items[product_id] = new_qty
        set_flash(request, f"Added {p.name} to cart")
        return RedirectResponse("/cart", status_code=303)

    @app.post("/cart/update")
    def cart_update(request: Request, product_id: int = Form(...), quantity: str = Form("")):
        user = current_user(request)
        if user is None:
            return to_login(request)
        items = store.cart(user["username"])["items"]
        if product_id not in items:
            return _cart_page(request, user, ["That product is not in your cart"], 400)
        qty = parse_quantity(quantity)
        if qty is None:
            return _cart_page(request, user, [MSG_QUANTITY], 400)
        items[product_id] = qty
        return RedirectResponse("/cart", status_code=303)

    @app.post("/cart/remove")
    def cart_remove(request: Request, product_id: int = Form(...)):
        user = current_user(request)
        if user is None:
            return to_login(request)
        store.cart(user["username"])["items"].pop(product_id, None)
        return RedirectResponse("/cart", status_code=303)

    @app.post("/cart/discount")
    def cart_discount(request: Request, code: str = Form("")):
        user = current_user(request)
        if user is None:
            return to_login(request)
        cart_ = store.cart(user["username"])
        if code.strip().upper() != DISCOUNT_CODE:
            return _cart_page(request, user, [MSG_DISCOUNT_INVALID], 400)
        if cart_["discounts"] >= 1 and not is_on("BUG_22"):
            return _cart_page(request, user, [MSG_DISCOUNT_ALREADY], 400)
        cart_["discounts"] += 1
        set_flash(request, MSG_DISCOUNT_APPLIED)
        return RedirectResponse("/cart", status_code=303)

    def _cart_is_empty(username: str) -> bool:
        return not cart_summary(store, username)["lines"]

    @app.get("/checkout", response_class=HTMLResponse)
    def checkout(request: Request):
        user = current_user(request)
        if user is None:
            return to_login(request)
        empty = _cart_is_empty(user["username"]) and not is_on("BUG_10")
        body = T.checkout_body(cart_summary(store, user["username"]), MSG_CART_EMPTY if empty else None)
        return render(request, "Checkout", body, user=user)

    @app.post("/checkout")
    def place_order(request: Request):
        user = current_user(request)
        if user is None:
            return to_login(request)
        username = user["username"]
        if _cart_is_empty(username) and not is_on("BUG_10"):
            body = T.checkout_body(cart_summary(store, username), MSG_CART_EMPTY)
            return render(request, "Checkout", body, 400, user)
        s = cart_summary(store, username)
        lines = [{"product_id": ln["product"].id, "name": ln["product"].name,
                  "unit_price": ln["product"].price, "quantity": ln["quantity"],
                  "line_total": ln["line_total"]} for ln in s["lines"]]
        order = store.add_order(username, lines, s["subtotal"], s["discount"], s["total"])
        store.clear_cart(username)
        return RedirectResponse(f"/orders/{order.id}", status_code=303)

    def _can_see_order(user: dict, order) -> bool:
        return is_on("BUG_04") or user["role"] == "admin" or order.owner == user["username"]

    @app.get("/orders/{oid}", response_class=HTMLResponse)
    def order_page(request: Request, oid: int):
        user = current_user(request)
        if user is None:
            return to_login(request)
        order = store.orders.get(oid)
        if order is None:
            return not_found(request, user, "Order")
        if not _can_see_order(user, order):
            return denied(request, user)
        return render(request, f"Order #{order.id}", T.order_body(order), user=user)

    # -- upload / admin / help ----------------------------------------------------
    @app.get("/upload", response_class=HTMLResponse)
    def upload_form(request: Request):
        user = current_user(request)
        if user is None:
            return to_login(request)
        return render(request, "Upload", T.upload_body(None, None), user=user)

    @app.post("/upload")
    def upload(request: Request, file: Optional[UploadFile] = File(None)):
        user = current_user(request)
        if user is None:
            return to_login(request)
        filename = os.path.basename((file.filename or "") if file else "").strip()
        if not filename:
            return render(request, "Upload", T.upload_body(MSG_UPLOAD_NONE, None), 400, user)
        allowed = {".csv", ".png"} | ({".exe"} if is_on("BUG_17") else set())
        if os.path.splitext(filename.lower())[1] not in allowed:
            return render(request, "Upload", T.upload_body(MSG_UPLOAD_TYPE, None), 400, user)
        data = file.file.read(UPLOAD_MAX_BYTES + 1)
        if len(data) > UPLOAD_MAX_BYTES:
            return render(request, "Upload", T.upload_body(MSG_UPLOAD_SIZE, None), 400, user)
        store.uploads.append({"owner": user["username"], "name": filename, "size": len(data)})
        return render(request, "Upload", T.upload_body(None, f"Uploaded {filename}"), user=user)

    @app.get("/admin", response_class=HTMLResponse)
    def admin(request: Request):
        user = current_user(request)
        if user is None:
            return to_login(request)
        if user["role"] != "admin" and not is_on("BUG_16"):
            return denied(request, user)
        return render(request, "Admin", T.admin_body(store.users.values()), user=user)

    @app.get("/help", response_class=HTMLResponse)
    def help_page(request: Request):
        return render(request, "Help", T.help_body(), user=current_user(request))

    # -- JSON API ------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"status": "ok", "app": "buggy_shop"}

    @app.get("/api/products")
    def api_products(request: Request, q: str = "", category: str = "", sort: str = "", page: str = "1"):
        _, err = api_auth(request)
        if err:
            return err
        if is_on("BUG_09"):
            _sleep(SLOW_DELAY_S)
        items = query_products(store, q, category, sort)
        page_items, page_no, pages, _ = paginate(items, page)
        return {"items": [product_json(p) for p in page_items], "page": page_no, "pages": pages,
                "per_page": PAGE_SIZE, "total": len(items)}

    @app.post("/api/products")
    async def api_create_product(request: Request):
        _, err = api_auth(request)
        if err:
            return err
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"errors": ["Request body must be JSON"]}, status_code=400)
        if not isinstance(payload, dict):
            return JSONResponse({"errors": ["Request body must be a JSON object"]}, status_code=400)
        clean, errors = validate_product(payload)
        if errors:
            return JSONResponse({"errors": errors}, status_code=422)
        product, created = create_or_dedupe(store, clean)
        return JSONResponse(product_json(product), status_code=201 if created else 200)

    @app.get("/api/orders/{oid}")
    def api_order(request: Request, oid: int):
        user, err = api_auth(request)
        if err:
            return err
        order = store.orders.get(oid)
        if order is None:
            return JSONResponse({"detail": "Order not found"}, status_code=404)
        if not _can_see_order(user, order):
            return JSONResponse({"detail": MSG_ACCESS_DENIED}, status_code=403)
        return order_json(order)

    return app


app = create_app()
