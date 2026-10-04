# Business Scenarios — sauceLabs

Total: **13 scenario(s)**

---

## BS-001: Display Complete Inventory Page Layout

**Business Objective:** Ensure users can access all inventory page components for product browsing
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is successfully authenticated and logged in

**Steps:**
1. Navigate to the inventory page
2. Verify header displays application logo, hamburger menu, shopping cart icon, and cart badge
3. Verify product sort dropdown is visible with sorting options
4. Verify inventory list displays all available products
5. Verify footer displays footer information and social media links

**Expected Result:** Complete inventory page layout is displayed with all required components visible and functional

**Business Rules:** BR-01, BR-02

**Traceability:**
- File: module_02_inventory.md | Req: REQ-001 | Section: 2. Page / Feature Structure
- File: module_02_inventory.md | Req: REQ-002 | Section: 2. Page / Feature Structure
- File: module_02_inventory.md | Req: REQ-003 | Section: 2. Page / Feature Structure
- File: module_02_inventory.md | Req: REQ-006 | Section: 2. Page / Feature Structure

---

## BS-002: Verify All Six Inventory Products Display

**Business Objective:** Ensure complete product catalog is available for customer selection
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is on the inventory page

**Steps:**
1. Count the number of inventory products displayed
2. Verify each product card contains product image, name, description, price, and Add to Cart button

**Expected Result:** Exactly six inventory products are displayed with complete product information on each card

**Business Rules:** BR-02

**Traceability:**
- File: module_02_inventory.md | Req: REQ-007 | Section: SC-M02-002: Verify All Inventory Items are Displayed
- File: module_02_inventory.md | Req: REQ-004 | Section: 2. Page / Feature Structure

---

## BS-003: Add Single Product to Shopping Cart

**Business Objective:** Enable customers to select products for purchase
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is on the inventory page
- Cart is empty or contains other items
- Target product is not already in cart

**Steps:**
1. Click the Add to Cart button on a specific product
2. Verify the button changes to Remove
3. Verify the cart badge increments by one

**Expected Result:** Product is added to cart, button changes to Remove, and cart badge shows updated count

**Business Rules:** BR-03, BR-04, BR-05

**Traceability:**
- File: module_02_inventory.md | Req: REQ-008 | Section: SC-M02-003: Add Single Item to Cart
- File: module_02_inventory.md | Req: REQ-009 | Section: SC-M02-003: Add Single Item to Cart

---

## BS-004: Remove Product from Shopping Cart

**Business Objective:** Allow customers to modify their cart by removing unwanted items
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is on the inventory page
- At least one product is already in the cart
- Target product shows Remove button

**Steps:**
1. Click the Remove button on a product that is in the cart
2. Verify the button changes back to Add to Cart
3. Verify the cart badge decreases by one

**Expected Result:** Product is removed from cart, button changes to Add to Cart, and cart badge shows decreased count

**Business Rules:** BR-03, BR-04

**Traceability:**
- File: module_02_inventory.md | Req: REQ-010 | Section: SC-M02-004: Remove Item from Cart
- File: module_02_inventory.md | Req: REQ-011 | Section: SC-M02-004: Remove Item from Cart

---

## BS-005: Sort Products by Name Alphabetically

**Business Objective:** Help customers find products easily by alphabetical organization
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is on the inventory page
- Products are displayed in default order

**Steps:**
1. Click on the product sort dropdown
2. Select Name (A to Z) option
3. Verify products are rearranged in alphabetical order by name

**Expected Result:** Products are displayed in alphabetical order from A to Z by product name

**Business Rules:** BR-06

**Traceability:**
- File: module_02_inventory.md | Req: REQ-012 | Section: SC-M02-006: Sort Products by Name (A-Z)

---

## BS-006: Sort Products by Name Reverse Alphabetically

**Business Objective:** Provide alternative product organization for customer convenience
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is on the inventory page
- Products are displayed in any current order

**Steps:**
1. Click on the product sort dropdown
2. Select Name (Z to A) option
3. Verify products are rearranged in reverse alphabetical order by name

**Expected Result:** Products are displayed in reverse alphabetical order from Z to A by product name

