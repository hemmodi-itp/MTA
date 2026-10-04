# Test Data — sauceLabs

Total: **35 dataset(s)**

---

## TD-005: BS-001 — View Complete Inventory Page Layout

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative & Boundary Variants

---

## TD-006: BS-002 — Display All Six Inventory Products

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative & Boundary Variants

---

## TD-007: BS-003 — Add Single Product to Shopping Cart

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative & Boundary Variants

---

## TD-008: BS-004 — Remove Product from Shopping Cart

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative & Boundary Variants

---

## TD-009: BS-005 — Sort Products Alphabetically A to Z

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative & Boundary Variants

---

## TD-010: BS-006 — Sort Products Alphabetically Z to A

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Name (Z to A) |

### Negative & Boundary Variants

#### NEG-001 (`empty`) — No sort option selected

**Iteration 1**  
*Expected error: Please select a sort option*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | `""` |

#### NEG-002 (`whitespace`) — Sort option contains only whitespace

**Iteration 1**  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select |     |

#### NEG-003 (`special_chars`) — XSS injection attempt in sort selection

**Iteration 1**  
*Expected error: Invalid sort option format*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | <script>alert('xss')</script> |

#### NEG-004 (`sql_injection`) — SQL injection attempt in sort selection

**Iteration 1**  
*Expected error: Invalid sort option value*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | ' OR '1'='1 |

#### NEG-005 (`wrong_format`) — Invalid sort option not in dropdown list

**Iteration 1**  
*Expected error: Selected sort option is not available*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Random Order XYZ |

#### NEG-006 (`too_long`) — Sort option value exceeds maximum length

**Iteration 1**  
*Expected error: Sort option value too long*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa |

#### NEG-007 (`at_boundary`) — Sort option at maximum character boundary

**Iteration 1**  
*Expected error: Sort option not recognized*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa |

#### NEG-008 (`url_input`) — URL input in sort selection field

**Iteration 1**  
*Expected error: Invalid sort option format*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | https://evil.com/redirect |

#### NEG-009 (`unicode`) — Unicode characters in sort selection

**Iteration 1**  
*Expected error: Sort option contains invalid characters*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Name (🔥 to 🎉) |

#### NEG-010 (`random`) — Unexpected random value in sort selection

**Iteration 1**  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | 12345!@#$% |

---

## TD-011: BS-007 — Sort Products by Price Low to High

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative & Boundary Variants

---

## TD-012: BS-008 — Sort Products by Price High to Low

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Price (high to low) |

### Negative & Boundary Variants

#### NEG-001 (`empty`) — No sort option selected

**Iteration 1**  
*Expected error: Please select a sort option*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | `""` |

#### NEG-002 (`special_chars`) — XSS injection attempt in sort selection

**Iteration 1**  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | <script>alert('xss')</script> |

#### NEG-003 (`sql_injection`) — SQL injection attempt in sort selection

**Iteration 1**  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | ' OR '1'='1 |

#### NEG-004 (`wrong_format`) — Invalid sort option not in dropdown

**Iteration 1**  
*Expected error: Selected sort option is not available*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Invalid Sort Option |

#### NEG-005 (`url_input`) — URL injection in sort selection

**Iteration 1**  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | https://evil.com/redirect |

---

## TD-013: BS-009 — Navigate to Product Details Page

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative & Boundary Variants

---

## TD-014: BS-010 — Access Shopping Cart Page

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative & Boundary Variants

---

## TD-015: BS-011 — Open Navigation Menu

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative & Boundary Variants

---

## TD-016: BS-012 — Logout from Application

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative & Boundary Variants

---

## TD-017: BS-013 — Verify Cart Persistence During Interface Interactions

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative & Boundary Variants

---

## TD-018: BS-014 — Maintain Cart State After Page Refresh

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative & Boundary Variants

---

## TD-015: M01_BS_001 — Access SauceLabs Login Page URL

