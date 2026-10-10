"""
templates.py — server-rendered HTML for the Buggy Shop benchmark app.

Plain f-strings + html.escape, a little vanilla JS for client validation.
Templates are bug-agnostic: app.py decides behaviour and passes plain values
(e.g. `raw_description=True`, `help_href="/helpp"`) in here.

Stable hooks for DOM scanners: every key element has an `id` and a
`data-testid` attribute; errors use role="alert", success messages role="status".
"""

from html import escape
from decimal import Decimal
from typing import Iterable, Optional
from urllib.parse import quote

_CSS = """
:root { --fg:#1d1d1f; --muted:#5f6368; --accent:#0b57d0; --bad:#b3261e; --ok:#146c2e; --line:#d0d4da; }
* { box-sizing: border-box; }
body { margin:0; font-family: system-ui, sans-serif; color: var(--fg); background:#fafafa; }
header { display:flex; gap:1rem; align-items:center; padding:.75rem 1rem; background:#fff; border-bottom:1px solid var(--line); flex-wrap:wrap; }
header .brand { font-weight:700; text-decoration:none; color:var(--fg); }
nav ul { list-style:none; display:flex; gap:1rem; margin:0; padding:0; flex-wrap:wrap; }
main { max-width: 860px; margin: 1.5rem auto; padding: 0 1rem; }
footer { border-top:1px solid var(--line); padding:1rem; text-align:center; }
a { color: var(--accent); }
label { display:block; font-weight:600; margin-top:.75rem; }
input, select, textarea { font: inherit; padding:.4rem; width:100%; max-width:420px; }
input[type=number] { max-width:6rem; }
button { font: inherit; padding:.45rem .9rem; margin-top:.75rem; cursor:pointer; }
table { border-collapse: collapse; width:100%; }
th, td { text-align:left; padding:.4rem; border-bottom:1px solid var(--line); vertical-align: top; }
.alert { color: var(--bad); border:1px solid var(--bad); padding:.5rem .75rem; background:#fdecea; }
.status { color: var(--ok); border:1px solid var(--ok); padding:.5rem .75rem; background:#e6f4ea; }
.muted { color: var(--muted); }
.inline { display:inline; }
.search-row { display:flex; gap:.5rem; flex-wrap:wrap; align-items:flex-end; }
.search-row label { margin-top:0; }
"""


def e(value) -> str:
    return escape("" if value is None else str(value), quote=True)


def page(title: str, body: str, user: Optional[dict] = None, flash: Optional[str] = None,
         help_href: str = "/help") -> str:
    if user:
        admin_link = (
            '<li><a id="nav-admin" data-testid="nav-admin" href="/admin">Admin</a></li>'
            if user.get("role") == "admin" else ""
        )
        nav = f"""
<nav aria-label="Main" id="main-nav" data-testid="main-nav">
  <ul>
    <li><a id="nav-products" data-testid="nav-products" href="/products">Products</a></li>
    <li><a id="nav-new-product" data-testid="nav-new-product" href="/products/new">Add product</a></li>
    <li><a id="nav-cart" data-testid="nav-cart" href="/cart">Cart</a></li>
    <li><a id="nav-upload" data-testid="nav-upload" href="/upload">Upload</a></li>
    {admin_link}
    <li><a id="logout-link" data-testid="logout-link" href="/logout">Log out</a></li>
  </ul>
</nav>
<span id="current-user" data-testid="current-user" class="muted">Signed in as {e(user.get("username"))}</span>"""
    else:
        nav = """
<nav aria-label="Main" id="main-nav" data-testid="main-nav">
  <ul><li><a id="nav-login" data-testid="nav-login" href="/login">Log in</a></li></ul>
</nav>"""
    flash_html = (
        f'<p id="flash" data-testid="flash" role="status" class="status">{e(flash)}</p>' if flash else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} - Buggy Shop</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <a class="brand" href="/products" id="brand-link" data-testid="brand-link">Buggy Shop</a>
  {nav}
