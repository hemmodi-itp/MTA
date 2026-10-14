"""
locator_changes.py — Phase 6 healing benchmark: switchable LOCATOR changes (not bugs — the app behaves the same).

Applied to every rendered page by app.py. Flags are read like the BUG_xx flags (LOC_01=1, ...). Every change keeps
the form field `name` attributes (the server reads them) and all behaviour; only what a refactor would touch
changes: ids, test ids, wording, wrappers, position in the DOM.

  LOC_01  login button: id + test id renamed
  LOC_02  username field: id + test id renamed (label follows)
  LOC_03  password field: wrapped in a div, id + test id renamed
  LOC_04  product form save button: test id renamed AND reworded ("Save product" -> "Save item")
  LOC_05  product name field: id + test id renamed
  LOC_06  price field: moved into a <fieldset><legend>Pricing</legend>, id + test id renamed
  LOC_07  category select: id + test id renamed
  LOC_08  product search box: id + test id renamed
  LOC_09  add-to-cart button: id + test id renamed
  LOC_10  footer help link: moved into a footer <nav>, id + test id renamed
  LOC_11  CONTROL — the product form's save button is removed; a "Cancel" button takes its slot (heal must refuse)
  LOC_12  CONTROL — the product name field is removed; a "Nickname" field takes its slot (heal must refuse)

Ground truth for the benchmark: while any LOC_xx is on, each target element carries `data-bench-id="<key>"` (added
before any change, never moved to a replacement element). MTA's fingerprint never reads it. With every flag off the
page is byte-for-byte the normal app.
"""

import re

from benchmarks.apps.buggy_shop.bugs import is_on

ALL_LOCATOR_CHANGES = tuple(f"LOC_{i:02d}" for i in range(1, 13))
CONTROLS = ("LOC_11", "LOC_12")

# key -> the original opening-tag fragment that identifies the target element
TRUTH = {
    "login_button": 'id="login-button" data-testid="login-button"',
    "username": 'id="username" data-testid="username"',
    "password": 'id="password" data-testid="password"',
    "save_product": 'id="save-product" data-testid="save-product"',
    "product_name": 'id="name" data-testid="name"',
    "price": 'id="price" data-testid="price"',
    "category": 'id="category" data-testid="category"',
    "search": 'id="search" data-testid="search"',
    "add_to_cart": 'id="add-to-cart" data-testid="add-to-cart"',
    "help_link": 'id="footer-help-link" data-testid="footer-help-link"',
}

# flag -> list of (regex, replacement), applied in order after the truth attributes are in place
CHANGES = {
    "LOC_01": [(r'id="login-button" data-testid="login-button"', 'id="signin-submit" data-testid="signin-submit"')],
    "LOC_02": [(r'<label for="username">', '<label for="user-login">'),
               (r'id="username" data-testid="username"', 'id="user-login" data-testid="user-login"')],
    "LOC_03": [(r'(<input id="password" data-testid="password"[^>]*>)', r'<div class="pw-wrap">\1</div>'),
               (r'<label for="password">', '<label for="pass-input">'),
               (r'id="password" data-testid="password"', 'id="pass-input" data-testid="pass-input"')],
    # the id stays: the app's own script disables #save-product on submit (renaming it would break the app, not
    # just the locator)
    "LOC_04": [(r'id="save-product" data-testid="save-product"([^>]*)>Save product<',
                r'id="save-product" data-testid="submit-product"\1>Save item<')],
    "LOC_05": [(r'<label for="name">', '<label for="product-name-input">'),
               (r'id="name" data-testid="name"', 'id="product-name-input" data-testid="product-name-input"')],
    "LOC_06": [(r'(<label for="price">Price</label>\s*<input id="price" data-testid="price"[^>]*>)',
                r'<fieldset class="pricing"><legend>Pricing</legend>\1</fieldset>'),
               (r'<label for="price">', '<label for="price-input">'),
               (r'id="price" data-testid="price"', 'id="price-input" data-testid="price-input"')],
    "LOC_07": [(r'<label for="category">', '<label for="product-category">'),
               (r'id="category" data-testid="category"', 'id="product-category" data-testid="product-category"')],
    "LOC_08": [(r'<label for="search">', '<label for="product-search">'),
               (r'id="search" data-testid="search"', 'id="product-search" data-testid="product-search"')],
    "LOC_09": [(r'id="add-to-cart" data-testid="add-to-cart"', 'id="cart-add" data-testid="cart-add"')],
    "LOC_10": [(r'(<a id="footer-help-link" data-testid="footer-help-link"[^>]*>Help</a>)',
                r'<nav aria-label="Footer"><a href="/products">Shop</a> \1</nav>'),
               (r'id="footer-help-link" data-testid="footer-help-link"', 'id="help-link" data-testid="help-link"')],
    "LOC_11": [(r'<button id="save-product" data-testid="save-product" data-bench-id="save_product" type="submit">'
                r'Save product</button>',
                '<button id="cancel-edit" data-testid="cancel-edit" type="button">Cancel</button>')],
    "LOC_12": [(r'<input id="name" data-testid="name" data-bench-id="product_name" name="name"',
                '<input id="nickname" data-testid="nickname" name="nickname"'),
               (r'<label for="name">Name</label>', '<label for="nickname">Nickname</label>')],
}


def mark_truth(html: str) -> str:
    for key, frag in TRUTH.items():
        html = html.replace(frag, f'{frag} data-bench-id="{key}"')
    return html


def apply(html: str) -> str:
    """With any LOC_xx on: truth attributes, then every enabled change. Off (the default): the page is untouched."""
    enabled = [flag for flag in ALL_LOCATOR_CHANGES if is_on(flag)]
    if not enabled:
        return html
    html = mark_truth(html)
    for flag in enabled:
        for pattern, repl in CHANGES[flag]:
            html = re.sub(pattern, repl, html)
    return html