**Actor:** Guest / unauthenticated visitor

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_url | url | https://www.saucedemo.com/ |
| assert_username_input | assertion | Username |
| assert_password_input | assertion | Password |
| assert_login_button | assertion | Login |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Target URL is unreachable or returns page error preventing login form rendering

**Iteration 1**  
*Expected error: 404 Page Not Found - Login form elements fail to load*

| Field | Type | Value |
|---|---|---|
| navigate_url | url | https://www.saucedemo.com/invalid-page |
| assert_username_input | assertion | Username |
| assert_password_input | assertion | Password |
| assert_login_button | assertion | Login |

---

## TD-016: M01_BS_002 — User Login Validation

**Actor:** standard_user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| fill_username | text | standard_user |
| fill_password | password | secret_sauce |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Missing credentials or invalid username and password combinations

**Iteration 1**  
*Expected error: Epic sadface: Username is required*

| Field | Type | Value |
|---|---|---|
| fill_username | text | `""` |
| fill_password | password | secret_sauce |

**Iteration 2**  
*Expected error: Epic sadface: Password is required*

| Field | Type | Value |
|---|---|---|
| fill_username | text | standard_user |
| fill_password | password | `""` |

**Iteration 3**  
*Expected error: Epic sadface: Username and password do not match any user in this service*

| Field | Type | Value |
|---|---|---|
| fill_username | text | invalid_user |
| fill_password | password | wrong_password |

#### NEG-002 (`boundary`) — Username field length exceeding maximum limits

**Iteration 1**  
*Expected error: Epic sadface: Username and password do not match any user in this service*

| Field | Type | Value |
|---|---|---|
| fill_username | text | user_exceeding_255_characters_limit_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa |
| fill_password | password | secret_sauce |

---

## TD-017: M02_BS_001 — View Inventory Page and Verify Product List

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_inventory_url | url | /inventory.html |
| assert_page_header | assertion | Products |
| assert_product_count | count_min | 6 |
| assert_cart_icon | assertion | shopping_cart_link |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Page fails to load catalog elements or redirects to login page

**Iteration 1**  
*Expected error: Expected at least 6 products, but found 0*

| Field | Type | Value |
|---|---|---|
| navigate_inventory_url | url | /inventory.html |
| assert_page_header | assertion | Products |
| assert_product_count | count_min | 0 |
| assert_cart_icon | assertion | shopping_cart_link |

**Iteration 2**  
*Expected error: Navigation target redirected to login page instead of inventory page*

| Field | Type | Value |
|---|---|---|
| navigate_inventory_url | url | /index.html |
| assert_page_header | assertion | Products |
| assert_product_count | count_min | 6 |
| assert_cart_icon | assertion | shopping_cart_link |

---

## TD-018: M02_BS_002 — Add Single Item to Shopping Cart

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| select_product_item | assertion | Sauce Labs Backpack |
| assert_button_text | assertion | Remove |
| assert_cart_badge_count | count_min | 1 |
| assert_page_url | url | /inventory.html |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Product failed to be added to cart and badge count did not increment

**Iteration 1**  
*Expected error: Item state failed to update: button text remained 'Add to cart' and badge count did not increment*

| Field | Type | Value |
|---|---|---|
| select_product_item | assertion | Sauce Labs Backpack |
| assert_button_text | assertion | Add to cart |
| assert_cart_badge_count | count_min | 0 |
| assert_page_url | url | /inventory.html |

---

## TD-019: M02_BS_003 — Remove Item from Cart via Inventory Page

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| select_product_item | assertion | Sauce Labs Backpack |
| assert_button_text | assertion | Add to cart |
| assert_cart_badge_count | count_min | 0 |
| expected_url | url | /inventory.html |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Item removal action fails to update button label or decrement cart count

**Iteration 1**  
*Expected error: Button text failed to revert to 'Add to cart' and cart badge count was not decremented*

| Field | Type | Value |
|---|---|---|
| select_product_item | assertion | Sauce Labs Backpack |
| assert_button_text | assertion | Remove |
| assert_cart_badge_count | count_min | 1 |
| expected_url | url | /inventory.html |

**Iteration 2**  
*Expected error: Cart badge count remained unchanged after item removal*