</header>
<main id="main" data-testid="main">
{flash_html}
{body}
</main>
<footer id="site-footer" data-testid="site-footer">
  <a id="footer-help-link" data-testid="footer-help-link" href="{e(help_href)}">Help</a>
</footer>
</body>
</html>"""


def _alerts(errors: Iterable[str], element_id: str) -> str:
    errors = list(errors)
    if not errors:
        return f'<div id="{element_id}" data-testid="{element_id}" role="alert" class="alert" hidden></div>'
    items = "".join(f"<li>{e(m)}</li>" for m in errors)
    return f'<div id="{element_id}" data-testid="{element_id}" role="alert" class="alert"><ul>{items}</ul></div>'


# ── login ───────────────────────────────────────────────────────────────────

def login_body(error: Optional[str], next_url: str, username: str, password_label: bool) -> str:
    err = (
        f'<p id="login-error" data-testid="login-error" role="alert" class="alert">{e(error)}</p>'
        if error else ""
    )
    if password_label:
        pw_label = '<label for="password">Password</label>'
    else:
        # Visible text, but not associated with the input: no accessible name.
        pw_label = '<span class="muted">Password</span>'
    return f"""
<h1>Log in</h1>
{err}
<form id="login-form" data-testid="login-form" method="post" action="/login">
  <input type="hidden" name="next" value="{e(next_url)}">
  <label for="username">Username</label>
  <input id="username" data-testid="username" name="username" type="text" autocomplete="username" value="{e(username)}" required>
  {pw_label}
  <input id="password" data-testid="password" name="password" type="password" autocomplete="current-password" required>
  <button id="login-button" data-testid="login-button" type="submit">Log in</button>
</form>"""


# ── products ────────────────────────────────────────────────────────────────

def _price(p) -> str:
    return f"{p:.3f}" if p != p.quantize(Decimal("0.01")) else f"{p:.2f}"


def fmt_price(p) -> str:
    return _price(p)


def products_body(items, q: str, category: str, sort: str, categories, page_no: int, pages: int,
                  total: int, start: int, prev_href: Optional[str], next_href: Optional[str]) -> str:
    cat_opts = '<option value="">All categories</option>' + "".join(
        f'<option value="{e(c)}"{" selected" if c == category else ""}>{e(c)}</option>' for c in categories
    )
    sorts = [("", "Default"), ("price_asc", "Price: low to high"), ("price_desc", "Price: high to low"),
             ("name", "Name")]
    sort_opts = "".join(
        f'<option value="{v}"{" selected" if v == sort else ""}>{lbl}</option>' for v, lbl in sorts
    )
    if items:
        rows = "".join(
            f'<li data-testid="product-item" data-product-id="{p.id}">'
            f'<a href="/products/{p.id}" data-testid="product-link">{e(p.name)}</a> '
            f'<span data-testid="product-price">${_price(p.price)}</span> '
            f'<span class="muted" data-testid="product-category">{e(p.category)}</span></li>'
            for p in items
        )
        listing = f'<ul id="product-list" data-testid="product-list">{rows}</ul>'
        count = (f'<p id="result-count" data-testid="result-count">Showing {start + 1}-{start + len(items)} '
                 f'of {total} products</p>')
    else:
        listing = '<p id="no-results" data-testid="no-results">No products found</p>'
        count = '<p id="result-count" data-testid="result-count">Showing 0 of 0 products</p>'
    prev_link = (f'<a id="prev-page" data-testid="prev-page" href="{e(prev_href)}" rel="prev">Previous</a>'
                 if prev_href else "")
    next_link = (f'<a id="next-page" data-testid="next-page" href="{e(next_href)}" rel="next">Next</a>'
                 if next_href else "")
    return f"""
<h1>Products</h1>
<form id="search-form" data-testid="search-form" method="get" action="/products" role="search">
  <div class="search-row">
    <div><label for="search">Search</label>
      <input id="search" data-testid="search" name="q" type="search" value="{e(q)}"></div>
    <div><label for="category-filter">Category</label>
      <select id="category-filter" data-testid="category-filter" name="category">{cat_opts}</select></div>
    <div><label for="sort">Sort by</label>
      <select id="sort" data-testid="sort" name="sort">{sort_opts}</select></div>
    <div><button id="search-button" data-testid="search-button" type="submit">Search</button></div>
  </div>
