# Business Scenarios — sauceLabs

Total: **21 scenario(s)**

---

## M01_BS_001: Access SauceLabs Login Page URL

**Business Objective:** Ensure unauthenticated visitors can access the official SauceLabs login page at the specified URL.
**Actor:** Guest / unauthenticated visitor
**Confidence:** 100%

**Preconditions:**
- Web browser is available and connected to the internet.

**Steps:**
1. Navigate to https://www.saucedemo.com/.

**Expected Result:** The SauceLabs login page is loaded successfully, displaying the username input, password input, and signin button.

**Traceability:**
- File: module_01_login.md | Req: REQ-002 | Section: 2. Page / Feature Structure
- File: module_01_login.md | Req: REQ-001 | Section: 1. Purpose

---

## M01_BS_002: User Login Validation

**Business Objective:** Authenticate a standard user into the SauceLabs portal using valid credentials.
**Actor:** standard_user
**Confidence:** 95%

**Preconditions:**
- User is on the login page at https://www.saucedemo.com/.

**Steps:**
1. Enter the username in the username input field.
2. Enter the password in the password input field.
3. Click the signin button.

**Expected Result:** The user is successfully authenticated and redirected into the SauceLabs application.

**Traceability:**
- File: module_01_login.md | Req: REQ-001 | Section: 1. Purpose
- File: module_01_login.md | Req: REQ-002 | Section: 2. Page / Feature Structure

---

## M01_BS_003: Login Form Missing Required Fields Validation

**Business Objective:** Ensure the login form validates required credentials prior to submission and displays inline error messages when mandatory inputs are omitted.
**Actor:** Guest / unauthenticated visitor
**Confidence:** 92%

**Preconditions:**
- The web browser is open and navigated to https://www.saucedemo.com/.

**Steps:**
1. Navigate to the login page URL https://www.saucedemo.com/.
2. Leave the username and password fields blank.
3. Click the signin button.

**Expected Result:** Form submission is prevented, and inline error messages appear next to the relevant required input fields.

**Business Rules:** BR-01, BR-02

**Traceability:**
- File: module_01_login.md | Req: REQ-001 | Section: 1. Purpose
- File: module_01_login.md | Req: REQ-002 | Section: 2. Page / Feature Structure

---

## M01_BS_004: Inline Error Message Display Placement Validation

**Business Objective:** Verify that form validation error messages are displayed inline next to the corresponding input fields when login validation fails.
**Actor:** Guest / unauthenticated visitor
**Confidence:** 90%

**Preconditions:**
- The user is on the SauceLabs login page at https://www.saucedemo.com/.

**Steps:**
1. Navigate to https://www.saucedemo.com/.
2. Leave one or both required input fields (username/password) blank.
3. Click the signin button to trigger validation.
4. Verify the position and formatting of the displayed error messages.

**Expected Result:** Validation error messages appear inline directly adjacent to the relevant invalid or missing field.

**Business Rules:** BR-01, BR-02

**Traceability:**
- File: module_01_login.md | Req: REQ-001 | Section: 1. Purpose
- File: module_01_login.md | Req: REQ-002 | Section: 2. Page / Feature Structure

---

## M01_BS_005: Standard User Login and Confirmation Redirection

**Business Objective:** Ensure standard_user can successfully authenticate using the login form and is automatically redirected to the confirmation page.
**Actor:** standard_user
**Confidence:** 95%

**Preconditions:**
- The login page at https://www.saucedemo.com/ is accessible.
- The user possesses valid credentials for standard_user.

**Steps:**
1. Navigate to https://www.saucedemo.com/.
2. Enter standard_user into the username field.
3. Enter the correct password into the password field.
4. Click the signin button.

**Expected Result:** The standard_user is successfully authenticated and the application redirects the user to /confirmation.

**Business Rules:** BR-03

**Traceability:**
- File: module_01_login.md | Req: REQ-001 | Section: 1. Purpose
- File: module_01_login.md | Req: REQ-003 | Section: 2. Page / Feature Structure

---

## M02_BS_001: View Inventory Page and Verify Product List

**Business Objective:** Ensure authenticated users can view the full product catalog and page elements.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is logged in with valid credentials.

**Steps:**
1. 1. Complete login process with valid credentials.
2. 2. Navigate to the Inventory page.
3. 3. Observe the product list, header elements, shopping cart icon, and sort dropdown.

**Expected Result:** The Inventory page loads successfully displaying six products, each showing an image, title, description, price, and 'Add to Cart' button.

**Business Rules:** BR-01, BR-02