| Field | Type | Value |
|---|---|---|
| select_product_item | assertion | Sauce Labs Backpack |
| assert_button_text | assertion | Add to cart |
| assert_cart_badge_count | count_min | 1 |
| expected_url | url | /inventory.html |

---

## TD-020: M02_BS_004 — Add Multiple Products to Shopping Cart

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| assert_cart_badge_count | count_min | 3 |
| assert_button_state_text | assertion | Remove |
| assert_inventory_page_url | url | /inventory.html |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Cart count or button state failed to update after adding multiple products

**Iteration 1**  
*Expected error: Cart badge count is missing or button state did not change to Remove*

| Field | Type | Value |
|---|---|---|
| assert_cart_badge_count | count_min | 0 |
| assert_button_state_text | assertion | Add to cart |
| assert_inventory_page_url | url | /inventory.html |

**Iteration 2**  
*Expected error: Cart badge count shows 1 instead of expected count 3*

| Field | Type | Value |
|---|---|---|
| assert_cart_badge_count | count_min | 1 |
| assert_button_state_text | assertion | Remove |
| assert_inventory_page_url | url | /inventory.html |

---

## TD-021: M02_BS_005 — Sort Products Alphabetically from A to Z

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Name (A to Z) |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Invalid or unselected sort option

**Iteration 1**  
*Expected error: Please select a valid sort option*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | `""` |

**Iteration 2**  
*Expected error: Selected sort option is not supported*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | INVALID_SORT_VALUE |

---

## TD-022: M02_BS_006 — Sort Products Alphabetically from Z to A

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Name (Z to A) |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Invalid or unselected sort option

**Iteration 1**  
*Expected error: Please select a sort option*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | `""` |

**Iteration 2**  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | invalid_option |

---

## TD-023: M02_BS_007 — Sort Products by Price Ascending (Low to High)

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Price (low to high) |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Invalid or missing sort option selection

**Iteration 1**  
*Expected error: Please select a sort option*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | `""` |

**Iteration 2**  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | invalid_option |

---

## TD-024: M02_BS_008 — Sort Products by Price Descending (High to Low)

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Price (high to low) |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Invalid or unselected sort option

**Iteration 1**  
*Expected error: Please select a sort option*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | `""` |

**Iteration 2**  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | invalid_option |

---

## TD-025: M02_BS_009 — Navigate to Product Details Page

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_product_title | navigation | Sauce Labs Backpack |
| assert_product_title | assertion | Sauce Labs Backpack |
| assert_product_url | url | /inventory-item.html?id=4 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Product details page fails to render or target URL is invalid

**Iteration 1**  
*Expected error: Product details failed to load for the selected item*

| Field | Type | Value |
|---|---|---|
| click_product_title | navigation | Sauce Labs Backpack |
| assert_product_title | assertion | Item Not Found |
| assert_product_url | url | /404 |

**Iteration 2**  
*Expected error: Navigation target product does not exist*

| Field | Type | Value |
|---|---|---|
| click_product_title | navigation | Invalid Product |
| assert_product_title | assertion | `""` |
| assert_product_url | url | /inventory.html |

---

## TD-026: M02_BS_010 — Open Shopping Cart Page from Inventory

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_cart_icon | navigation | Shopping Cart Container |
| assert_cart_url | url | https://www.saucedemo.com/cart.html |
| assert_cart_heading | assertion | Your Cart |
| assert_min_items_count | count_min | 1 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Cart page opens but previously added items fail to render

**Iteration 1**  
*Expected error: Cart page loaded but retained products were missing*

| Field | Type | Value |
|---|---|---|
| click_cart_icon | navigation | Shopping Cart Container |
| assert_cart_url | url | https://www.saucedemo.com/cart.html |
| assert_cart_heading | assertion | Your Cart |
| assert_min_items_count | count_min | 0 |

---

## TD-027: M02_BS_011 — Open Sidebar Navigation Menu

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| click_menu_button | navigation | hamburger_menu_icon |
| assert_sidebar_visible | assertion | bm-menu-wrap |
| assert_navigation_link | assertion | All Items |
| assert_menu_items_count | count_min | 4 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Sidebar navigation menu fails to render or open upon clicking menu icon