</form>
{count}
{listing}
<nav aria-label="Pagination" id="pagination" data-testid="pagination">
  {prev_link}
  <span id="page-indicator" data-testid="page-indicator">Page {page_no} of {pages}</span>
  {next_link}
</nav>"""


def product_form_body(action: str, heading: str, values: dict, errors: list[str], categories,
                      name_max: int, name_strict_less: bool, require_name: bool,
                      disable_on_submit: bool) -> str:
    cat_opts = '<option value="">Choose a category</option>' + "".join(
        f'<option value="{e(c)}"{" selected" if c == values.get("category") else ""}>{e(c)}</option>'
        for c in categories
    )
    required_attr = ' required aria-required="true"' if require_name else ""
    js_bool = lambda b: "true" if b else "false"  # noqa: E731
    return f"""
<h1>{e(heading)}</h1>
{_alerts(errors, "form-errors")}
<form id="product-form" data-testid="product-form" method="post" action="{e(action)}" novalidate>
  <label for="name">Name</label>
  <input id="name" data-testid="name" name="name" type="text" value="{e(values.get("name", ""))}"{required_attr}>
  <label for="price">Price</label>
  <input id="price" data-testid="price" name="price" type="text" inputmode="decimal" value="{e(values.get("price", ""))}" required aria-required="true">
  <label for="category">Category</label>
  <select id="category" data-testid="category" name="category" required aria-required="true">{cat_opts}</select>
  <label for="description">Description (optional)</label>
  <textarea id="description" data-testid="description" name="description" rows="4">{e(values.get("description", ""))}</textarea>
  <button id="save-product" data-testid="save-product" type="submit">Save product</button>
</form>
<script>
(function () {{
  var NAME_MAX = {name_max}, NAME_STRICT = {js_bool(name_strict_less)};
  var REQUIRE_NAME = {js_bool(require_name)}, DISABLE_ON_SUBMIT = {js_bool(disable_on_submit)};
  var form = document.getElementById('product-form');
  var box = document.getElementById('form-errors');
  form.addEventListener('submit', function (ev) {{
    var errors = [];
    var name = form.elements['name'].value.trim();
    var price = form.elements['price'].value.trim();
    var category = form.elements['category'].value;
    var desc = form.elements['description'].value;
    if (!name) {{
      if (REQUIRE_NAME) errors.push('Name is required');
    }} else if (NAME_STRICT ? name.length >= NAME_MAX : name.length > NAME_MAX) {{
      errors.push('Name must be at most 50 characters');
    }}
    if (!price) errors.push('Price is required');
    else if (!/^-?\\d+(\\.\\d{{1,2}})?$/.test(price)) errors.push('Price must be a number with at most 2 decimals');
    else if (parseFloat(price) < 0) errors.push('Price must be zero or more');
    if (!category) errors.push('Please choose a category');
    if (desc.length > 500) errors.push('Description must be at most 500 characters');
    if (errors.length) {{
      ev.preventDefault();
      box.innerHTML = '';
      var ul = document.createElement('ul');
      errors.forEach(function (m) {{ var li = document.createElement('li'); li.textContent = m; ul.appendChild(li); }});
      box.appendChild(ul);
      box.hidden = false;
      return;
    }}
    if (DISABLE_ON_SUBMIT) {{
      var btn = document.getElementById('save-product');
      btn.disabled = true;
      btn.textContent = 'Saving...';
    }}
  }});
}})();
</script>"""


def product_detail_body(p, raw_description: bool, cart_errors: list[str]) -> str:
    desc = (p.description or "") if raw_description else e(p.description)
    return f"""