**Business Rules:** BR-06

**Traceability:**
- File: module_02_inventory.md | Req: REQ-013 | Section: SC-M02-007: Sort Products by Name (Z-A)

---

## BS-007: Sort Products by Price Low to High

**Business Objective:** Enable price-conscious customers to find affordable options first
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is on the inventory page
- Products are displayed in any current order

**Steps:**
1. Click on the product sort dropdown
2. Select Price (low to high) option
3. Verify products are rearranged in ascending price order

**Expected Result:** Products are displayed with lowest priced items first, ascending to highest priced items

**Business Rules:** BR-06

**Traceability:**
- File: module_02_inventory.md | Req: REQ-014 | Section: SC-M02-008: Sort Products by Price (Low to High)

---

## BS-008: Sort Products by Price High to Low

**Business Objective:** Allow customers to view premium products first
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is on the inventory page
- Products are displayed in any current order

**Steps:**
1. Click on the product sort dropdown
2. Select Price (high to low) option
3. Verify products are rearranged in descending price order

**Expected Result:** Products are displayed with highest priced items first, descending to lowest priced items

**Business Rules:** BR-06

**Traceability:**
- File: module_02_inventory.md | Req: REQ-015 | Section: SC-M02-009: Sort Products by Price (High to Low)

---

## BS-009: Navigate to Product Details Page

**Business Objective:** Provide customers with detailed product information for informed purchasing decisions
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is on the inventory page
- Products are displayed with clickable images and titles

**Steps:**
1. Click on a product image or product title
2. Verify navigation occurs to the Product Details page for the selected product

**Expected Result:** User is navigated to the Product Details page showing detailed information for the selected product

**Business Rules:** BR-07

**Traceability:**
- File: module_02_inventory.md | Req: REQ-016 | Section: SC-M02-010: Navigate to Product Details

---

## BS-010: Access Shopping Cart Page

**Business Objective:** Allow customers to review and manage their selected items
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is on the inventory page
- Shopping cart icon is visible in the header

**Steps:**
1. Click on the shopping cart icon
2. Verify navigation occurs to the shopping cart page

**Expected Result:** User is navigated to the shopping cart page displaying current cart contents

**Business Rules:** BR-08

**Traceability:**
- File: module_02_inventory.md | Req: REQ-017 | Section: SC-M02-011: Open Shopping Cart
- File: module_02_inventory.md | Req: REQ-005 | Section: 2. Page / Feature Structure

---

## BS-011: Open Navigation Menu

**Business Objective:** Provide users access to application navigation options
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is on the inventory page
- Hamburger menu icon is visible in the header

**Steps:**
1. Click on the hamburger menu icon
2. Verify the sidebar menu opens with navigation options

**Expected Result:** Sidebar menu opens displaying available navigation options

**Business Rules:** BR-10

**Traceability:**
- File: module_02_inventory.md | Req: REQ-018 | Section: SC-M02-012: Open Hamburger Menu

---

## BS-012: Logout and Return to Login Page

**Business Objective:** Securely terminate user session and redirect to authentication
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is logged in and on the inventory page
- Hamburger menu is accessible

**Steps:**
1. Click on the hamburger menu icon to open sidebar menu
2. Click on the Logout option
3. Verify redirection to the Login page occurs

**Expected Result:** User session is terminated and user is redirected to the Login page

**Business Rules:** BR-09

**Traceability:**
- File: module_02_inventory.md | Req: REQ-019 | Section: SC-M02-013: Logout Successfully

---

## BS-013: Maintain Cart Contents After Page Refresh

**Business Objective:** Ensure cart persistence during user session for improved shopping experience
**Actor:** Primary User
**Confidence:** 95%

**Preconditions:**
- User is on the inventory page
- One or more items have been added to the cart
- Cart badge shows current item count

**Steps:**
1. Note the current cart contents and badge count
2. Refresh the browser page
3. Verify cart selections and badge count remain unchanged

**Expected Result:** Cart contents and badge count are preserved after page refresh

**Business Rules:** BR-08

**Traceability:**
- File: module_02_inventory.md | Req: REQ-020 | Section: SC-M02-015: Refresh Inventory Page

---