**Iteration 1**  
*Expected error: Sidebar navigation menu failed to open*

| Field | Type | Value |
|---|---|---|
| click_menu_button | navigation | hamburger_menu_icon |
| assert_sidebar_visible | assertion | `""` |
| assert_navigation_link | assertion | `""` |
| assert_menu_items_count | count_min | 0 |

---

## TD-028: M02_BS_012 — User Logout via Sidebar Menu

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| expected_url | url | https://www.saucedemo.com/ |
| expected_heading | assertion | Swag Labs |
| expected_login_button | assertion | Login |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Session termination failure keeping user on inventory page

**Iteration 1**  
*Expected error: User session was not terminated and user was not redirected to login*

| Field | Type | Value |
|---|---|---|
| expected_url | url | https://www.saucedemo.com/inventory.html |
| expected_heading | assertion | Products |
| expected_login_button | assertion | `""` |

---

## TD-029: M02_BS_013 — Verify Cart Badge Persistence Across UI Interactions

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| select_product | select | Sauce Labs Backpack |
| select_sort_option | select | Price (low to high) |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Invalid or unselected sort option submitted

**Iteration 1**  
*Expected error: Please select a valid sort option*

| Field | Type | Value |
|---|---|---|
| select_product | select | Sauce Labs Backpack |
| select_sort_option | select | `""` |

**Iteration 2**  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_product | select | Sauce Labs Backpack |
| select_sort_option | select | INVALID_SORT_KEY |

---

## TD-030: M02_BS_014 — Refresh Inventory Page and Preserve Session State

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| assert_page_url | url | https://www.saucedemo.com/inventory.html |
| assert_page_heading | assertion | Products |
| assert_cart_badge_count | assertion | 2 |
| assert_min_cart_items | count_min | 2 |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Session or cart state lost after browser refresh

**Iteration 1**  
*Expected error: Session lost after browser refresh; user redirected to login page*

| Field | Type | Value |
|---|---|---|
| assert_page_url | url | https://www.saucedemo.com/ |
| assert_page_heading | assertion | Login |
| assert_cart_badge_count | assertion | `""` |
| assert_min_cart_items | count_min | 0 |

**Iteration 2**  
*Expected error: Cart items and badge count were not preserved after browser refresh*

| Field | Type | Value |
|---|---|---|
| assert_page_url | url | https://www.saucedemo.com/inventory.html |
| assert_page_heading | assertion | Products |
| assert_cart_badge_count | assertion | 0 |
| assert_min_cart_items | count_min | 0 |

---

## TD-031: M01_BS_003 — Login Form Missing Required Fields Validation

**Actor:** Guest / unauthenticated visitor

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| fill_username | text | standard_user |
| fill_password | password | secret_sauce |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Missing required credentials on form submission

**Iteration 1**  
*Expected error: Epic sadface: Username is required*

| Field | Type | Value |
|---|---|---|
| fill_username | text | `""` |
| fill_password | password | `""` |

**Iteration 2**  
*Expected error: Epic sadface: Password is required*

| Field | Type | Value |
|---|---|---|
| fill_username | text | standard_user |
| fill_password | password | `""` |

**Iteration 3**  
*Expected error: Epic sadface: Username is required*

| Field | Type | Value |
|---|---|---|
| fill_username | text | `""` |
| fill_password | password | secret_sauce |

#### NEG-002 (`boundary`) — Credentials exceeding standard length limit of 255 characters

**Iteration 1**  
*Expected error: Epic sadface: Username and password do not match any user in this service*

| Field | Type | Value |
|---|---|---|
| fill_username | text | user_255_limit_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa |
| fill_password | password | secret_sauce |

---

## TD-032: M02_BS_015 — Enforce Non-Duplicate Product Selection in Shopping Cart

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| assert_product_item | assertion | Sauce Labs Backpack |
| assert_button_state | assertion | Remove |
| assert_cart_badge_count | assertion | 1 |
| assert_inventory_url | url | /inventory.html |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Button state fails to change to Remove or duplicate item increments cart badge count