<h1 id="product-name" data-testid="product-name">{e(p.name)}</h1>
<p>Price: <span id="product-price" data-testid="product-price">${_price(p.price)}</span></p>
<p>Category: <span id="product-category" data-testid="product-category">{e(p.category)}</span></p>
<h2>Description</h2>
<div id="product-description" data-testid="product-description">{desc}</div>
{_alerts(cart_errors, "cart-error")}
<form id="add-to-cart-form" data-testid="add-to-cart-form" method="post" action="/cart/add" novalidate>
  <input type="hidden" name="product_id" value="{p.id}">
  <label for="quantity">Quantity</label>
  <input id="quantity" data-testid="quantity" name="quantity" type="number" min="1" max="99" value="1">
  <button id="add-to-cart" data-testid="add-to-cart" type="submit">Add to cart</button>
</form>
<p><a id="edit-product" data-testid="edit-product" href="/products/{p.id}/edit">Edit product</a></p>
<form id="delete-form" data-testid="delete-form" method="post" action="/products/{p.id}/delete">
  <button id="delete-product" data-testid="delete-product" type="submit">Delete</button>
</form>
<p><a id="back-to-products" data-testid="back-to-products" href="/products">Back to products</a></p>"""


# ── cart / checkout / orders ────────────────────────────────────────────────

def _summary_rows(summary: dict) -> str:
    disc = ""
    if summary["discounts"]:
        times = f" x{summary['discounts']}" if summary["discounts"] > 1 else ""
        disc = (f'<tr><th scope="row">Discount (SAVE10{times})</th>'
                f'<td id="cart-discount" data-testid="cart-discount">-${summary["discount"]:.2f}</td></tr>')
    return f"""
<table id="cart-summary" data-testid="cart-summary">
  <tr><th scope="row">Subtotal</th><td id="cart-subtotal" data-testid="cart-subtotal">${summary["subtotal"]:.2f}</td></tr>
  {disc}
  <tr><th scope="row">Total</th><td id="cart-total" data-testid="cart-total">${summary["total"]:.2f}</td></tr>
</table>"""


def cart_body(summary: dict, errors: list[str]) -> str:
    lines = summary["lines"]
    if lines:
        rows = "".join(f"""
  <tr data-testid="cart-line" data-product-id="{ln['product'].id}">
    <td data-testid="cart-line-name">{e(ln['product'].name)}</td>
    <td data-testid="cart-line-price">${_price(ln['product'].price)}</td>
    <td>
      <form class="inline" method="post" action="/cart/update" novalidate>
        <input type="hidden" name="product_id" value="{ln['product'].id}">
        <label for="qty-{ln['product'].id}">Quantity for {e(ln['product'].name)}</label>
        <input id="qty-{ln['product'].id}" data-testid="cart-line-quantity" name="quantity" type="number" min="1" max="99" value="{ln['quantity']}">
        <button type="submit" data-testid="update-quantity">Update</button>
      </form>
      <form class="inline" method="post" action="/cart/remove">
        <input type="hidden" name="product_id" value="{ln['product'].id}">
        <button type="submit" data-testid="remove-line">Remove</button>
      </form>
    </td>
    <td data-testid="line-total">${ln['line_total']:.2f}</td>
  </tr>""" for ln in lines)
        table = f"""
<table id="cart-table" data-testid="cart-table">
  <thead><tr><th scope="col">Product</th><th scope="col">Unit price</th><th scope="col">Quantity</th><th scope="col">Line total</th></tr></thead>
  <tbody>{rows}</tbody>
</table>"""
    else:
        table = '<p id="cart-empty" data-testid="cart-empty">Your cart is empty</p>'
    return f"""
<h1>Your cart</h1>
{_alerts(errors, "cart-error")}
{table}
{_summary_rows(summary)}
<form id="discount-form" data-testid="discount-form" method="post" action="/cart/discount">
  <label for="discount-code">Discount code</label>
  <input id="discount-code" data-testid="discount-code" name="code" type="text">
  <button id="apply-discount" data-testid="apply-discount" type="submit">Apply</button>
</form>
<p><a id="checkout-link" data-testid="checkout-link" href="/checkout">Proceed to checkout</a></p>"""


def checkout_body(summary: dict, empty_error: Optional[str]) -> str:
    if empty_error:
        return f"""
