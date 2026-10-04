# Business Requirements Document — Module 02: Inventory Page

---

## 1. Purpose

This module validates the **Inventory (Products) page** of the SauceDemo application after a successful login. It ensures that users can browse products, sort the inventory, view product information, add and remove items from the cart, and navigate to related pages such as the shopping cart and product details.

---

## 2. Page / Feature Structure

| Region | Description |
|--------|-------------|
| Header | Displays the application logo, hamburger menu, shopping cart icon, and cart badge. |
| Product Sort | Dropdown allowing users to sort products by Name (A-Z, Z-A) and Price (Low-High, High-Low). |
| Inventory List | Displays all available inventory items. |
| Inventory Card | Contains product image, product name, description, price, and Add to Cart / Remove button. |
| Shopping Cart | Displays the current number of selected items and navigates to the cart page. |
| Footer | Displays footer information and social media links. |

**URL:** `https://www.saucedemo.com/inventory.html`

---

## 3. Actors

| Actor | Description |
|-------|-------------|
| Primary User | Authenticated Standard User |
| Secondary User | Authenticated Performance User / Problem User |
| Automated Test Agent | Playwright test runner executing automated scenarios |

---

## 4. Business Scenarios

### SC-M02-001: View Inventory Page Successfully

- **Actor:** Authenticated User
- **Precondition:** User has successfully logged into SauceDemo.
- **Steps:**
  1. Login using valid credentials.
  2. Navigate to Inventory page.
- **Expected Result:**
  - Inventory page loads successfully.
  - Product list is displayed.
  - Shopping cart icon is visible.
  - Sort dropdown is available.
- **Business Rules:**
  - Only authenticated users can access this page.

---

### SC-M02-002: Verify All Inventory Items are Displayed

- **Actor:** Authenticated User
- **Precondition:** User is on Inventory page.
- **Steps:**
  1. Observe the inventory list.
- **Expected Result:**
  - Six inventory products are displayed.
  - Each product contains:
    - Product image
    - Product name
    - Description
    - Price
    - Add to Cart button
- **Business Rules:**
  - Every product must contain complete information.

---

### SC-M02-003: Add Single Item to Cart

- **Actor:** Authenticated User
- **Precondition:** User is on Inventory page.
- **Steps:**
  1. Click "Add to Cart" for a product.
- **Expected Result:**
  - Button changes to "Remove".
  - Cart badge increments by one.
- **Business Rules:**
  - Same product cannot be added multiple times.

---

### SC-M02-004: Remove Item from Cart

- **Actor:** Authenticated User
- **Precondition:** Product already added to cart.
- **Steps:**
  1. Click Remove.
- **Expected Result:**
  - Product removed from cart.
  - Button changes back to Add to Cart.
  - Cart badge decreases.
- **Business Rules:**
  - Cart badge reflects current cart quantity.

---

### SC-M02-005: Add Multiple Products

- **Actor:** Authenticated User
- **Precondition:** User on Inventory page.
- **Steps:**
  1. Add multiple products.
- **Expected Result:**
  - Cart badge displays correct count.
  - All selected products remain selected.
- **Business Rules:**
  - Badge count equals total unique selected products.

---

### SC-M02-006: Sort Products by Name (A-Z)

- **Actor:** Authenticated User
- **Precondition:** Inventory page loaded.
- **Steps:**
  1. Select "Name (A to Z)".
- **Expected Result:**
  - Products appear in alphabetical order.
- **Business Rules:**
  - Sorting occurs immediately.

---

### SC-M02-007: Sort Products by Name (Z-A)

- **Actor:** Authenticated User
- **Precondition:** Inventory page loaded.
- **Steps:**
  1. Select "Name (Z to A)".
- **Expected Result:**
  - Products displayed in reverse alphabetical order.
- **Business Rules:**
  - Entire product list updates.

---

### SC-M02-008: Sort Products by Price (Low to High)