**Iteration 1**  
*Expected error: Duplicate item allowed in shopping cart; button state remained 'Add to cart' and cart badge incremented to 2.*

| Field | Type | Value |
|---|---|---|
| assert_product_item | assertion | Sauce Labs Backpack |
| assert_button_state | assertion | Add to cart |
| assert_cart_badge_count | assertion | 2 |
| assert_inventory_url | url | /inventory.html |

**Iteration 2**  
*Expected error: Button state failed to transition to 'Remove' after adding product to cart.*

| Field | Type | Value |
|---|---|---|
| assert_product_item | assertion | Sauce Labs Backpack |
| assert_button_state | assertion | Add to cart |
| assert_cart_badge_count | assertion | 1 |
| assert_inventory_url | url | /inventory.html |

---

## TD-033: M02_BS_016 — Restrict Access to Inventory Page for Unauthenticated Users

**Actor:** Automated Test Agent

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| navigate_target_url | url | https://www.saucedemo.com/inventory.html |
| expected_redirect_url | url | https://www.saucedemo.com/ |
| expected_error_assertion | assertion | Epic sadface: You can only access 'inventory.html' when you are logged in. |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Unauthenticated user direct navigation is not blocked or fails to redirect to login

**Iteration 1**  
*Expected error: User was improperly permitted access to inventory page without authentication*

| Field | Type | Value |
|---|---|---|
| navigate_target_url | url | https://www.saucedemo.com/inventory.html |
| expected_redirect_url | url | https://www.saucedemo.com/inventory.html |
| expected_error_assertion | assertion | `""` |

---

## TD-034: M01_BS_004 — Inline Error Message Display Placement Validation

**Actor:** Guest / unauthenticated visitor

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| fill_username | text | standard_user |
| fill_password | password | secret_sauce |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Missing required username or password fields

**Iteration 1**  
*Expected error: Epic sadface: Username is required*

| Field | Type | Value |
|---|---|---|
| fill_username | text | `""` |
| fill_password | password | `""` |

**Iteration 2**  
*Expected error: Epic sadface: Password is required*

| Field | Type | Value |
|---|---|---|
| fill_username | text | standard_user |
| fill_password | password | `""` |

**Iteration 3**  
*Expected error: Epic sadface: Username is required*

| Field | Type | Value |
|---|---|---|
| fill_username | text | `""` |
| fill_password | password | secret_sauce |

#### NEG-002 (`boundary`) — Username field at 255-character maximum length limit

**Iteration 1**  
*Expected error: Epic sadface: Username and password do not match any user in this service*

| Field | Type | Value |
|---|---|---|
| fill_username | text | user_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa |
| fill_password | password | secret_sauce |

---

## TD-035: M01_BS_005 — Standard User Login and Confirmation Redirection

**Actor:** standard_user

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| fill_username | text | standard_user |
| fill_password | password | secret_sauce |

### Negative & Boundary Variants

#### NEG-001 (`negative`) — Invalid or missing credentials provided during login

**Iteration 1**  
*Expected error: Epic sadface: Username is required*

| Field | Type | Value |
|---|---|---|
| fill_username | text | `""` |
| fill_password | password | secret_sauce |

**Iteration 2**  
*Expected error: Epic sadface: Password is required*

| Field | Type | Value |
|---|---|---|
| fill_username | text | standard_user |
| fill_password | password | `""` |

**Iteration 3**  
*Expected error: Epic sadface: Username and password do not match any user in this service*

| Field | Type | Value |
|---|---|---|
| fill_username | text | standard_user |
| fill_password | password | invalid_password |

#### NEG-002 (`boundary`) — Username field exceeding standard length limits

**Iteration 1**  
*Expected error: Epic sadface: Username and password do not match any user in this service*

| Field | Type | Value |
|---|---|---|
| fill_username | text | standard_user_abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijkl |
| fill_password | password | secret_sauce |

---
