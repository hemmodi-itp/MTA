# Test Data — sauceLabs

Total: **14 dataset(s)**

---

## TD-005: BS-001 — View Complete Inventory Page Layout

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative Variants

---

## TD-006: BS-002 — Display All Six Inventory Products

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative Variants

---

## TD-007: BS-003 — Add Single Product to Shopping Cart

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative Variants

---

## TD-008: BS-004 — Remove Product from Shopping Cart

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative Variants

---

## TD-009: BS-005 — Sort Products Alphabetically A to Z

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative Variants

---

## TD-010: BS-006 — Sort Products Alphabetically Z to A

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Name (Z to A) |

### Negative Variants

#### NEG-001 (`empty`) — No sort option selected  
*Expected error: Please select a sort option*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | `""` |

#### NEG-002 (`whitespace`) — Sort option contains only whitespace  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select |     |

#### NEG-003 (`special_chars`) — XSS injection attempt in sort selection  
*Expected error: Invalid sort option format*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | <script>alert('xss')</script> |

#### NEG-004 (`sql_injection`) — SQL injection attempt in sort selection  
*Expected error: Invalid sort option value*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | ' OR '1'='1 |

#### NEG-005 (`wrong_format`) — Invalid sort option not in dropdown list  
*Expected error: Selected sort option is not available*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Random Order XYZ |

#### NEG-006 (`too_long`) — Sort option value exceeds maximum length  
*Expected error: Sort option value too long*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa |

#### NEG-007 (`at_boundary`) — Sort option at maximum character boundary  
*Expected error: Sort option not recognized*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa |

#### NEG-008 (`url_input`) — URL input in sort selection field  
*Expected error: Invalid sort option format*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | https://evil.com/redirect |

#### NEG-009 (`unicode`) — Unicode characters in sort selection  
*Expected error: Sort option contains invalid characters*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Name (🔥 to 🎉) |

#### NEG-010 (`random`) — Unexpected random value in sort selection  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | 12345!@#$% |

---

## TD-011: BS-007 — Sort Products by Price Low to High

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative Variants

---

## TD-012: BS-008 — Sort Products by Price High to Low

**Actor:** Primary User

### Positive Dataset

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Price (high to low) |

### Negative Variants

#### NEG-001 (`empty`) — No sort option selected  
*Expected error: Please select a sort option*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | `""` |

#### NEG-002 (`special_chars`) — XSS injection attempt in sort selection  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | <script>alert('xss')</script> |

#### NEG-003 (`sql_injection`) — SQL injection attempt in sort selection  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | ' OR '1'='1 |

#### NEG-004 (`wrong_format`) — Invalid sort option not in dropdown  
*Expected error: Selected sort option is not available*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | Invalid Sort Option |

#### NEG-005 (`url_input`) — URL injection in sort selection  
*Expected error: Invalid sort option selected*

| Field | Type | Value |
|---|---|---|
| select_sort_option | select | https://evil.com/redirect |

---

## TD-013: BS-009 — Navigate to Product Details Page

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative Variants

---

## TD-014: BS-010 — Access Shopping Cart Page

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative Variants

---

## TD-015: BS-011 — Open Navigation Menu

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative Variants

---

## TD-016: BS-012 — Logout from Application

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative Variants

---

## TD-017: BS-013 — Verify Cart Persistence During Interface Interactions

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative Variants

---

## TD-018: BS-014 — Maintain Cart State After Page Refresh

**Actor:** Primary User

### Positive Dataset

_No input fields identified for this scenario._

### Negative Variants

---