- **Actor:** Authenticated User
- **Precondition:** Inventory page loaded.
- **Steps:**
  1. Select "Price (low to high)".
- **Expected Result:**
  - Products sorted by ascending price.
- **Business Rules:**
  - Lowest priced product appears first.

---

### SC-M02-009: Sort Products by Price (High to Low)

- **Actor:** Authenticated User
- **Precondition:** Inventory page loaded.
- **Steps:**
  1. Select "Price (high to low)".
- **Expected Result:**
  - Products sorted by descending price.
- **Business Rules:**
  - Highest priced product appears first.

---

### SC-M02-010: Navigate to Product Details

- **Actor:** Authenticated User
- **Precondition:** Inventory page loaded.
- **Steps:**
  1. Click a product image or title.
- **Expected Result:**
  - Product Details page opens.
- **Business Rules:**
  - Correct product information must be displayed.

---

### SC-M02-011: Open Shopping Cart

- **Actor:** Authenticated User
- **Precondition:** User on Inventory page.
- **Steps:**
  1. Click shopping cart icon.
- **Expected Result:**
  - Shopping cart page opens.
- **Business Rules:**
  - Previously added products remain in cart.

---

### SC-M02-012: Open Hamburger Menu

- **Actor:** Authenticated User
- **Precondition:** User on Inventory page.
- **Steps:**
  1. Click menu icon.
- **Expected Result:**
  - Sidebar menu opens.
- **Business Rules:**
  - Sidebar options become accessible.

---

### SC-M02-013: Logout Successfully

- **Actor:** Authenticated User
- **Precondition:** Sidebar menu open.
- **Steps:**
  1. Click Logout.
- **Expected Result:**
  - User redirected to Login page.
- **Business Rules:**
  - Session is terminated.

---

### SC-M02-014: Verify Cart Badge Persistence

- **Actor:** Authenticated User
- **Precondition:** Products added to cart.
- **Steps:**
  1. Sort products.
  2. Open and close menu.
- **Expected Result:**
  - Cart badge remains unchanged.
- **Business Rules:**
  - Sorting must not clear cart.

---

### SC-M02-015: Refresh Inventory Page

- **Actor:** Authenticated User
- **Precondition:** Items already in cart.
- **Steps:**
  1. Refresh browser.
- **Expected Result:**
  - Inventory reloads.
  - Cart selections remain.
- **Business Rules:**
  - Session state should persist.

---

## 5. Field Constraints

| Field | Required | Max Length | Format | Notes |
|-------|----------|------------|--------|-------|
| Sort Dropdown | Yes | N/A | Enum | Values: Name A-Z, Name Z-A, Price Low-High, Price High-Low |
| Add to Cart Button | Yes | N/A | Action | Changes to Remove after click |
| Remove Button | Yes | N/A | Action | Appears only after adding item |
| Product Link | Yes | N/A | Navigation | Opens Product Details |
| Shopping Cart Icon | Yes | N/A | Navigation | Opens Cart page |

---

## 6. Business Rules

- **BR-01:** Inventory page is accessible only after successful authentication.
- **BR-02:** Every inventory item must display image, title, description, price, and action button.
- **BR-03:** Add to Cart button changes to Remove after product selection.
- **BR-04:** Cart badge must accurately reflect selected products.
- **BR-05:** Duplicate additions of the same product are not permitted.
- **BR-06:** Sorting changes only the display order and does not modify cart contents.
- **BR-07:** Product links navigate to the corresponding Product Details page.
- **BR-08:** Shopping cart contents persist during the active session.
- **BR-09:** Logout terminates the session and redirects to the Login page.
- **BR-10:** Menu navigation must remain functional regardless of cart state.

---

## 7. Out of Scope for This Module

- Checkout workflow
- Shopping cart validation
- Product details page validation
- Payment processing
- Backend API validation
- Database verification
- Performance testing
- Mobile responsiveness
- Cross-browser compatibility
- Accessibility (WCAG) validation
- Security testing
```