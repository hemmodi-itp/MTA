# Buggy Shop — Business Requirements Document

| Field | Value |
|---|---|
| Product | Buggy Shop (web storefront and back office) |
| Version | 1.0 |
| Status | Approved for testing |
| Audience | Product, engineering, QA |

## 1. Purpose

Buggy Shop is a small online shop. Signed-in customers browse a product catalogue, manage
products, fill a cart, apply a discount code, check out and view their orders. Administrators can
also see the user list. This document lists the business requirements (`REQ-xx`) and their
acceptance criteria (`AC-xx.y`). Each acceptance criterion is a testable statement of correct
behaviour. Where a message is quoted, the application must show exactly that text.

## 2. Users and roles

| Role | Description |
|---|---|
| Customer (`user`) | Browses products, manages products, buys items, sees only their own orders. |
| Administrator (`admin`) | Everything a customer can do, plus the Admin page and every order. |

Test accounts (local environment only): `alice` / `alice-pass-1` (customer), `admin` / `admin-pass-1`
(administrator).

## 3. Scope

In scope: login and logout, product catalogue (list, search, filter, sort, paginate), product
create/edit/delete, product detail, cart, discount code, checkout, order confirmation and order
viewing, file upload, admin user list, help page, and the JSON API mirror under `/api/`.

Out of scope: payments, shipping, email notifications, user registration.

## 4. Requirements and acceptance criteria

### REQ-01 Authentication and session

Users must sign in before using the shop. Only the login page, the help page and the health check
are available without signing in; any other page redirects to the login page.

- AC-01.1: Given valid credentials (for example `alice` / `alice-pass-1`), when the user submits the login form, then they land on the Products page.
- AC-01.2: Given a wrong password or an unknown username, when the user submits the login form, then the page shows exactly "Invalid username or password" and does not reveal which part was wrong.
- AC-01.3: When the user logs out, the session is invalidated on the server: afterwards every protected page redirects to the login page, even if the old session cookie is sent again.
- AC-01.4: Every field on the login form (Username, Password) has a visible label that is programmatically associated with its input (accessible name).

### REQ-02 Product catalogue

The Products page lists products with search, a category filter, sorting and pagination.

- AC-02.1: The product list is paginated with 5 products per page, with Previous/Next links and a "Page N of M" indicator.
- AC-02.2: Search matches any product whose name contains the search text, ignoring upper/lower case (for example "mouse" finds "wireless Mouse").
- AC-02.3: Sorting by price (low to high, or high to low) is stable: products with the same price keep their catalogue order (product id order, which is also their name order).
- AC-02.4: A search containing any characters, including `%`, `_`, quotes or symbols, never causes an error; it simply returns the matching products or "No products found".
- AC-02.5: When a category filter (or search or sort) is active, the pagination links keep it, so page 2 still shows only the filtered products.
- AC-02.6: The product list (page and API) loads within 2 seconds.

### REQ-03 Product management

Signed-in users can add, edit and delete products. The form has Name, Price, Category and an
optional Description. Validation runs in the browser and is always enforced again on the server
(including for the JSON API).

- AC-03.1: Name is required; an empty or blank name is rejected with "Name is required".
- AC-03.2: Name must be 1–50 characters; a name of exactly 50 characters is accepted and 51 or more is rejected with "Name must be at most 50 characters".
- AC-03.3: Price is required, numeric with at most 2 decimals, and must be zero or more; a negative price is rejected with "Price must be zero or more". The server enforces this too, including `POST /api/products`.
- AC-03.4: Category must be one of Books, Electronics or Home ("Please choose a category"); Description is optional and at most 500 characters ("Description must be at most 500 characters").
- AC-03.5: The product description is shown on the product detail page as plain text: any HTML or script in it is displayed literally and never executed.
- AC-03.6: Submitting the same product twice in quick succession (double click, or the same name and price within 5 seconds) creates only one product; the Save button is disabled while saving.
- AC-03.7: When a product is deleted, the page confirms "Product deleted" and the product disappears permanently: it no longer appears in the list or search, and its detail page returns "Product not found", even after a reload.

### REQ-04 File upload

- AC-04.1: Uploading a CSV or PNG file of at most 1 MB succeeds and shows "Uploaded <file name>".
- AC-04.2: Any other file type (for example `.exe`, `.txt`, `.pdf`) is rejected by the server with "Only CSV or PNG files are allowed"; files over 1 MB are rejected with "File must be 1 MB or smaller".

### REQ-05 Cart and checkout

- AC-05.1: Quantity must be a whole number from 1 to 99, both when adding from the product page and when updating the cart; anything else (0, negative, 100 or more, text) is rejected with "Quantity must be between 1 and 99".
- AC-05.2: Line totals, subtotal, discount and total are calculated from exact amounts and rounded half up to 2 decimals. Examples: 1 × Gel Pen at 1.005 gives a total of 1.01; 3 × Gel Pen gives 3.02; 1 × Atlas of Maps (19.95) with SAVE10 gives a total of 17.96 (17.955 rounded half up).
- AC-05.3: Discount code SAVE10 gives 10% off the cart and can be applied only once per cart; applying it again shows "Discount already applied" and the total does not change. Unknown codes show "Invalid discount code".
- AC-05.4: Checkout with an empty cart does not create an order; the checkout page shows "Your cart is empty".

### REQ-06 Orders

- AC-06.1: Placing an order from a non-empty cart opens the order confirmation page for the new order, showing "Order #<id>", the message "Thank you! Your order #<id> has been placed.", its lines and total; the cart is then empty.
- AC-06.2: Customers can see only their own orders. Opening another user's order (page `/orders/<id>` or `GET /api/orders/<id>`) returns HTTP 403 with "Access denied". Administrators can see every order.

### REQ-07 Administration

- AC-07.1: The Admin page (`/admin`, listing users and roles) is available only to administrators; any other signed-in user gets HTTP 403 with "Access denied".

### REQ-08 Help

- AC-08.1: Every page has a "Help" link in the footer that opens the Help page (`/help`), which is available without signing in.

## 5. Non-functional requirements

- Accessibility: semantic HTML, labelled form controls, errors announced with `role="alert"`.
- Performance: see AC-02.6.
- Security: output encoding for all user content (AC-03.5), server-side authorization on every request (AC-06.2, AC-07.1), session invalidation on logout (AC-01.3).

## 6. JSON API (mirror of the UI)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | Public. `{"status": "ok"}` |
| GET | `/api/products` | Same `q`, `category`, `sort`, `page` parameters and rules as the Products page. |
| POST | `/api/products` | JSON `{name, price, category, description}`; same validation as the form (422 with `errors`). |
| GET | `/api/orders/{id}` | Same ownership rule as AC-06.2. |

All API endpoints except `/api/health` require a signed-in session (otherwise HTTP 401).