**Traceability:**
- File: module_02_inventory.md | Req: REQ-001 | Section: SC-M02-001: View Inventory Page Successfully
- File: module_02_inventory.md | Req: REQ-002 | Section: SC-M02-002: Verify All Inventory Items are Displayed

---

## M02_BS_002: Add Single Item to Shopping Cart

**Business Objective:** Allow users to select an item from the inventory and add it to their cart.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is authenticated and on the Inventory page.

**Steps:**
1. 1. Locate a product on the Inventory page.
2. 2. Click the 'Add to Cart' button for the selected product.

**Expected Result:** The product's button text changes to 'Remove', and the shopping cart badge count increments by one.

**Business Rules:** BR-03, BR-04, BR-05

**Traceability:**
- File: module_02_inventory.md | Req: REQ-003 | Section: SC-M02-003: Add Single Item to Cart

---

## M02_BS_003: Remove Item from Cart via Inventory Page

**Business Objective:** Allow users to deselect an item directly from the Inventory page.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is authenticated and has at least one item added to the cart.

**Steps:**
1. 1. Locate an item previously added to the cart displaying a 'Remove' button.
2. 2. Click the 'Remove' button.

**Expected Result:** The item is removed from the cart, the button reverts to 'Add to Cart', and the shopping cart badge count decreases by one.

**Business Rules:** BR-03, BR-04

**Traceability:**
- File: module_02_inventory.md | Req: REQ-004 | Section: SC-M02-004: Remove Item from Cart

---

## M02_BS_004: Add Multiple Products to Shopping Cart

**Business Objective:** Enable users to select multiple distinct items and see accurate cart count updates.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is authenticated and on the Inventory page.

**Steps:**
1. 1. Click 'Add to Cart' on the first product.
2. 2. Click 'Add to Cart' on a second distinct product.
3. 3. Click 'Add to Cart' on a third distinct product.

**Expected Result:** All selected products show 'Remove' buttons and the cart badge accurately reflects the total unique count of selected items (3).

**Business Rules:** BR-04, BR-05

**Traceability:**
- File: module_02_inventory.md | Req: REQ-005 | Section: SC-M02-005: Add Multiple Products

---

## M02_BS_005: Sort Products Alphabetically from A to Z

**Business Objective:** Allow users to organize the product list alphabetically by name.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is authenticated and on the Inventory page.

**Steps:**
1. 1. Click the product sort dropdown menu.
2. 2. Select 'Name (A to Z)' option.

**Expected Result:** Products immediately rearrange in alphabetical order by name from A to Z.

**Business Rules:** BR-06

**Traceability:**
- File: module_02_inventory.md | Req: REQ-006 | Section: SC-M02-006: Sort Products by Name (A-Z)

---

## M02_BS_006: Sort Products Alphabetically from Z to A

**Business Objective:** Allow users to organize the product list in reverse alphabetical order.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is authenticated and on the Inventory page.

**Steps:**
1. 1. Click the product sort dropdown menu.
2. 2. Select 'Name (Z to A)' option.

**Expected Result:** Products immediately rearrange in reverse alphabetical order by name from Z to A.

**Business Rules:** BR-06

**Traceability:**
- File: module_02_inventory.md | Req: REQ-007 | Section: SC-M02-007: Sort Products by Name (Z-A)

---

## M02_BS_007: Sort Products by Price Ascending (Low to High)

**Business Objective:** Allow users to organize products starting from the lowest price.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is authenticated and on the Inventory page.

**Steps:**
1. 1. Click the product sort dropdown menu.
2. 2. Select 'Price (low to high)' option.

**Expected Result:** Products sort by ascending price, displaying the lowest priced item first.

**Business Rules:** BR-06

**Traceability:**
- File: module_02_inventory.md | Req: REQ-008 | Section: SC-M02-008: Sort Products by Price (Low to High)

---

## M02_BS_008: Sort Products by Price Descending (High to Low)

**Business Objective:** Allow users to organize products starting from the highest price.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is authenticated and on the Inventory page.

**Steps:**
1. 1. Click the product sort dropdown menu.
2. 2. Select 'Price (high to low)' option.

**Expected Result:** Products sort by descending price, displaying the highest priced item first.

**Business Rules:** BR-06

**Traceability:**
- File: module_02_inventory.md | Req: REQ-009 | Section: SC-M02-009: Sort Products by Price (High to Low)

---

## M02_BS_009: Navigate to Product Details Page

**Business Objective:** Enable users to view detailed information for a specific product.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is authenticated and on the Inventory page.

**Steps:**
1. 1. Click on a product title or product image in the inventory list.