<h1>Checkout</h1>
<p id="checkout-error" data-testid="checkout-error" role="alert" class="alert">{e(empty_error)}</p>
<p><a href="/products" id="continue-shopping" data-testid="continue-shopping">Continue shopping</a></p>"""
    items = "".join(
        f'<li data-testid="checkout-line">{ln["quantity"]} x {e(ln["product"].name)} = ${ln["line_total"]:.2f}</li>'
        for ln in summary["lines"]
    )
    return f"""
<h1>Checkout</h1>
<ul id="checkout-lines" data-testid="checkout-lines">{items}</ul>
{_summary_rows(summary)}
<form id="checkout-form" data-testid="checkout-form" method="post" action="/checkout">
  <button id="place-order" data-testid="place-order" type="submit">Place order</button>
</form>"""


def order_body(order) -> str:
    rows = "".join(
        f'<tr data-testid="order-line"><td>{e(ln["name"])}</td><td>{ln["quantity"]}</td>'
        f'<td>${ln["line_total"]:.2f}</td></tr>'
        for ln in order.lines
    )
    return f"""
<h1 id="order-title" data-testid="order-title">Order #{order.id}</h1>
<p id="order-confirmation" data-testid="order-confirmation" role="status" class="status">Thank you! Your order #{order.id} has been placed.</p>
<p>Ordered by <span id="order-owner" data-testid="order-owner">{e(order.owner)}</span></p>
<table id="order-lines" data-testid="order-lines">
  <thead><tr><th scope="col">Product</th><th scope="col">Quantity</th><th scope="col">Line total</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<p>Subtotal: <span id="order-subtotal" data-testid="order-subtotal">${order.subtotal:.2f}</span></p>
<p>Discount: <span id="order-discount" data-testid="order-discount">${order.discount:.2f}</span></p>
<p>Total: <span id="order-total" data-testid="order-total">${order.total:.2f}</span></p>"""


# ── upload / admin / help / errors ──────────────────────────────────────────

def upload_body(error: Optional[str], success: Optional[str]) -> str:
    err = (f'<p id="upload-error" data-testid="upload-error" role="alert" class="alert">{e(error)}</p>'
           if error else "")
    ok = (f'<p id="upload-result" data-testid="upload-result" role="status" class="status">{e(success)}</p>'
          if success else "")
    return f"""
<h1>Upload a file</h1>
<p class="muted">CSV or PNG files up to 1 MB.</p>
{err}{ok}
<form id="upload-form" data-testid="upload-form" method="post" action="/upload" enctype="multipart/form-data">
  <label for="file">File</label>
  <input id="file" data-testid="file" name="file" type="file" accept=".csv,.png">
  <button id="upload-button" data-testid="upload-button" type="submit">Upload</button>
</form>"""


def admin_body(users) -> str:
    rows = "".join(
        f'<tr data-testid="user-row"><td>{e(u.username)}</td><td>{e(u.role)}</td></tr>' for u in users
    )
    return f"""
<h1>Admin</h1>
<h2>Users</h2>
<table id="user-table" data-testid="user-table">
  <thead><tr><th scope="col">Username</th><th scope="col">Role</th></tr></thead>
  <tbody>{rows}</tbody>
</table>"""


def help_body() -> str:
    return """
<h1 id="help-title" data-testid="help-title">Help</h1>
<h2>Shopping</h2>
<p>Browse the catalogue on the Products page. Use search, the category filter and sorting to find items.</p>
<h2>Your cart</h2>
<p>Quantities must be between 1 and 99. Discount code SAVE10 gives 10% off, once per cart.</p>
<h2>Uploads</h2>
<p>You can upload CSV or PNG files up to 1 MB.</p>
<h2>Contact</h2>
<p>Email support@buggyshop.invalid.</p>"""


def error_body(title: str, message: str) -> str:
    return f"""
<h1>{e(title)}</h1>
<p id="error-message" data-testid="error-message" role="alert" class="alert">{e(message)}</p>
<p><a href="/products">Back to products</a></p>"""


def login_redirect_target(path_and_query: str) -> str:
    return "/login?next=" + quote(path_and_query, safe="")
