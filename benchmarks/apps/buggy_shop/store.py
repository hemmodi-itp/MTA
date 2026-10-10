"""
store.py — in-memory data store for the Buggy Shop benchmark app.

A fresh Store is created by create_app(), so every process start (and every
test that builds its own app) begins from the same deterministic seed.
Nothing here knows about bug flags; bug behaviour lives in app.py.
"""

import hmac
import secrets
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

CATEGORIES: tuple[str, ...] = ("Books", "Electronics", "Home")

DISCOUNT_CODE = "SAVE10"
DISCOUNT_RATE = Decimal("0.10")

# (name, category, price, description). Ids are assigned 1..N in this order.
# Notes for benchmark authors:
#   * names are deliberately mixed case (search case-sensitivity, BUG_19);
#   * price ties (9.99 x4, 19.95 x2, 24.00 x2) are listed so that id order and
#     case-insensitive name order agree within each tie (sort stability, BUG_14);
#   * "Gel Pen" costs 1.005 so a 1 x Gel Pen cart total exposes truncation vs
#     round-half-up (BUG_03); 10% off 19.95 (=17.955) exposes it too.
_SEED_PRODUCTS: list[tuple[str, str, str, str]] = [
    ("The Pragmatic Coder", "Books", "29.99", "A practical guide to everyday software craftsmanship."),
    ("data science handbook", "Books", "39.50", "Reference for statistics, Python and machine learning."),
    ("Atlas of Maps", "Books", "19.95", "Full-colour world atlas with 200 maps."),
    ("Blue Notebook", "Books", "9.99", "A5 dotted notebook, 120 pages."),
    ("Gel Pen", "Home", "1.005", "Smooth 0.5 mm black gel pen, sold individually."),
    ("USB-C Cable", "Electronics", "12.49", "1 m braided USB-C to USB-C cable."),
    ("LED Desk Lamp", "Electronics", "24.00", "Dimmable LED lamp with three colour temperatures."),
    ("wireless Mouse", "Electronics", "19.95", "Quiet 2.4 GHz wireless mouse."),
    ("Ceramic Mug", "Home", "9.99", "350 ml stoneware mug, dishwasher safe."),
    ("Cotton Throw Blanket", "Home", "34.00", "Soft woven cotton blanket, 130 x 170 cm."),
    ("Python Pocket Guide", "Books", "14.25", "Compact Python 3 language reference."),
    ("noise cancelling Headphones", "Electronics", "129.00", "Over-ear headphones with active noise cancelling."),
    ("Bamboo Cutting Board", "Home", "18.75", "Large bamboo board with juice groove."),
    ("Dish Towel Set", "Home", "9.99", "Set of three absorbent cotton towels."),
    ("Mystery at Midnight", "Books", "12.99", "A page-turning detective novel."),
    ("Portable Charger", "Electronics", "45.00", "10,000 mAh power bank with USB-C PD."),
    ("Scented Candle", "Home", "15.50", "Vanilla and cedar soy candle, 40 hour burn."),
    ("Monitor Stand", "Electronics", "24.00", "Aluminium riser with storage drawer."),
    ("HDMI Adapter", "Electronics", "8.49", "USB-C to HDMI 4K adapter."),
    ("Earbuds Case", "Electronics", "9.99", "Silicone protective case for earbuds."),
    ("Cookbook: Quick Meals", "Books", "22.00", "100 recipes ready in 30 minutes."),
    ("Glass Water Bottle", "Home", "11.95", "750 ml borosilicate bottle with sleeve."),
    ("Phone Stand", "Electronics", "13.30", "Adjustable desktop phone stand."),
]

_SEED_USERS: list[tuple[str, str, str]] = [
    ("alice", "alice-pass-1", "user"),
    ("admin", "admin-pass-1", "admin"),
]


@dataclass
class Product:
    id: int
    name: str
    price: Decimal
    category: str
    description: str = ""
    created_at: float = 0.0


@dataclass
class User:
    username: str
    password: str
    role: str


@dataclass
class Order:
    id: int
    owner: str
    lines: list[dict]
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    created_at: float = field(default_factory=time.time)


class Store:
    def __init__(self) -> None:
        self.products: dict[int, Product] = {}
        self.users: dict[str, User] = {}
        self.sessions: dict[str, dict] = {}
        self.orders: dict[int, Order] = {}
        self.carts: dict[str, dict] = {}
        self.uploads: list[dict] = []
        self._next_product_id = 1
        self._next_order_id = 1
        self._seed()

    # ── seeding ─────────────────────────────────────────────────────────────
    def _seed(self) -> None:
        for name, category, price, description in _SEED_PRODUCTS:
            # created_at=-inf so a seeded product never counts as "just created"
            self.add_product(name, Decimal(price), category, description, created_at=float("-inf"))
        for username, password, role in _SEED_USERS:
            self.users[username] = User(username, password, role)
        p1, p8 = self.products[1], self.products[8]
        self.add_order("admin", [_line(p1, 1)], p1.price, Decimal("0.00"), p1.price)
        alice_total = (p8.price * 2).quantize(Decimal("0.01"))
        self.add_order("alice", [_line(p8, 2)], alice_total, Decimal("0.00"), alice_total)

    # ── users / sessions ────────────────────────────────────────────────────
    def authenticate(self, username: str, password: str) -> tuple[Optional[User], str]:
        """Returns (user, "") on success, else (None, "unknown_user" | "bad_password")."""
        user = self.users.get(username)
        if user is None:
            return None, "unknown_user"
        if not hmac.compare_digest(user.password.encode(), password.encode()):
            return None, "bad_password"
        return user, ""

    def create_session(self, username: str) -> str:
        sid = secrets.token_urlsafe(24)
        self.sessions[sid] = {"username": username, "flash": None}
        return sid

    def get_session(self, sid: Optional[str]) -> Optional[dict]:
        if not sid:
            return None
        return self.sessions.get(sid)

    def destroy_session(self, sid: Optional[str]) -> None:
        if sid:
            self.sessions.pop(sid, None)

    # ── products ────────────────────────────────────────────────────────────
    def add_product(self, name: str, price: Decimal, category: str, description: str = "",
                    created_at: Optional[float] = None) -> Product:
        pid = self._next_product_id
        self._next_product_id += 1
        product = Product(pid, name, price, category, description,
                          time.monotonic() if created_at is None else created_at)
        self.products[pid] = product
        return product

    def find_recent_duplicate(self, name: str, price: Decimal, window_s: float) -> Optional[Product]:
        now = time.monotonic()
        for p in self.products.values():
            if p.name == name and p.price == price and now - p.created_at <= window_s:
                return p
        return None

    def delete_product(self, pid: int) -> None:
        self.products.pop(pid, None)

    # ── carts / orders ──────────────────────────────────────────────────────
    def cart(self, username: str) -> dict:
        return self.carts.setdefault(username, {"items": {}, "discounts": 0})

    def clear_cart(self, username: str) -> None:
        self.carts[username] = {"items": {}, "discounts": 0}

    def add_order(self, owner: str, lines: list[dict], subtotal: Decimal, discount: Decimal,
                  total: Decimal) -> Order:
        oid = self._next_order_id
        self._next_order_id += 1
        order = Order(oid, owner, lines, subtotal, discount, total)
        self.orders[oid] = order
        return order


def _line(product: Product, qty: int) -> dict:
    return {
        "product_id": product.id,
        "name": product.name,
        "unit_price": product.price,
        "quantity": qty,
        "line_total": (product.price * qty).quantize(Decimal("0.01")),
    }