**Expected Result:** The user is navigated to the corresponding Product Details page.

**Business Rules:** BR-07

**Traceability:**
- File: module_02_inventory.md | Req: REQ-010 | Section: SC-M02-010: Navigate to Product Details

---

## M02_BS_010: Open Shopping Cart Page from Inventory

**Business Objective:** Allow users to view items currently in their cart.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is authenticated and on the Inventory page with items in cart.

**Steps:**
1. 1. Click the shopping cart icon in the top header.

**Expected Result:** The Shopping Cart page opens with previously added products retained.

**Business Rules:** BR-08

**Traceability:**
- File: module_02_inventory.md | Req: REQ-011 | Section: SC-M02-011: Open Shopping Cart

---

## M02_BS_011: Open Sidebar Navigation Menu

**Business Objective:** Provide access to application navigation options via sidebar menu.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is authenticated and on the Inventory page.

**Steps:**
1. 1. Click the hamburger menu icon at the top left of the page.

**Expected Result:** The sidebar menu opens, rendering navigation options accessible.

**Business Rules:** BR-10

**Traceability:**
- File: module_02_inventory.md | Req: REQ-012 | Section: SC-M02-012: Open Hamburger Menu

---

## M02_BS_012: User Logout via Sidebar Menu

**Business Objective:** Allow users to terminate their active session securely.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is authenticated and on the Inventory page.

**Steps:**
1. 1. Click the menu icon to open the sidebar menu.
2. 2. Click the 'Logout' menu option.

**Expected Result:** The user session is terminated and the user is redirected to the Login page.

**Business Rules:** BR-09

**Traceability:**
- File: module_02_inventory.md | Req: REQ-013 | Section: SC-M02-013: Logout Successfully

---

## M02_BS_013: Verify Cart Badge Persistence Across UI Interactions

**Business Objective:** Ensure active cart items and badge counts are preserved during sorting or menu toggling.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is authenticated and has items added to the cart.

**Steps:**
1. 1. Add one or more products to the cart on the Inventory page.
2. 2. Change product sorting order using the sort dropdown.
3. 3. Open and close the hamburger sidebar menu.

**Expected Result:** The shopping cart badge retains its accurate count and added items remain selected without being cleared or modified.

**Business Rules:** BR-04, BR-06, BR-10

**Traceability:**
- File: module_02_inventory.md | Req: REQ-014 | Section: SC-M02-014: Verify Cart Badge Persistence

---

## M02_BS_014: Refresh Inventory Page and Preserve Session State

**Business Objective:** Ensure page refreshes do not lose active session data or cart selections.
**Actor:** Primary User
**Confidence:** 100%

**Preconditions:**
- User is authenticated and has added products to the cart on the Inventory page.

**Steps:**
1. 1. Refresh the web browser on the Inventory page.

**Expected Result:** The Inventory page reloads successfully, maintaining session state and preserving active cart selections and badge count.

**Business Rules:** BR-08

**Traceability:**
- File: module_02_inventory.md | Req: REQ-015 | Section: SC-M02-015: Refresh Inventory Page

---

## M02_BS_015: Enforce Non-Duplicate Product Selection in Shopping Cart

**Business Objective:** Ensure that users cannot add duplicate instances of the same product to the shopping cart, enforcing unique product selection and state management.
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is authenticated and currently viewing the Inventory page.

**Steps:**
1. Click 'Add to Cart' for a selected product in the inventory list.
2. Observe the product action button and the shopping cart badge count.
3. Verify that the button state transitions to 'Remove' and no additional 'Add to Cart' action is available for that product.

**Expected Result:** The product button changes to 'Remove', preventing duplicate additions of the same product, and the cart badge count reflects exactly 1 unique product.

**Business Rules:** BR-03, BR-05

**Traceability:**
- File: module_02_inventory.md | Req: REQ-003 | Section: 4. Business Scenarios
- File: module_02_inventory.md | Req: REQ-005 | Section: 4. Business Scenarios

---

## M02_BS_016: Restrict Access to Inventory Page for Unauthenticated Users

**Business Objective:** Ensure system security by preventing unauthenticated access to the product inventory page.
**Actor:** Automated Test Agent
**Confidence:** 95%

**Preconditions:**
- The browser session is unauthenticated and lacks a valid session state.

**Steps:**
1. Attempt to navigate directly to the Inventory page URL.

**Expected Result:** Access is denied and the user is redirected to the Login page in accordance with authentication security rules.

**Business Rules:** BR-01

**Traceability:**
- File: module_02_inventory.md | Req: REQ-001 | Section: 4. Business Scenarios

---
